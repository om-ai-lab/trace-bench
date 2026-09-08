"""ThinkStream-3B adapter for the Open Stream Bench Core.

ThinkStream dependencies are imported lazily so the public OSB package remains
installable without the private ThinkStream environment.
"""

from __future__ import annotations

import importlib
import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .models import (
    AdapterCapabilities,
    EventKind,
    FatalEvaluationError,
    ModelEvent,
    Observation,
    QueryRequest,
    RecordContext,
    TaskName,
)


_CONTROL_RE = re.compile(r"<response>(.*?)((?:<\|im_end\|>)|$)", re.DOTALL)


def _is_cuda_fatal_error(exc: BaseException) -> bool:
    """Return whether ``exc`` indicates an unrecoverable CUDA context.

    A device-side assert leaves the CUDA context poisoned.  Continuing to the
    next record in the same process would turn one root failure into a long
    series of misleading per-record failures, so this is deliberately
    conservative for CUDA context/device-assert messages.
    """

    text = str(exc).lower()
    fatal_markers = (
        "device-side assert",
        "device side assert",
        "cuda error: an illegal memory access",
        "illegal memory access was encountered",
        "cuda context",
        "context is corrupted",
        "cuda error: initialization error",
        "cuda error: unknown error",
    )
    return any(marker in text for marker in fatal_markers)


def _raise_fatal_cuda_error(exc: BaseException) -> None:
    """Translate a poisoned CUDA-context error into the Core fatal path."""

    if _is_cuda_fatal_error(exc):
        raise FatalEvaluationError(
            "ThinkStream model process became unusable after a fatal CUDA error: "
            f"{exc}"
        ) from exc


def _git_revision(root: str | None) -> str | None:
    if root is None:
        return None
    git_dir = Path(root) / ".git"
    head = git_dir / "HEAD"
    if not head.is_file():
        return None
    value = head.read_text(encoding="utf-8").strip()
    if not value.startswith("ref: "):
        return value
    ref = git_dir / value.removeprefix("ref: ")
    return ref.read_text(encoding="utf-8").strip() if ref.is_file() else None


def parse_thinkstream_output(text: str) -> tuple[str, str, str]:
    """Return ``(decision, response, think)`` from raw control-token text."""

    raw = text or ""
    think = ""
    think_match = re.search(r"<think>(.*?)</think>", raw, flags=re.DOTALL)
    if think_match:
        think = think_match.group(1).strip()
    if "<silent>" in raw:
        return "silent", "", think
    response_match = _CONTROL_RE.search(raw)
    if response_match:
        response = response_match.group(1).strip()
        if response.upper() == "WAIT":
            return "silent", "", think
        return "response", response, think
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    cleaned = cleaned.replace("<|im_end|>", "").strip()
    return ("response", cleaned, think) if cleaned else ("unknown", "", think)


@dataclass
class _PendingQuery:
    request: QueryRequest
    query_id: str
    dispatch_perf_ns: int


@dataclass
class _PendingObservation:
    observation: Observation
    arrival_perf_ns: int


class ThinkStreamAdapter:
    """In-process ThinkStream adapter loaded through ``module:object``."""

    capabilities = AdapterCapabilities(
        evidence_delivery="decoded_frames",
        state_lifetime="persistent",
        response_mode="autonomous",
        qa_query_timing="before_observation_deferred",
        # The official Proactive track is a wall-clock experiment.  ThinkStream
        # receives the same 1 FPS Core observations, while its two-frame
        # buffering only changes model-call cadence.
        pacing="wall_clock",
        deployment="in_process",
        telemetry=True,
    )

    def __init__(
        self,
        *,
        model_id: str,
        model_type: str = "qwen2.5vl",
        frames_per_chunk: int = 2,
        max_len: int = 24576,
        max_new_tokens: int = 30,
        max_think_tokens: int = 20,
        min_pixels: int = 100352,
        max_pixels: int = 150528,
        temperature: float = 0.2,
        device: str = "cuda:0",
        thinkstream_root: str | None = None,
    ):
        if frames_per_chunk < 1:
            raise ValueError("frames_per_chunk must be positive")
        self.model_id = model_id
        self.model_type = model_type
        self.frames_per_chunk = frames_per_chunk
        self.max_len = max_len
        self.max_new_tokens = max_new_tokens
        self.max_think_tokens = max_think_tokens
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        self.temperature = temperature
        self.device = device
        self.thinkstream_root = thinkstream_root
        self._runtime: dict[str, Any] | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "adapter_name": "thinkstream",
            "adapter_version": "osb-contract-v4-telemetry-v2-response-episodes-v4",
            "protocol": {
                "contract": "osb-contract-v4",
                "telemetry": "osb-evaluation-telemetry-v2",
                "scorer": "osb-scoring-v5",
                "proactive_track": "native_streaming_autonomous_wall_clock",
            },
            "model": {"identity": self.model_id, "model_type": self.model_type},
            "native_stream": {
                "frames_per_inference_chunk": self.frames_per_chunk,
                "core_delivery_fps": 1.0,
                "model_call_rate_hz_at_core_1fps": 1.0 / self.frames_per_chunk,
                "persistent_engine": "StreamingWindowInferenceEngine",
            },
            "generation": {
                "max_len": self.max_len,
                "max_new_tokens": self.max_new_tokens,
                "max_think_tokens": self.max_think_tokens,
                "temperature": self.temperature,
            },
            "visual_preprocessing": {
                "min_pixels": self.min_pixels,
                "max_pixels": self.max_pixels,
            },
            "runtime": {"device": self.device, "thinkstream_root": self.thinkstream_root},
            "failure_policy": {
                "cuda_fatal_error": "abort_run_after_checkpoint",
                "recoverable_record_error": "persist_failed_record_and_continue",
            },
            "upstream": {
                "thinkstream_root": self.thinkstream_root,
                "thinkstream_revision": _git_revision(self.thinkstream_root),
                "official_eval_defaults": {
                    "max_len": 24576,
                    "source": "thinkstream/eval/eval_common.py",
                },
                "osb_alignment": {
                    "core_stream_fps": 1.0,
                    "frames_per_chunk": self.frames_per_chunk,
                    "max_len_matches_official_default": self.max_len == 24576,
                },
            },
            "response_assembly": {
                "schema": "response-episode-v1",
                "proactive_text_mode": "delta",
                "identity": "session_episode",
                "finalization": "wait_or_record_end",
            },
            "prompting": {
                "qa_user_content": "core_byte_identical",
                "qa_serialization": "processor.apply_chat_template_mechanical_roles_controls",
                "qa_decoding": "full_vocabulary_native_control_core_actual_option_parser",
                "proactive_instruction": "record_context_raw_once_at_instruction_boundary",
                "native_system_prompt": {
                    "identity": "thinkstream.data.stream_data_processor:SYSTEM_PROMPT",
                    "content_recorded": True,
                },
            },
            "telemetry": {
                "schema": "osb-evaluation-telemetry-v2",
                "raw_provider_output": True,
                "generated_token_ids": True,
                "prompt_hash": "sha256",
            },
        }

    def _load_runtime(self) -> dict[str, Any]:
        if self._runtime is not None:
            return self._runtime
        if self.thinkstream_root:
            import sys

            if self.thinkstream_root not in sys.path:
                sys.path.insert(0, self.thinkstream_root)
        try:
            torch = importlib.import_module("torch")
            transformers = importlib.import_module("transformers")
            model_mod = importlib.import_module("thinkstream.model")
            inference = importlib.import_module("thinkstream.model.inference")
            data = importlib.import_module("thinkstream.data.stream_data_processor")
            processor = transformers.AutoProcessor.from_pretrained(self.model_id)
            if hasattr(processor, "video_processor"):
                processor.video_processor.min_pixels = self.min_pixels
                processor.video_processor.max_pixels = self.max_pixels
            model_cls = model_mod.MODEL_CLS[self.model_type]
            model = model_cls.from_pretrained(
                self.model_id,
                torch_dtype=torch.bfloat16,
                attn_implementation="flash_attention_2",
                device_map=self.device,
            )
            model.config.text_config._attn_implementation = "flash_attention_2_infer"
            model.eval()
            text_config = model.config.text_config if self.model_type == "qwen3vl" else model.config
            video_token_id = processor.tokenizer.convert_tokens_to_ids(["<|video_pad|>"])[0]
            engine = inference.StreamingWindowInferenceEngine(
                model,
                batch_size=1,
                max_len=self.max_len,
                num_hidden_layers=text_config.num_hidden_layers,
                num_key_value_heads=text_config.num_key_value_heads,
                head_dim=text_config.hidden_size // text_config.num_attention_heads,
                vocab_size=text_config.vocab_size,
                pad_token_id=model.generation_config.pad_token_id,
                eos_token_ids=model.generation_config.eos_token_id,
                video_token_id=video_token_id,
                video_flex_window_size=getattr(
                    model.config, "video_flex_window_size", model_mod.DEFAULT_VIDEO_FLEX_WINDOW_SIZE
                ),
                device=self.device,
            )
            token_ids = processor.tokenizer.convert_tokens_to_ids(
                ["</think>", "<silent>", "<response>", "<|im_end|>"]
            )
        except Exception as exc:
            _raise_fatal_cuda_error(exc)
            raise
        self._runtime = {
            "torch": torch,
            "processor": processor,
            "engine": engine,
            "inference": inference,
            "data": data,
            "token_ids": token_ids,
            "video_token_id": video_token_id,
        }
        return self._runtime

    @staticmethod
    def _validate_observation(observation: Observation) -> np.ndarray:
        frame = np.asarray(observation.rgb)
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError("ThinkStream expects Core RGB uint8 HxWx3 observations")
        return frame

    def open(self, context: RecordContext) -> "ThinkStreamSession":
        return ThinkStreamSession(self, context)


class ThinkStreamSession:
    def __init__(self, adapter: ThinkStreamAdapter, context: RecordContext):
        self.adapter = adapter
        self.context = context
        self.pending: list[_PendingObservation] = []
        self.pending_query: _PendingQuery | None = None
        self.active_query: QueryRequest | None = None
        self.active_query_telemetry: _PendingQuery | None = None
        self.instruction_injected = False
        self.instruction_query_index = 0
        self.chunk_index = 0
        self.query_index = 0
        # Response identity and ordering are record-local.  ``chunk_index``
        # remains model-call telemetry only: one logical answer may span many
        # model chunks.
        self.sequence_id = 0
        self.response_episode_index = 0
        self.active_response_id: str | None = None
        self.pending_response_event: ModelEvent | None = None
        self.closed = False
        self._reset_engine()

    def _reset_engine(self) -> None:
        runtime = self.adapter._load_runtime()
        # ThinkStream replaces window bookkeeping tensors during inference;
        # reset them inside InferenceMode so PyTorch permits the in-place clear
        # before the next record session.
        try:
            with runtime["torch"].inference_mode():
                runtime["engine"].reset()
        except Exception as exc:
            _raise_fatal_cuda_error(exc)
            raise

    def _messages(self, query: QueryRequest | None) -> list[dict[str, Any]]:
        data = self.adapter._load_runtime()["data"]
        content: list[dict[str, Any]] = [{"type": "video"}]
        if query is not None:
            # Keep Core-owned benchmark text byte-identical. Any required
            # separators are added by the chat template, outside this field.
            content.append({"type": "text", "text": query.text})
        if self.chunk_index == 0:
            messages: list[dict[str, Any]] = [{"role": "system", "content": data.SYSTEM_PROMPT}]
        else:
            messages = []
        messages.append({"role": "user", "content": content})
        return messages

    def _prompt_metadata(self, query: QueryRequest | None, rendered_prompt: str) -> dict[str, Any]:
        """Capture prompt provenance without changing benchmark-owned content."""

        data = self.adapter._load_runtime()["data"]
        system_prompt = str(getattr(data, "SYSTEM_PROMPT", ""))
        return {
            "query_kind": query.kind if query is not None else None,
            "benchmark_user_content": query.text if query is not None else None,
            "benchmark_user_content_sha256": (
                hashlib.sha256(query.text.encode("utf-8")).hexdigest()
                if query is not None
                else None
            ),
            "system_prompt_identity": "thinkstream.data.stream_data_processor:SYSTEM_PROMPT",
            "system_prompt": system_prompt,
            "serialization_method": "processor.apply_chat_template",
            "rendered_prompt_sha256": hashlib.sha256(
                rendered_prompt.encode("utf-8")
            ).hexdigest(),
        }

    @staticmethod
    def _ids_from_tensor(value: Any) -> list[int]:
        ids = value.detach().cpu().tolist()
        if ids and isinstance(ids[0], list):
            if len(ids) != 1:
                raise ValueError("ThinkStream telemetry expects batch size one")
            ids = ids[0]
        return [int(item) for item in ids]

    @staticmethod
    def _gpu_memory_snapshot(torch: Any, device: str) -> dict[str, Any]:
        """Return directly observed allocator values, or explicit unavailability."""

        cuda = getattr(torch, "cuda", None)
        try:
            if cuda is None or not cuda.is_available():
                raise RuntimeError("CUDA allocator is unavailable")
            return {
                "device": str(device),
                "allocated_bytes": int(cuda.memory_allocated(device)),
                "reserved_bytes": int(cuda.memory_reserved(device)),
                "allocator_peak_allocated_bytes": int(cuda.max_memory_allocated(device)),
                "backend": "torch.cuda",
                "available": True,
                # The allocator peak is a process-lifetime value unless an
                # external run monitor owns/reset its sampling interval.
                "canonical_run_peak": False,
            }
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            _raise_fatal_cuda_error(exc)
            return {
                "device": str(device),
                "allocated_bytes": None,
                "reserved_bytes": None,
                "allocator_peak_allocated_bytes": None,
                "backend": "torch.cuda" if cuda is not None else None,
                "available": False,
                "canonical_run_peak": False,
                "unavailable_reason": str(exc),
            }

    @staticmethod
    def _resource_telemetry(
        gpu_before: dict[str, Any], gpu_after: dict[str, Any]
    ) -> dict[str, Any]:
        """Expose allocator snapshots through the Core resource contract.

        The adapter runs in the evaluation process and has no external sampler
        proving exclusive device ownership. Values are therefore directly
        observed but explicitly marked as non-canonical for isolated peak
        attribution.
        """

        if not gpu_before.get("available") or not gpu_after.get("available"):
            return {
                "backend": "torch.cuda",
                "sample_interval_ms": None,
                "attribution_ok": False,
                "devices": [],
                "unavailable_reason": gpu_after.get("unavailable_reason")
                or gpu_before.get("unavailable_reason"),
            }
        baseline = gpu_before.get("allocated_bytes")
        candidates = [
            gpu_before.get("allocator_peak_allocated_bytes"),
            gpu_after.get("allocator_peak_allocated_bytes"),
            gpu_after.get("allocated_bytes"),
        ]
        peaks = [int(value) for value in candidates if isinstance(value, int)]
        peak = max(peaks) if peaks else None
        increment = peak - int(baseline) if isinstance(baseline, int) and peak is not None else None
        return {
            "backend": "torch.cuda",
            "sample_interval_ms": None,
            "attribution_ok": False,
            "attribution_reason": "in-process allocator snapshot; no exclusive-device monitor",
            "devices": [
                {
                    "device_id": str(gpu_after.get("device")),
                    "baseline_bytes": baseline,
                    "peak_bytes": peak,
                    "peak_increment_bytes": increment,
                    "peak_minus_baseline_bytes": increment,
                    "canonical_run_peak": False,
                }
            ],
        }

    def _next_sequence_id(self) -> int:
        sequence_id = self.sequence_id
        self.sequence_id += 1
        return sequence_id

    def _next_response_id(self) -> str:
        response_id = f"episode-{self.response_episode_index}"
        self.response_episode_index += 1
        return response_id

    def _flush_pending_response(self, *, is_final: bool) -> list[ModelEvent]:
        event = self.pending_response_event
        if event is None:
            return []
        event.is_final = is_final
        self.pending_response_event = None
        if is_final:
            self.active_response_id = None
        return [event]

    def _normalize_proactive_event(self, event: ModelEvent) -> list[ModelEvent]:
        """Attach response-episode fields while preserving raw chunk output.

        ThinkStream returns one completed generation per model chunk, but a
        response can continue over multiple chunks.  Keep the first fragment
        pending until the next chunk so a following ``WAIT`` can mark the last
        fragment as final without inventing a boundary from ``chunk_index``.
        """

        if self.context.task is not TaskName.PROACTIVE:
            return [event]

        event.sequence_id = self._next_sequence_id()
        event.event_id = f"event-{event.sequence_id}"
        if event.kind is EventKind.ANSWER:
            if self.active_response_id is None:
                self.active_response_id = self._next_response_id()
            event.response_id = self.active_response_id
            event.text_mode = "delta"
            event.response_decision = "response"
            event.is_final = False
            previous = self.pending_response_event
            self.pending_response_event = event
            return [previous] if previous is not None else []

        if event.kind is EventKind.WAIT:
            event.text = "WAIT"
            event.response_id = None
            event.text_mode = "complete"
            event.response_decision = "silent"
            event.is_final = None
            return self._flush_pending_response(is_final=True) + [event]

        # A generation failure closes a response episode before the failure is
        # persisted.  The raw failure telemetry remains attached to ``event``.
        event.response_id = None
        event.text_mode = "complete"
        event.response_decision = None
        event.is_final = None
        return self._flush_pending_response(is_final=True) + [event]

    def _run_chunk(
        self,
        pending_observations: list[_PendingObservation],
        pending_query: _PendingQuery | None,
    ) -> ModelEvent:
        runtime = self.adapter._load_runtime()
        torch = runtime["torch"]
        processor = runtime["processor"]
        engine = runtime["engine"]
        inference = runtime["inference"]
        data = runtime["data"]
        observations = [item.observation for item in pending_observations]
        visible_until = observations[-1].timestamp_s
        if any(item.timestamp_s > visible_until for item in observations):
            raise ValueError("future observation passed to ThinkStream chunk")
        call_started = time.perf_counter_ns()
        effective_query = pending_query
        instruction_time_s = getattr(self.context.record, "instruction_time_s", None)
        # Autonomous Proactive receives the raw benchmark instruction exactly
        # once, at the first legal model call whose prefix reaches the
        # instruction boundary. Later chunks remain observation-only calls.
        if (
            self.context.task is TaskName.PROACTIVE
            and pending_query is None
            and not self.instruction_injected
            and isinstance(instruction_time_s, (int, float))
            and visible_until >= float(instruction_time_s) - 1e-9
        ):
            instruction = str(getattr(self.context.record, "instruction", ""))
            effective_query = _PendingQuery(
                request=QueryRequest(
                    kind="proactive",
                    logical_time_s=float(instruction_time_s),
                    text=instruction,
                ),
                query_id=f"instruction-{self.instruction_query_index}",
                dispatch_perf_ns=call_started,
            )
            self.instruction_query_index += 1
            self.instruction_injected = True
        # Core observations are RGB HWC. Qwen/ThinkStream video processors
        # consume RGB TCHW tensors.
        frame_tensors = [
            torch.from_numpy(self.adapter._validate_observation(item)).permute(2, 0, 1)
            for item in observations
        ]
        shapes = {tuple(frame.shape) for frame in frame_tensors}
        frames = torch.stack(frame_tensors) if len(shapes) == 1 else frame_tensors
        query = effective_query.request if effective_query else None
        text_prompt = processor.apply_chat_template(
            self._messages(query),
            tokenize=False,
            add_generation_prompt=True,
            **({"chat_template": data.QWEN_TEMPLATE_WO_SYSTEM} if self.chunk_index else {}),
        )
        prompt_metadata = self._prompt_metadata(query, text_prompt)
        inputs = processor(
            text=[text_prompt],
            videos=[frames],
            return_tensors="pt",
            # Core owns the evidence rate. ThinkStream's chunk size controls
            # model-call cadence and must not change the Core input FPS.
            fps=[self.context.config.stream_fps],
            min_pixels=self.adapter.min_pixels,
            max_pixels=self.adapter.max_pixels,
        )
        inputs["video_chunk_size"] = float(
            max(1.0, len(observations) / self.context.config.stream_fps)
        )
        inputs["position_ids"] = data.compute_position_ids(
            inputs, processor, self.adapter.model_type
        )
        # ``compute_position_ids`` consumes ``video_chunk_size`` but the
        # processor may leave this helper-only field in its mapping. The
        # official ThinkStream loop removes it before calling engine.generate.
        inputs.pop("second_per_grid_ts", None)
        actual_input_ids = self._ids_from_tensor(inputs["input_ids"])
        video_token_id = int(runtime["video_token_id"])
        actual_input_text_ids = [
            token_id for token_id in actual_input_ids if token_id != video_token_id
        ]
        inputs = inputs.to(self.adapter.device)
        think_end, silent, response, eos = runtime["token_ids"]
        active_query = query or self.active_query
        # ThinkStream's sampler uses ``is_query_window=False`` as an explicit
        # instruction to force ``</think> -> <silent>``.  That is correct for
        # pre-instruction history, but it is not correct for autonomous
        # observation chunks after the one benchmark instruction: those chunks
        # must let the model choose its native <response>/<silent> decision.
        response_decision_window = effective_query is not None or (
            self.context.task is TaskName.PROACTIVE and self.instruction_injected
        )
        sample_kwargs = {
            "think_end_token_id": think_end,
            "max_think_tokens": self.adapter.max_think_tokens,
            "eos_token_id": eos,
            "silent_token_id": silent,
            "response_token_id": response,
            "restricted_token_ids": None,
            "is_query_window": response_decision_window,
            "allow_deferral": self.context.task.value == "proactive",
        }
        if active_query is not None and self.context.task.value == "qa":
            # Keep the model-native control-token state machine, but do not
            # constrain QA to a benchmark-specific A-D vocabulary.  V1 has
            # records with E/F options, and the Core's actual-option parser is
            # the authority for deciding whether the generated label is valid.
            # ThinkStream's restricted sampler still emits exactly one token
            # after <response> when ``allow_deferral`` is false.
            vocab_size = getattr(processor.tokenizer, "vocab_size", None)
            if not isinstance(vocab_size, int) or vocab_size <= 0:
                raise ValueError("ThinkStream tokenizer must expose a positive vocab_size")
            sample_kwargs["restricted_token_ids"] = list(range(vocab_size))
            sample_kwargs["allow_deferral"] = False
        # ``active_query`` remains in effect for later autonomous chunks, but
        # query timing belongs only to the first chunk that actually consumes
        # the queued request. Reusing the same dispatch timestamp on every
        # later chunk would inflate the TTFT population for Proactive runs.
        telemetry_query = effective_query
        call_id = f"chunk-{self.chunk_index}"
        gpu_before = self._gpu_memory_snapshot(torch, self.adapter.device)
        first_token_perf_ns: int | None = None
        if self.context.task.value == "qa":
            sample_fn = inference.think_budget_sample_restricted
            sample_kwargs["eos_token_id"] = eos
            sample_kwargs["silent_token_id"] = silent
            sample_kwargs["response_token_id"] = response
            sample_kwargs["restricted_token_ids"] = sample_kwargs.get("restricted_token_ids") or []
        else:
            # Proactive answers are open-ended, but still need ThinkStream's
            # control-token state machine. Passing the full vocabulary as the
            # response restriction preserves open-ended text while enforcing
            # ``</think> -> <silent>/<response> -> text -> eos``.
            sample_fn = inference.think_budget_sample_restricted
            sample_kwargs = {
                "think_end_token_id": think_end,
                "max_think_tokens": self.adapter.max_think_tokens,
                "eos_token_id": eos,
                "silent_token_id": silent,
                "response_token_id": response,
                "restricted_token_ids": list(range(int(runtime["processor"].tokenizer.vocab_size))),
                "is_query_window": response_decision_window,
                "allow_deferral": True,
            }

        def measured_sample(**kwargs: Any) -> Any:
            nonlocal first_token_perf_ns
            token = sample_fn(**kwargs)
            if first_token_perf_ns is None:
                if getattr(torch, "cuda", None) is not None and torch.cuda.is_available():
                    torch.cuda.synchronize(self.adapter.device)
                first_token_perf_ns = time.perf_counter_ns()
            return token

        try:
            outputs = engine.generate(
                **inputs,
                num_generations=1,
                max_new_tokens=self.adapter.max_new_tokens,
                temperature=self.adapter.temperature,
                sample=measured_sample,
                sample_kwargs=sample_kwargs,
            )
            # ``generate`` is a blocking Python API, but synchronize explicitly
            # before claiming that its state update and output are committed.
            if getattr(torch, "cuda", None) is not None and torch.cuda.is_available():
                torch.cuda.synchronize(self.adapter.device)
            finished = time.perf_counter_ns()
            generated_token_ids = self._ids_from_tensor(outputs[0])
            raw = processor.batch_decode([outputs[0]], skip_special_tokens=False)[0]
        except Exception as exc:
            if _is_cuda_fatal_error(exc):
                raise FatalEvaluationError(
                    "ThinkStream model process became unusable after a fatal CUDA error: "
                    f"{exc}"
                ) from exc
            failed = time.perf_counter_ns()
            return ModelEvent(
                kind=EventKind.FAILURE,
                logical_time_s=visible_until,
                status="failed",
                failed_reason=str(exc),
                raw_output=None,
                telemetry=self._telemetry(
                    pending_observations=pending_observations,
                    pending_query=telemetry_query,
                    call_id=call_id,
                    call_started=call_started,
                    call_finished=failed,
                    first_token_perf_ns=first_token_perf_ns,
                    commit_perf_ns=None,
                    actual_input_ids=actual_input_ids,
                    actual_input_text_ids=actual_input_text_ids,
                    generated_token_ids=None,
                    gpu_before=gpu_before,
                    gpu_after=self._gpu_memory_snapshot(torch, self.adapter.device),
                    response_decision=None,
                    failure_stage="model_generation",
                    failure=exc,
                    prompt_metadata=prompt_metadata,
                ),
            )
        decision, answer, think = parse_thinkstream_output(raw)
        kind = (
            EventKind.ANSWER
            if decision == "response"
            else EventKind.WAIT
            if decision == "silent"
            else EventKind.FAILURE
        )
        event = ModelEvent(
            kind=kind,
            logical_time_s=visible_until,
            text=answer if kind == EventKind.ANSWER else "WAIT" if kind == EventKind.WAIT else "",
            status="ok" if kind != EventKind.FAILURE else "failed",
            failed_reason=None if kind != EventKind.FAILURE else "unparseable ThinkStream output",
            raw_output={
                "provider_text": raw,
                # Keep the historical key for consumers of v8 artifacts.
                "text": raw,
                "generated_token_ids": generated_token_ids,
                "think": think,
                "prompt_metadata": prompt_metadata,
            },
            telemetry=self._telemetry(
                pending_observations=pending_observations,
                pending_query=telemetry_query,
                call_id=call_id,
                call_started=call_started,
                call_finished=finished,
                first_token_perf_ns=first_token_perf_ns,
                commit_perf_ns=finished,
                actual_input_ids=actual_input_ids,
                actual_input_text_ids=actual_input_text_ids,
                generated_token_ids=generated_token_ids,
                gpu_before=gpu_before,
                gpu_after=self._gpu_memory_snapshot(torch, self.adapter.device),
                response_decision=decision,
                failure_stage="output_parsing" if kind == EventKind.FAILURE else None,
                failure=(
                    ValueError("unparseable ThinkStream output")
                    if kind == EventKind.FAILURE
                    else None
                ),
                prompt_metadata=prompt_metadata,
            ),
        )
        # Provider output produced during autonomous prefill is retained as
        # non-prediction telemetry. It must not open or close a scored episode.
        if (
            self.context.task is TaskName.PROACTIVE
            and isinstance(instruction_time_s, (int, float))
            and visible_until < float(instruction_time_s) - 1e-9
        ):
            event.telemetry.update(
                {
                    "provider_output_suppressed": True,
                    "suppression_reason": "before_instruction_boundary",
                    "eligible_for_scoring": False,
                }
            )
            event.kind = EventKind.TELEMETRY
            event.text = ""
            event.response_decision = None
        return event

    def _telemetry(
        self,
        *,
        pending_observations: list[_PendingObservation],
        pending_query: _PendingQuery | None,
        call_id: str,
        call_started: int,
        call_finished: int,
        first_token_perf_ns: int | None,
        commit_perf_ns: int | None,
        actual_input_ids: list[int],
        actual_input_text_ids: list[int],
        generated_token_ids: list[int] | None,
        gpu_before: dict[str, Any],
        gpu_after: dict[str, Any],
        response_decision: str | None,
        failure_stage: str | None,
        failure: Exception | None,
        prompt_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        frames = []
        for item in pending_observations:
            observation = item.observation
            height, width = np.asarray(observation.rgb).shape[:2]
            frames.append(
                {
                    "observation_id": observation.observation_id or f"frame-{observation.frame_index}",
                    "frame_index": observation.frame_index,
                    "video_time_s": observation.timestamp_s,
                    "scheduled_arrival_perf_ns": observation.scheduled_arrival_perf_ns,
                    "arrival_perf_ns": item.arrival_perf_ns,
                    "commit_perf_ns": commit_perf_ns,
                    "submitted_occurrences": 1,
                    "submitted_width": int(width),
                    "submitted_height": int(height),
                    "submitted_pixels": int(width * height),
                }
            )
        query_id = pending_query.query_id if pending_query else None
        dispatch = pending_query.dispatch_perf_ns if pending_query else None
        # Completion is a model-call boundary for every generated chunk.  The
        # nested query telemetry below remains query-only, while autonomous
        # Proactive chunks still expose completion timing for workload/reporting.
        completion = call_finished if generated_token_ids is not None else None
        frame_arrivals = [item.arrival_perf_ns for item in pending_observations]
        if self.context.task is TaskName.QA:
            if dispatch is None:
                qa_phase = "history"
            elif any(value < dispatch for value in frame_arrivals) and any(
                value >= dispatch for value in frame_arrivals
            ):
                qa_phase = "mixed_boundary"
            else:
                qa_phase = "query"
        else:
            qa_phase = None
        query_telemetry = None
        if pending_query is not None:
            query_telemetry = {
                "query_id": query_id,
                "query_kind": pending_query.request.kind,
                "logical_time_s": pending_query.request.logical_time_s,
                "dispatch_perf_ns": dispatch,
                "first_token_perf_ns": first_token_perf_ns,
                "completion_perf_ns": completion,
                "ttft_ms": (
                    (first_token_perf_ns - dispatch) / 1e6
                    if first_token_perf_ns is not None and dispatch is not None
                    else None
                ),
                "response_total_ms": (
                    (completion - dispatch) / 1e6
                    if completion is not None and dispatch is not None
                    else None
                ),
                "input_text_tokens": len(actual_input_text_ids),
                "output_tokens": len(generated_token_ids)
                if generated_token_ids is not None
                else None,
            }
        failure_type = type(failure).__name__ if failure is not None else None
        resource_telemetry = self._resource_telemetry(gpu_before, gpu_after)
        model_call = {
            "call_id": call_id,
            "stage": (
                "qa_history_processing"
                if qa_phase == "history"
                else "qa_mixed_boundary"
                if qa_phase == "mixed_boundary"
                else "qa_query_answer"
                if qa_phase == "query"
                else "stream_chunk_generation"
            ),
            "start_perf_ns": call_started,
            "end_perf_ns": call_finished,
            "first_token_perf_ns": first_token_perf_ns,
            "completion_perf_ns": completion,
            "submitted_frame_occurrences": len(frames),
            "submitted_pixels": sum(item["submitted_pixels"] for item in frames),
            "input_text_tokens": len(actual_input_text_ids),
            "output_tokens": len(generated_token_ids) if generated_token_ids is not None else None,
            "num_cached_tokens": None,
        }
        return {
            "schema_version": "osb-evaluation-telemetry-v2",
            "chunk_idx": self.chunk_index,
            "visible_until": pending_observations[-1].observation.timestamp_s,
            "frame_count": len(frames),
            "frame_telemetry": frames,
            "adapter_submitted_frame_count": len(frames),
            "adapter_unique_submitted_frame_count": len(
                {item["observation_id"] for item in frames}
            ),
            "duplicate_frame_count": len(frames) - len({item["observation_id"] for item in frames}),
            "adapter_submitted_pixel_count": sum(item["submitted_pixels"] for item in frames),
            "arrival_perf_ns": min(item["arrival_perf_ns"] for item in frames),
            "commit_perf_ns": commit_perf_ns,
            "query_id": query_id,
            "query_telemetry": query_telemetry,
            # Core/scoring keeps the historical query boundary fields at the
            # event top level.  Keep them in addition to the structured nested
            # object so an answer generated by the observation that consumes a
            # queued QA query is selected as the QA prediction.
            "query_dispatch_perf_ns": dispatch,
            # Autonomous Proactive chunks have no query telemetry, but their
            # first-token boundary is still required for wall-clock scoring.
            "first_token_perf_ns": first_token_perf_ns,
            "response_completion_perf_ns": completion,
            "response_total_ms": query_telemetry.get("response_total_ms")
            if query_telemetry is not None
            else None,
            "model_call": model_call,
            # The list form is the canonical cross-adapter aggregation
            # contract. Keep the singular compatibility field above for older
            # Bundle readers.
            "model_calls": [model_call],
            "model_call_count": 1,
            "inference_wall_time_s": (call_finished - call_started) / 1e9,
            "actual_input_ids": actual_input_ids,
            "actual_input_token_count": len(actual_input_ids),
            "actual_input_text_ids": actual_input_text_ids,
            "input_text_tokens": len(actual_input_text_ids),
            "generated_token_ids": generated_token_ids,
            "output_tokens": len(generated_token_ids) if generated_token_ids is not None else None,
            # Compatibility name retained for the existing tiny bundles.
            "output_token_count": len(generated_token_ids)
            if generated_token_ids is not None
            else None,
            "response_decision": response_decision,
            "qa_phase": qa_phase,
            "prompt_metadata": prompt_metadata,
            "gpu_memory": {"before": gpu_before, "after": gpu_after},
            "resource_telemetry": resource_telemetry,
            "failure_stage": failure_stage,
            "failure_type": failure_type,
            "failure_reason": str(failure) if failure is not None else None,
            "timed_out": isinstance(failure, TimeoutError),
            "retry_count": 0,
            "telemetry_coverage": {
                "frames": "complete" if commit_perf_ns is not None else "missing_commit",
                "input_text_tokens": "complete",
                "output_tokens": "complete" if generated_token_ids is not None else "missing",
                "model_calls": "complete",
                "query_timing": (
                    "complete"
                    if pending_query is not None and first_token_perf_ns is not None
                    else "partial_no_first_token"
                    if pending_query is not None
                    else "not_applicable"
                ),
                "ttft": (
                    "complete"
                    if pending_query is not None and first_token_perf_ns is not None
                    else "missing"
                    if pending_query is not None
                    else "not_applicable"
                ),
                "gpu_memory": "allocator_snapshot_only"
                if gpu_before["available"]
                else "unavailable",
            },
        }

    def observe(self, observation: Observation) -> list[ModelEvent]:
        if self.closed:
            raise RuntimeError("ThinkStream session is closed")
        self.pending.append(
            _PendingObservation(observation=observation, arrival_perf_ns=time.perf_counter_ns())
        )
        boundary_reached = False
        if self.context.task is TaskName.PROACTIVE:
            instruction_time_s = getattr(self.context.record, "instruction_time_s", None)
            boundary_reached = (
                not self.instruction_injected
                and isinstance(instruction_time_s, (int, float))
                and observation.timestamp_s >= float(instruction_time_s) - 1e-9
            )
        elif self.context.task is TaskName.QA and self.pending_query is not None:
            boundary_reached = observation.timestamp_s >= self.pending_query.request.logical_time_s - 1e-9
        if len(self.pending) < self.adapter.frames_per_chunk and not boundary_reached:
            return []
        pending_query = self.pending_query
        self.pending_query = None
        if pending_query is not None:
            self.active_query = pending_query.request
            self.active_query_telemetry = pending_query
        observations, self.pending = self.pending, []
        try:
            event = self._run_chunk(observations, pending_query)
        except Exception as exc:
            _raise_fatal_cuda_error(exc)
            raise
        self.chunk_index += 1
        return self._normalize_proactive_event(event)

    def query(self, request: QueryRequest) -> list[ModelEvent]:
        if self.closed:
            raise RuntimeError("ThinkStream session is closed")
        self.pending_query = _PendingQuery(
            request=request,
            query_id=f"query-{self.query_index}",
            dispatch_perf_ns=time.perf_counter_ns(),
        )
        self.query_index += 1
        self.active_query = request
        self.active_query_telemetry = self.pending_query
        return []

    def close(self) -> list[ModelEvent]:
        if self.closed:
            return []
        self.closed = True
        events: list[ModelEvent] = []
        if not self.pending:
            return self._flush_pending_response(is_final=True)
        pending_query = self.pending_query
        observations = self.pending
        self.pending = []
        self.pending_query = None
        try:
            event = self._run_chunk(observations, pending_query)
        except Exception as exc:
            _raise_fatal_cuda_error(exc)
            raise
        self.chunk_index += 1
        events.extend(self._normalize_proactive_event(event))
        events.extend(self._flush_pending_response(is_final=True))
        return events
