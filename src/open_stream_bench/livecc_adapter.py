"""LiveCC adapter for the Open Stream Bench RGB observation contract.

The adapter intentionally does not call LiveCC's file-replay helper.  Core
decodes the legal evidence and this module converts those RGB observations into
the in-memory video tensors expected by the LiveCC/Qwen2-VL processor.

LiveCC dependencies are imported lazily so the public OSB package and its
deterministic tests do not require CUDA, model weights, or the LiveCC checkout.
"""

from __future__ import annotations

import atexit
import hashlib
import importlib
import math
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
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


def _is_cuda_fatal_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "device-side assert",
            "device side assert",
            "illegal memory access",
            "cuda context",
            "context is corrupted",
            "cuda error: initialization error",
            "cuda error: unknown error",
        )
    )


def _raise_fatal_cuda_error(exc: BaseException) -> None:
    if _is_cuda_fatal_error(exc):
        raise FatalEvaluationError(
            "LiveCC model process became unusable after a fatal CUDA error: "
            f"{exc}"
        ) from exc


def _ids_from_value(value: Any) -> list[int]:
    if value is None:
        return []
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    while isinstance(value, list) and value and isinstance(value[0], list):
        if len(value) != 1:
            raise ValueError("LiveCC adapter expects batch size one")
        value = value[0]
    return [int(item) for item in value] if isinstance(value, list) else [int(value)]


def _sync_cuda(torch: Any, device: str) -> None:
    if not str(device).startswith("cuda"):
        return
    cuda = getattr(torch, "cuda", None)
    if cuda is not None and cuda.is_available():
        cuda.synchronize(device)


def _cuda_physical_index(torch: Any, device: str) -> int | None:
    """Resolve a torch CUDA device to its physical NVML index."""

    if not str(device).startswith("cuda"):
        return None
    suffix = str(device).split(":", 1)[1] if ":" in str(device) else None
    try:
        logical_index = int(suffix) if suffix is not None else int(torch.cuda.current_device())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not visible:
        return logical_index
    entries = [item.strip() for item in visible.split(",") if item.strip()]
    if logical_index < 0 or logical_index >= len(entries):
        return None
    try:
        return int(entries[logical_index])
    except ValueError:
        # UUID/MIG visibility cannot be safely converted to an index here.
        return None


class _ProcessGpuMonitor:
    """Sample this evaluation process through NVML while a model is loaded."""

    def __init__(self, torch: Any, device: str, interval_ms: float = 100.0):
        self._torch = torch
        self._device = str(device)
        self._interval_ms = float(interval_ms)
        self._pid = os.getpid()
        self._physical_index = _cuda_physical_index(torch, device)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._nvml: Any | None = None
        self._handle: Any | None = None
        self._uuid: str | None = None
        self._error: str | None = None
        self._latest: dict[str, Any] | None = None
        self._peak_bytes: int | None = None
        self._initialize()

    def _initialize(self) -> None:
        if self._physical_index is None:
            self._error = "CUDA device has no numeric physical NVML index"
            return
        try:
            pynvml = importlib.import_module("pynvml")
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(self._physical_index)
            uuid = pynvml.nvmlDeviceGetUUID(handle)
            if isinstance(uuid, bytes):
                uuid = uuid.decode("ascii", errors="replace")
            self._nvml = pynvml
            self._handle = handle
            self._uuid = str(uuid)
        except Exception as exc:
            self._error = f"NVML process monitor unavailable: {exc}"
            self._nvml = None
            self._handle = None

    def _processes(self) -> list[Any]:
        if self._nvml is None or self._handle is None:
            return []
        for name in (
            "nvmlDeviceGetComputeRunningProcesses_v3",
            "nvmlDeviceGetComputeRunningProcesses_v2",
            "nvmlDeviceGetComputeRunningProcesses",
        ):
            function = getattr(self._nvml, name, None)
            if function is not None:
                try:
                    return list(function(self._handle))
                except Exception as exc:
                    self._error = f"NVML process sampling failed: {exc}"
                    return []
        self._error = "NVML process enumeration API is unavailable"
        return []

    def _sample(self) -> dict[str, Any]:
        if self._nvml is None or self._handle is None:
            return {
                "device": self._device,
                "device_index": self._physical_index,
                "backend": "nvml-process-memory",
                "available": False,
                "attribution_ok": False,
                "canonical_run_peak": False,
                "sample_interval_ms": self._interval_ms,
                "unavailable_reason": self._error or "NVML is unavailable",
            }
        process_rows = self._processes()
        current_bytes: int | None = None
        other_pids: list[int] = []
        for row in process_rows:
            pid = int(getattr(row, "pid", -1))
            value = getattr(row, "usedGpuMemory", None)
            if not isinstance(value, int) or value < 0:
                continue
            if pid == self._pid:
                current_bytes = (current_bytes or 0) + value
            else:
                other_pids.append(pid)
        attribution_ok = current_bytes is not None and not other_pids
        if current_bytes is not None:
            self._peak_bytes = max(self._peak_bytes or current_bytes, current_bytes)
        snapshot = {
            "device": self._device,
            "device_index": self._physical_index,
            "device_uuid": self._uuid,
            "backend": "nvml-process-memory",
            "available": current_bytes is not None,
            "attribution_ok": attribution_ok,
            "canonical_run_peak": attribution_ok,
            "sample_interval_ms": self._interval_ms,
            "process_pid": self._pid,
            "process_used_bytes": current_bytes,
            "process_peak_bytes": self._peak_bytes,
            "other_compute_pids": sorted(set(other_pids)),
        }
        with self._lock:
            self._latest = snapshot
        return snapshot

    def start(self) -> None:
        if self._nvml is None or self._thread is not None:
            return
        self._sample()

        def run() -> None:
            while not self._stop.wait(self._interval_ms / 1000.0):
                self._sample()

        self._thread = threading.Thread(
            target=run,
            name="osb-livecc-gpu-monitor",
            daemon=True,
        )
        self._thread.start()

    def snapshot(self) -> dict[str, Any]:
        return self._sample()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_ms / 1000.0 * 2))
            self._thread = None
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml = None
            self._handle = None


def _gpu_memory_snapshot(
    torch: Any, device: str, monitor: _ProcessGpuMonitor | None = None
) -> dict[str, Any]:
    """Return process-attributed NVML data, with allocator fallback for diagnostics."""

    if monitor is not None:
        snapshot = monitor.snapshot()
        if snapshot.get("available"):
            return snapshot

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


def _resource_telemetry(
    gpu_before: dict[str, Any], gpu_after: dict[str, Any]
) -> dict[str, Any]:
    if (
        gpu_before.get("backend") == "nvml-process-memory"
        and gpu_after.get("backend") == "nvml-process-memory"
    ):
        baseline = gpu_before.get("process_used_bytes")
        candidates = [
            gpu_before.get("process_peak_bytes"),
            gpu_after.get("process_peak_bytes"),
            gpu_after.get("process_used_bytes"),
        ]
        peaks = [int(value) for value in candidates if isinstance(value, int)]
        peak = max(peaks) if peaks else None
        increment = (
            peak - int(baseline)
            if isinstance(baseline, int) and peak is not None
            else None
        )
        attribution_ok = bool(
            gpu_before.get("attribution_ok") and gpu_after.get("attribution_ok")
        )
        return {
            "backend": "nvml-process-memory",
            "sample_interval_ms": gpu_after.get("sample_interval_ms"),
            "attribution_ok": attribution_ok,
            "attribution_reason": (
                None
                if attribution_ok
                else "current process missing or another compute process shares the device"
            ),
            "devices": [
                {
                    "device_id": str(
                        gpu_after.get("device_index", gpu_after.get("device"))
                    ),
                    "device_uuid": gpu_after.get("device_uuid"),
                    "process_pid": gpu_after.get("process_pid"),
                    "other_compute_pids": gpu_after.get("other_compute_pids", []),
                    "baseline_bytes": baseline,
                    "peak_bytes": peak,
                    "peak_increment_bytes": increment,
                    "peak_minus_baseline_bytes": increment,
                    "canonical_run_peak": attribution_ok,
                }
            ],
        }
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
    increment = (
        peak - int(baseline)
        if isinstance(baseline, int) and peak is not None
        else None
    )
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


def _is_silent_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return re.fullmatch(
        r"[\s*_`~:：,，.!！?？\-]*(?:WAIT|wait)[\s*_`~:：,，.!！?？\-]*",
        stripped,
    ) is not None


def _silence_source(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return "empty_output"
    if re.fullmatch(r"(?:\s*\.{1,}|\s*…)+\s*", stripped):
        # LiveCC uses an ellipsis as a provider continuation marker, not a
        # native benchmark silence token. It carries no substantive answer.
        return "provider_empty_continuation"
    if re.fullmatch(
        r"[\s*_`~:：,，.!！?？\-]*(?:WAIT|wait)[\s*_`~:：,，.!！?？\-]*",
        stripped,
    ):
        return "text_wait"
    return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _qwen_downscaled_shape(height: int, width: int, max_pixels: int) -> tuple[int, int]:
    """Return Qwen2-VL-compatible dimensions without upscaling Core frames."""

    if height <= 0 or width <= 0:
        raise ValueError("RGB frame dimensions must be positive")
    if height * width <= max_pixels:
        return height, width
    factor = 28
    beta = math.sqrt((height * width) / max_pixels)
    resized_height = max(factor, math.floor(height / beta / factor) * factor)
    resized_width = max(factor, math.floor(width / beta / factor) * factor)
    while resized_height * resized_width > max_pixels:
        if resized_height >= resized_width:
            resized_height -= factor
        else:
            resized_width -= factor
        if resized_height < factor or resized_width < factor:
            return factor, factor
    return resized_height, resized_width


class _TokenTimestampStreamer:
    """Minimal Transformers streamer that records generated IDs and TTFT."""

    def __init__(self, torch: Any, device: str, prompt_length: int = 0):
        self._torch = torch
        self._device = device
        self._prompt_length = max(0, int(prompt_length))
        self._prompt_seen = False
        self.generated_token_ids: list[int] = []
        self.first_token_perf_ns: int | None = None

    def put(self, value: Any) -> None:
        ids = _ids_from_value(value)
        if not self._prompt_seen and self._prompt_length:
            # Transformers calls streamer.put(input_ids) once before the
            # generated stream. Consume exactly that prompt prefix so the
            # first generated token receives the real timestamp. Supporting a
            # single put containing prompt plus generated IDs also keeps fake
            # runtimes and alternate streamers deterministic.
            self._prompt_seen = True
            if len(ids) <= self._prompt_length:
                return
            ids = ids[self._prompt_length :]
        if not ids:
            return
        self.generated_token_ids.extend(ids)
        if self.first_token_perf_ns is None:
            _sync_cuda(self._torch, self._device)
            self.first_token_perf_ns = time.perf_counter_ns()

    def end(self) -> None:
        return None


@dataclass
class _PendingObservation:
    observation: Observation
    arrival_perf_ns: int


@dataclass
class _PendingQuery:
    request: QueryRequest
    query_id: str
    dispatch_perf_ns: int


@dataclass
class _GenerationResult:
    visible_text: str
    raw_text: str
    generated_token_ids: list[int]
    actual_input_ids: list[int]
    telemetry: dict[str, Any]
    raw_output: dict[str, Any]
    failed_reason: str | None = None


class LiveCCAdapter:
    """In-process LiveCC adapter using Core-decoded RGB observations."""

    PROACTIVE_WAIT_FALLBACK_PROMPT = (
        "You are observing a live video stream frame by frame.\n"
        "Follow the user's instruction.\n"
        "If the available evidence is insufficient, output WAIT.\n"
        "If the evidence is sufficient, output only a concise answer."
    )

    def __init__(
        self,
        *,
        model_id: str | None = None,
        livecc_root: str | None = None,
        device: str = "cuda",
        frames_per_chunk: int = 2,
        min_pixels: int = 100 * 28 * 28,
        max_pixels: int = 384 * 28 * 28,
        max_new_tokens: int = 16,
        qa_max_new_tokens: int = 16,
        context_window_tokens: int = 32768,
        repetition_penalty: float = 1.05,
        temperature: float = 0.2,
        do_sample: bool = True,
        qa_do_sample: bool = False,
        return_attention_mask: bool = False,
        context_prompt: str = "Please describe the video.",
        proactive_system_prompt: str = PROACTIVE_WAIT_FALLBACK_PROMPT,
        gpu_monitor_interval_ms: float = 100.0,
        pacing: str = "logical",
    ):
        if frames_per_chunk < 1:
            raise ValueError("frames_per_chunk must be positive")
        if min_pixels <= 0 or max_pixels <= 0 or min_pixels > max_pixels:
            raise ValueError("LiveCC pixel limits must be positive and ordered")
        if context_window_tokens <= 0:
            raise ValueError("context_window_tokens must be positive")
        if qa_max_new_tokens <= 0 or max_new_tokens <= 0:
            raise ValueError("generation token budgets must be positive")
        if gpu_monitor_interval_ms <= 0:
            raise ValueError("gpu_monitor_interval_ms must be positive")
        self.model_id = model_id or os.environ.get("LIVECC_MODEL_PATH")
        self.livecc_root = livecc_root or os.environ.get("LIVECC_ROOT")
        self.device = device
        self.frames_per_chunk = frames_per_chunk
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        self.max_new_tokens = max_new_tokens
        self.qa_max_new_tokens = qa_max_new_tokens
        self.context_window_tokens = context_window_tokens
        self.repetition_penalty = repetition_penalty
        self.temperature = temperature
        self.do_sample = do_sample
        self.qa_do_sample = qa_do_sample
        self.return_attention_mask = return_attention_mask
        self.context_prompt = context_prompt
        self.proactive_system_prompt = proactive_system_prompt
        self.gpu_monitor_interval_ms = float(gpu_monitor_interval_ms)
        self._runtime: dict[str, Any] | None = None
        self._gpu_monitor: _ProcessGpuMonitor | None = None
        self.capabilities = AdapterCapabilities(
            evidence_delivery="decoded_frames",
            state_lifetime="persistent",
            response_mode="autonomous",
            qa_query_timing="before_observation_deferred",
            pacing=pacing,
            deployment="in_process",
            telemetry=True,
        )

    @property
    def metadata(self) -> dict[str, Any]:
        shared_source = (
            str(Path(self.livecc_root).expanduser() / "demo" / "infer.py")
            if self.livecc_root
            else None
        )
        return {
            "adapter_name": "livecc",
            "adapter_version": "osb-rgb-v1.3",
            "protocol": {
                "contract": "osb-contract-v4",
                "telemetry": "osb-evaluation-telemetry-v2",
                "scorer": "osb-scoring-v6",
                "preflight": "osb-preflight-v4",
                "proactive_track": (
                    "native_streaming_autonomous_wall_clock"
                    if self.capabilities.pacing == "wall_clock"
                    else "native_streaming_autonomous_logical_diagnostic"
                ),
            },
            "model": {"identity": self.model_id, "device": self.device},
            "hardware": {
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "device_attribution": "nvml_process_memory_current_pid_exclusive",
                "gpu_monitor_backend": "nvml-process-memory",
                "gpu_monitor_interval_ms": self.gpu_monitor_interval_ms,
            },
            "prompt_contract": {
                "qa_user_content": "core_byte_identical_user_content",
                "qa_serialization": "mechanical_chat_template_roles_and_control_tokens",
                "qa_native_bootstrap": self.context_prompt,
                "qa_native_bootstrap_sha256": _sha256_text(self.context_prompt),
                "proactive_instruction": "raw_record_instruction_once_at_boundary",
                "system_prompt": {
                    "qa_mode": "native_processor_chat_template",
                    "qa_explicit_message": False,
                    "qa_identity": "Qwen2-VL processor chat template default",
                    "proactive_mode": "contract_fallback",
                    "proactive_explicit_message": True,
                    "proactive_identity": "osb-proactive-wait-fallback-v1",
                    "proactive_content": self.proactive_system_prompt,
                    "proactive_sha256": _sha256_text(self.proactive_system_prompt),
                },
                "native_silence_markers": [],
                "provider_control_markers": ["..."],
                "wait_fallback": "standalone_text_wait",
            },
            "shared_runtime": {
                "source": shared_source,
                "sha256": _sha256_file(Path(shared_source)) if shared_source else None,
                "identity": "LiveCCDemoInfer",
            },
            "native_stream": {
                "evidence_source": "osb_core_decoded_rgb",
                "pacing": self.capabilities.pacing,
                "frames_per_inference_chunk": self.frames_per_chunk,
                "core_delivery_fps": 1.0,
                "model_call_rate_hz_at_core_1fps": 1.0 / self.frames_per_chunk,
                "persistent_state": "past_key_values_and_past_ids",
            },
            "generation": {
                "max_new_tokens": self.max_new_tokens,
                "qa_max_new_tokens": self.qa_max_new_tokens,
                "context_window_tokens": self.context_window_tokens,
                "max_model_len": self.context_window_tokens,
                "repetition_penalty": self.repetition_penalty,
                "temperature": self.temperature,
                "do_sample": self.do_sample,
                "qa_do_sample": self.qa_do_sample,
                "gpu_monitor_interval_ms": self.gpu_monitor_interval_ms,
                "attention_mask_mode": (
                    "explicit" if self.return_attention_mask else "official_disabled"
                ),
            },
            "visual_preprocessing": {
                "min_pixels": self.min_pixels,
                "max_pixels": self.max_pixels,
                "input_contract": "Core RGB uint8 HWC; no file replay",
                "adapter_resize": "qwen2vl_factor_28_max_pixels_downscale_only",
                "context_policy": "adaptive_generation_budget_no_kv_truncation",
            },
            "runtime": {
                "device": self.device,
                "livecc_root": self.livecc_root,
            },
            "failure_policy": {
                "cuda_fatal_error": "abort_run_after_checkpoint",
                "recoverable_record_error": "persist_failed_record_and_continue",
            },
        }

    @staticmethod
    def _validate_observation(observation: Observation) -> np.ndarray:
        frame = np.asarray(observation.rgb)
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError("LiveCC expects Core RGB uint8 HxWx3 observations")
        return np.ascontiguousarray(frame)

    @staticmethod
    def _resize_shape(height: int, width: int, max_pixels: int) -> tuple[int, int]:
        return _qwen_downscaled_shape(height, width, max_pixels)

    def _load_runtime(self) -> dict[str, Any]:
        if self._runtime is not None:
            return self._runtime
        if not self.model_id:
            raise ValueError(
                "LiveCC model_id is required; pass adapter_config.model_id or "
                "set LIVECC_MODEL_PATH"
            )
        try:
            if self.livecc_root:
                root = Path(self.livecc_root).expanduser().resolve()
                candidates = [root, root / "demo", root / "livecc-utils" / "src"]
                for candidate in reversed(candidates):
                    value = str(candidate)
                    if value not in sys.path:
                        sys.path.insert(0, value)
            infer_module = importlib.import_module("demo.infer")
            infer_cls = getattr(infer_module, "LiveCCDemoInfer")
            infer = infer_cls(model_path=self.model_id, device=self.device)
            torch = importlib.import_module("torch")
            processor = infer.processor
            tokenizer = processor.tokenizer
            video_token_id: int | None = None
            try:
                value = tokenizer.convert_tokens_to_ids(["<|video_pad|>"])
                video_token_id = int(value[0] if isinstance(value, list) else value)
            except (AttributeError, IndexError, TypeError, ValueError):
                pass
            video_processor = getattr(processor, "video_processor", None)
            if video_processor is not None:
                if hasattr(video_processor, "min_pixels"):
                    video_processor.min_pixels = self.min_pixels
                if hasattr(video_processor, "max_pixels"):
                    video_processor.max_pixels = self.max_pixels
            gpu_monitor = _ProcessGpuMonitor(
                torch,
                self.device,
                interval_ms=self.gpu_monitor_interval_ms,
            )
            gpu_monitor.start()
            self._gpu_monitor = gpu_monitor
            atexit.register(gpu_monitor.close)
            self._runtime = {
                "torch": torch,
                "infer": infer,
                "model": infer.model,
                "processor": processor,
                "tokenizer": tokenizer,
                "video_token_id": video_token_id,
                "system_prompt_offset": int(getattr(infer, "system_prompt_offset", 0)),
                "gpu_monitor": gpu_monitor,
            }
        except Exception as exc:
            _raise_fatal_cuda_error(exc)
            raise
        return self._runtime

    def open(self, context: RecordContext) -> "LiveCCSession":
        return LiveCCSession(self, context)

    def close(self) -> None:
        if self._gpu_monitor is not None:
            self._gpu_monitor.close()
            self._gpu_monitor = None


class LiveCCSession:
    def __init__(self, adapter: LiveCCAdapter, context: RecordContext):
        self.adapter = adapter
        self.context = context
        self._runtime = adapter._load_runtime()
        self.pending: list[_PendingObservation] = []
        self.pending_query: _PendingQuery | None = None
        self.last_observed_timestamp: float | None = None
        self.message_sent = False
        self.system_prompt_sent = False
        self.proactive_started = context.task is not TaskName.PROACTIVE
        self.query_index = 0
        self.call_index = 0
        self.sequence_id = 0
        self.response_episode_index = 0
        self.closed = False
        self.qa_answered = False
        self.context_overflowed = False
        self.state: dict[str, Any] = {
            "past_ids": None,
            "past_key_values": None,
        }

    def _model_device(self) -> str:
        model = self._runtime["model"]
        return str(getattr(model, "device", self.adapter.device))

    def _frame_tensor(self, observation: Observation) -> Any:
        torch = self._runtime["torch"]
        frame = self.adapter._validate_observation(observation)
        height, width = self.adapter._resize_shape(
            frame.shape[0], frame.shape[1], self.adapter.max_pixels
        )
        if (height, width) != frame.shape[:2]:
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        return torch.from_numpy(frame).permute(2, 0, 1).contiguous()

    def _take_batch(self) -> tuple[list[_PendingObservation], _PendingQuery | None]:
        if self.pending_query is not None and self.context.task is TaskName.QA:
            query_time = self.pending_query.request.logical_time_s
            eligible = [
                item
                for item in self.pending
                if item.observation.timestamp_s <= query_time + 1e-9
            ]
            if eligible and (
                len(eligible) >= self.adapter.frames_per_chunk
                or (
                    self.last_observed_timestamp is not None
                    and self.last_observed_timestamp >= query_time - 1e-9
                )
            ):
                eligible_ids = {id(item) for item in eligible}
                self.pending = [
                    item for item in self.pending if id(item) not in eligible_ids
                ]
                query = self.pending_query
                self.pending_query = None
                return eligible, query
            if (
                not eligible
                and self.last_observed_timestamp is not None
                and self.last_observed_timestamp >= query_time - 1e-9
            ):
                query = self.pending_query
                self.pending_query = None
                return [], query
        if len(self.pending) < self.adapter.frames_per_chunk:
            return [], None
        batch, self.pending = (
            self.pending[: self.adapter.frames_per_chunk],
            self.pending[self.adapter.frames_per_chunk :],
        )
        return batch, None

    def _conversation(
        self,
        observations: list[_PendingObservation],
        message: str,
        system_prompt: str | None = None,
    ) -> tuple[Any, str, list[int]]:
        processor = self._runtime["processor"]
        torch = self._runtime["torch"]
        model_device = self._model_device()
        content: list[dict[str, Any]] = []
        clip = None
        if observations:
            frames = [self._frame_tensor(item.observation) for item in observations]
            clip = torch.stack(frames)
            content.append({"type": "video", "video": clip})
        if message:
            content.append({"type": "text", "text": message})
        conversation: list[dict[str, Any]] = []
        if system_prompt:
            conversation.append(
                {
                    "role": "system",
                    "content": [{"type": "text", "text": system_prompt}],
                }
            )
        conversation.append({"role": "user", "content": content})
        texts = processor.apply_chat_template(
            conversation,
            tokenize=False,
            add_generation_prompt=True,
            return_tensors="pt",
        )
        past_ids = self.state.get("past_ids")
        if past_ids is not None:
            offset = int(self._runtime.get("system_prompt_offset", 0))
            texts = "<|im_end|>\n" + texts[offset:]
        kwargs: dict[str, Any] = {
            "text": texts,
            "return_tensors": "pt",
            "return_attention_mask": self.adapter.return_attention_mask,
        }
        if clip is not None:
            kwargs["images"] = None
            kwargs["videos"] = [clip]
            kwargs["min_pixels"] = self.adapter.min_pixels
            kwargs["max_pixels"] = self.adapter.max_pixels
        inputs = processor(**kwargs)
        if hasattr(inputs, "to"):
            inputs = inputs.to(model_device)
        if past_ids is not None:
            if hasattr(past_ids, "to"):
                past_ids = past_ids.to(model_device)
            inputs["input_ids"] = torch.cat([past_ids, inputs["input_ids"]], dim=1)
        actual_input_ids = _ids_from_value(inputs["input_ids"])
        return inputs, texts, actual_input_ids

    def _decode(self, token_ids: list[int], *, skip_special_tokens: bool) -> str:
        tokenizer = self._runtime["tokenizer"]
        if hasattr(tokenizer, "decode"):
            return str(tokenizer.decode(token_ids, skip_special_tokens=skip_special_tokens))
        processor = self._runtime["processor"]
        if hasattr(processor, "decode"):
            return str(processor.decode(token_ids, skip_special_tokens=skip_special_tokens))
        return ""

    def _prompt_metadata(
        self,
        query: _PendingQuery | None,
        rendered_prompt: str,
        system_prompt: str | None,
    ) -> dict[str, Any]:
        """Persist prompt provenance without changing benchmark-owned text."""

        return {
            "query_kind": query.request.kind if query is not None else None,
            "benchmark_user_content": query.request.text if query is not None else None,
            "benchmark_user_content_sha256": (
                _sha256_text(query.request.text) if query is not None else None
            ),
            "system_prompt_identity": (
                "osb-proactive-wait-fallback-v1" if system_prompt else "none"
            ),
            "system_prompt": system_prompt,
            "serialization_method": (
                "processor.apply_chat_template_mechanical_roles_control_tokens"
            ),
            "rendered_prompt_sha256": (
                _sha256_text(rendered_prompt) if rendered_prompt else None
            ),
        }

    def _telemetry(
        self,
        *,
        observations: list[_PendingObservation],
        query: _PendingQuery | None,
        call_id: str,
        call_started: int,
        call_finished: int,
        first_token_perf_ns: int | None,
        commit_perf_ns: int | None,
        actual_input_ids: list[int],
        generated_token_ids: list[int] | None,
        rendered_prompt: str,
        system_prompt: str | None,
        instruction_dispatch_perf_ns: int | None,
        max_model_len: int | None,
        configured_max_new_tokens: int,
        effective_max_new_tokens: int,
        gpu_before: dict[str, Any],
        gpu_after: dict[str, Any],
        failure: BaseException | None,
        failure_stage: str | None,
    ) -> dict[str, Any]:
        video_token_id = self._runtime.get("video_token_id")
        text_token_ids_observable = isinstance(video_token_id, int)
        actual_input_text_ids = (
            [token_id for token_id in actual_input_ids if token_id != video_token_id]
            if text_token_ids_observable
            else []
        )
        input_text_token_count = (
            len(actual_input_text_ids) if text_token_ids_observable else None
        )
        frames = []
        for item in observations:
            observation = item.observation
            source_height, source_width = np.asarray(observation.rgb).shape[:2]
            height, width = self.adapter._resize_shape(
                source_height, source_width, self.adapter.max_pixels
            )
            frames.append(
                {
                    "observation_id": observation.observation_id
                    or f"frame-{observation.frame_index}",
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
        query_id = query.query_id if query else None
        dispatch = query.dispatch_perf_ns if query else None
        frame_arrivals = [item.arrival_perf_ns for item in observations]
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
        completion = call_finished if query and generated_token_ids is not None else None
        query_telemetry = None
        if query is not None:
            query_telemetry = {
                "query_id": query_id,
                "query_kind": query.request.kind,
                "logical_time_s": query.request.logical_time_s,
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
                "input_text_tokens": input_text_token_count,
                "output_tokens": (
                    len(generated_token_ids) if generated_token_ids is not None else None
                ),
            }
        model_call = {
            "call_id": call_id,
            "stage": (
                "qa_history_processing"
                if qa_phase == "history"
                else "qa_mixed_boundary"
                if qa_phase == "mixed_boundary"
                else "qa_query_answer"
                if qa_phase == "query"
                else "proactive_stream_chunk"
                if self.context.task is TaskName.PROACTIVE
                else "qa_prefix_state"
            ),
            "start_perf_ns": call_started,
            "end_perf_ns": call_finished,
            "submitted_frame_occurrences": len(frames),
            "submitted_pixels": sum(item["submitted_pixels"] for item in frames),
            "input_text_tokens": input_text_token_count,
            "output_tokens": (
                len(generated_token_ids) if generated_token_ids is not None else None
            ),
            "num_cached_tokens": None,
            "rendered_prompt_sha256": _sha256_text(rendered_prompt)
            if rendered_prompt
            else None,
            "instruction_dispatch_perf_ns": instruction_dispatch_perf_ns,
            "max_model_len": max_model_len,
            "configured_max_new_tokens": configured_max_new_tokens,
            "effective_max_new_tokens": effective_max_new_tokens,
            "qa_phase": qa_phase,
        }
        prompt_metadata = self._prompt_metadata(query, rendered_prompt, system_prompt)
        return {
            "schema_version": "osb-evaluation-telemetry-v2",
            "chunk_idx": self.call_index,
            "visible_until": (
                observations[-1].observation.timestamp_s
                if observations
                else query.request.logical_time_s if query else None
            ),
            "frame_count": len(frames),
            "frame_telemetry": frames,
            "adapter_submitted_frame_count": len(frames),
            "adapter_unique_submitted_frame_count": len(
                {item["observation_id"] for item in frames}
            ),
            "duplicate_frame_count": 0,
            "adapter_submitted_pixel_count": sum(
                item["submitted_pixels"] for item in frames
            ),
            "arrival_perf_ns": min(
                (item.arrival_perf_ns for item in observations),
                default=None,
            ),
            "commit_perf_ns": commit_perf_ns,
            "query_id": query_id,
            "benchmark_user_content_sha256": (
                _sha256_text(query.request.text) if query is not None else None
            ),
            "instruction_dispatch_perf_ns": instruction_dispatch_perf_ns,
            "instruction_text_sha256": (
                _sha256_text(self.context.record.instruction)
                if instruction_dispatch_perf_ns is not None
                and self.context.task is TaskName.PROACTIVE
                else None
            ),
            "rendered_prompt_sha256": _sha256_text(rendered_prompt)
            if rendered_prompt
            else None,
            "system_prompt_mode": (
                "proactive_wait_fallback" if system_prompt else "native_processor_default"
            ),
            "system_prompt_sha256": _sha256_text(system_prompt)
            if system_prompt
            else None,
            "prompt_serialization": "processor.apply_chat_template_mechanical_roles_control_tokens",
            "prompt_metadata": prompt_metadata,
            "query_telemetry": query_telemetry,
            "query_dispatch_perf_ns": dispatch,
            "first_token_perf_ns": first_token_perf_ns,
            "response_completion_perf_ns": completion,
            "response_total_ms": (
                query_telemetry.get("response_total_ms")
                if query_telemetry is not None
                else None
            ),
            "model_call": model_call,
            "model_calls": [model_call],
            "model_call_count": 1,
            "inference_wall_time_s": (call_finished - call_started) / 1e9,
            "actual_input_ids": actual_input_ids,
            "actual_input_token_count": len(actual_input_ids),
            "actual_input_text_ids": actual_input_text_ids,
            "input_text_tokens": input_text_token_count,
            "generated_token_ids": generated_token_ids,
            "output_tokens": (
                len(generated_token_ids) if generated_token_ids is not None else None
            ),
            "output_token_count": (
                len(generated_token_ids) if generated_token_ids is not None else None
            ),
            "qa_phase": qa_phase,
            "gpu_memory": {"before": gpu_before, "after": gpu_after},
            "resource_telemetry": _resource_telemetry(gpu_before, gpu_after),
            "failure_stage": failure_stage,
            "failure_type": type(failure).__name__ if failure is not None else None,
            "failure_reason": str(failure) if failure is not None else None,
            "timed_out": isinstance(failure, TimeoutError),
            "retry_count": 0,
            "max_model_len": max_model_len,
            "configured_max_new_tokens": configured_max_new_tokens,
            "effective_max_new_tokens": effective_max_new_tokens,
            "telemetry_coverage": {
                    "frames": "complete" if commit_perf_ns is not None else "missing_commit",
                "input_text_tokens": (
                    "complete" if text_token_ids_observable else "missing_vision_token_id"
                ),
                "output_tokens": (
                    "complete" if generated_token_ids is not None else "missing"
                ),
                "model_calls": "complete",
                "instruction_dispatch": (
                    "complete" if instruction_dispatch_perf_ns is not None else "not_applicable"
                ),
                "rendered_prompt_hash": "complete" if rendered_prompt else "missing",
                    "query_timing": (
                    "complete"
                    if query is not None and first_token_perf_ns is not None
                    else "partial_no_first_token"
                    if query is not None
                    else "not_applicable"
                ),
                "ttft": (
                    "complete"
                    if query is not None and first_token_perf_ns is not None
                    else "missing"
                    if query is not None
                    else "not_applicable"
                ),
                "gpu_memory": (
                    "process_attributed"
                    if gpu_before.get("backend") == "nvml-process-memory"
                    and gpu_before.get("attribution_ok")
                    and gpu_after.get("attribution_ok")
                    else "unavailable_or_unattributed"
                ),
            },
        }

    def _generate(
        self,
        observations: list[_PendingObservation],
        query: _PendingQuery | None,
        message: str,
        system_prompt: str | None = None,
    ) -> _GenerationResult:
        torch = self._runtime["torch"]
        model = self._runtime["model"]
        tokenizer = self._runtime["tokenizer"]
        call_id = f"call-{self.call_index}"
        self.call_index += 1
        call_started = time.perf_counter_ns()
        instruction_dispatch_perf_ns = (
            call_started
            if message and self.context.task is TaskName.PROACTIVE and not self.message_sent
            else None
        )
        rendered_prompt = ""
        model_context_limit = self.adapter.context_window_tokens
        actual_input_ids: list[int] = []
        streamer: _TokenTimestampStreamer | None = None
        configured_max_new_tokens = (
            self.adapter.qa_max_new_tokens
            if query is not None
            else self.adapter.max_new_tokens
        )
        effective_max_new_tokens = configured_max_new_tokens
        gpu_monitor = self._runtime.get("gpu_monitor")
        gpu_before = _gpu_memory_snapshot(torch, self.adapter.device, gpu_monitor)
        try:
            inputs, rendered_prompt, actual_input_ids = self._conversation(
                observations, message, system_prompt
            )
            streamer = _TokenTimestampStreamer(
                torch, self.adapter.device, prompt_length=len(actual_input_ids)
            )
            do_sample = (
                self.adapter.qa_do_sample
                if query is not None
                else self.adapter.do_sample
            )
            model_context_limit = int(
                getattr(
                    getattr(model, "config", None),
                    "max_position_embeddings",
                    self.adapter.context_window_tokens,
                )
                or self.adapter.context_window_tokens
            )
            available_new_tokens = model_context_limit - len(actual_input_ids)
            if available_new_tokens < 1:
                self.context_overflowed = True
                raise ValueError(
                    "LiveCC input plus generation exceeds model context window: "
                    f"requested={len(actual_input_ids) + 1}, limit={model_context_limit}"
                )
            # QA only needs a short option label, while proactive output is
            # already bounded. Never ask the model for tokens that cannot fit;
            # persist both configured and effective budgets for auditability.
            effective_max_new_tokens = min(configured_max_new_tokens, available_new_tokens)
            generation_kwargs = dict(inputs)
            generation_kwargs.update(
                {
                    "past_key_values": self.state.get("past_key_values"),
                    "return_dict_in_generate": True,
                    "do_sample": do_sample,
                    "repetition_penalty": self.adapter.repetition_penalty,
                    "max_new_tokens": effective_max_new_tokens,
                    "pad_token_id": getattr(
                        getattr(model, "config", None),
                        "eos_token_id",
                        getattr(
                            getattr(model, "generation_config", None),
                            "pad_token_id",
                            None,
                        ),
                    ),
                    "streamer": streamer,
                }
            )
            if do_sample:
                generation_kwargs["temperature"] = self.adapter.temperature
            outputs = model.generate(**generation_kwargs)
            _sync_cuda(torch, self.adapter.device)
            call_finished = time.perf_counter_ns()
            sequences = getattr(outputs, "sequences", None)
            if sequences is not None:
                sequence_ids = _ids_from_value(sequences)
                generated_ids = sequence_ids[len(actual_input_ids) :]
                if hasattr(sequences, "ndim") and sequences.ndim == 2:
                    self.state["past_ids"] = sequences[:, :-1]
            else:
                generated_ids = list(streamer.generated_token_ids)
            self.state["past_key_values"] = getattr(outputs, "past_key_values", None)
            raw_text = (
                tokenizer.decode(generated_ids, skip_special_tokens=False)
                if hasattr(tokenizer, "decode")
                else ""
            )
            visible_text = (
                tokenizer.decode(generated_ids, skip_special_tokens=True)
                if hasattr(tokenizer, "decode")
                else raw_text
            )
            telemetry = self._telemetry(
                observations=observations,
                query=query,
                call_id=call_id,
                call_started=call_started,
                call_finished=call_finished,
                first_token_perf_ns=streamer.first_token_perf_ns,
                commit_perf_ns=call_finished,
                actual_input_ids=actual_input_ids,
                generated_token_ids=generated_ids,
                rendered_prompt=rendered_prompt,
                system_prompt=system_prompt,
                instruction_dispatch_perf_ns=instruction_dispatch_perf_ns,
                max_model_len=model_context_limit,
                configured_max_new_tokens=configured_max_new_tokens,
                effective_max_new_tokens=effective_max_new_tokens,
                gpu_before=gpu_before,
                gpu_after=_gpu_memory_snapshot(torch, self.adapter.device, gpu_monitor),
                failure=None,
                failure_stage=None,
            )
            return _GenerationResult(
                visible_text=visible_text,
                raw_text=raw_text,
                generated_token_ids=generated_ids,
                actual_input_ids=actual_input_ids,
                telemetry=telemetry,
                raw_output={
                    "provider_text": raw_text,
                    "visible_text": visible_text,
                    "generated_token_ids": generated_ids,
                    "actual_input_ids": actual_input_ids,
                    "is_silent": False,
                    "silence_source": None,
                },
            )
        except Exception as exc:
            _raise_fatal_cuda_error(exc)
            call_finished = time.perf_counter_ns()
            telemetry = self._telemetry(
                observations=observations,
                query=query,
                call_id=call_id,
                call_started=call_started,
                call_finished=call_finished,
                first_token_perf_ns=None,
                commit_perf_ns=None,
                actual_input_ids=actual_input_ids,
                # A failed generation has no completed output boundary. Keep
                # any partial IDs in raw_output, but do not report them as a
                # completed response or manufacture response_total_ms.
                generated_token_ids=None,
                rendered_prompt=rendered_prompt,
                system_prompt=system_prompt,
                instruction_dispatch_perf_ns=instruction_dispatch_perf_ns,
                max_model_len=model_context_limit,
                configured_max_new_tokens=configured_max_new_tokens,
                effective_max_new_tokens=effective_max_new_tokens,
                gpu_before=gpu_before,
                gpu_after=_gpu_memory_snapshot(torch, self.adapter.device, gpu_monitor),
                failure=exc,
                failure_stage="model_generation",
            )
            return _GenerationResult(
                visible_text="",
                raw_text="",
                generated_token_ids=[],
                actual_input_ids=[],
                telemetry=telemetry,
                raw_output={
                    "provider_text": "",
                    "visible_text": "",
                    "generated_token_ids": list(streamer.generated_token_ids) if streamer else [],
                    "actual_input_ids": actual_input_ids,
                    "is_silent": False,
                    "silence_source": None,
                    "error": str(exc),
                },
                failed_reason=str(exc),
            )

    def _event(
        self,
        result: _GenerationResult,
        observations: list[_PendingObservation],
        query: _PendingQuery | None,
    ) -> ModelEvent:
        logical_time = (
            observations[-1].observation.timestamp_s
            if observations
            else query.request.logical_time_s if query else 0.0
        )
        if result.failed_reason is not None:
            return ModelEvent(
                kind=EventKind.FAILURE,
                logical_time_s=logical_time,
                status="failed",
                failed_reason=result.failed_reason,
                raw_output=result.raw_output,
                telemetry=result.telemetry,
            )
        if query is not None or self.context.task is TaskName.QA:
            if isinstance(result.raw_output, dict):
                result.raw_output.setdefault("is_silent", False)
            return ModelEvent(
                kind=EventKind.ANSWER,
                logical_time_s=logical_time,
                text=result.visible_text,
                raw_output=result.raw_output,
                response_decision="response",
                is_final=True,
                event_id=f"qa-{self.sequence_id}",
                sequence_id=self.sequence_id,
                telemetry=result.telemetry,
            )
        silence_source = _silence_source(result.visible_text)
        if silence_source is not None:
            if isinstance(result.raw_output, dict):
                result.raw_output["is_silent"] = True
                result.raw_output["silence_source"] = silence_source
            # A control-only response is not a valid answer token. Keep the
            # raw generated IDs and their timing, but exclude them from the
            # response episode/latency first-token field.
            control_first_token = result.telemetry.get("first_token_perf_ns")
            result.telemetry["control_first_token_perf_ns"] = control_first_token
            result.telemetry["first_token_perf_ns"] = None
            result.telemetry["silence_source"] = silence_source
            return ModelEvent(
                kind=EventKind.WAIT,
                logical_time_s=logical_time,
                text="WAIT",
                raw_output=result.raw_output,
                response_decision="silent",
                event_id=f"event-{self.sequence_id}",
                sequence_id=self.sequence_id,
                telemetry=result.telemetry,
            )
        event = ModelEvent(
            kind=EventKind.ANSWER,
            logical_time_s=logical_time,
            text=result.visible_text,
            raw_output=result.raw_output,
            response_id=f"episode-{self.response_episode_index}",
            sequence_id=self.sequence_id,
            text_mode="complete",
            is_final=True,
            response_decision="response",
            event_id=f"event-{self.sequence_id}",
            telemetry=result.telemetry,
        )
        if isinstance(result.raw_output, dict):
            result.raw_output.setdefault("is_silent", False)
            result.raw_output.setdefault("silence_source", None)
        self.response_episode_index += 1
        return event

    def _run_batch(
        self,
        observations: list[_PendingObservation],
        query: _PendingQuery | None,
    ) -> list[ModelEvent]:
        if query is not None and observations:
            if any(
                item.observation.timestamp_s > query.request.logical_time_s + 1e-9
                for item in observations
            ):
                raise ValueError("future observation passed to LiveCC QA query")
        if query is not None and self.context.task is TaskName.QA:
            message = query.request.text
        elif not self.message_sent:
            message = (
                self.context.record.instruction
                if self.context.task is TaskName.PROACTIVE
                else self.adapter.context_prompt
            )
        else:
            message = ""
        system_prompt = (
            self.adapter.proactive_system_prompt
            if self.context.task is TaskName.PROACTIVE and not self.system_prompt_sent
            else None
        )
        result = self._generate(observations, query, message, system_prompt)
        if message:
            self.message_sent = True
        if system_prompt:
            self.system_prompt_sent = True
        event = self._event(result, observations, query)
        if query is None and self.context.task is TaskName.QA:
            if event.kind is EventKind.FAILURE:
                return [event]
            return [
                ModelEvent(
                    kind=EventKind.TELEMETRY,
                    logical_time_s=event.logical_time_s,
                    raw_output=event.raw_output,
                    telemetry=event.telemetry,
                )
            ]
        if query is not None:
            self.qa_answered = True
        self.sequence_id += 1
        return [event]

    def observe(self, observation: Observation) -> list[ModelEvent]:
        if self.closed:
            raise RuntimeError("LiveCC session is closed")
        if self.context_overflowed:
            return []
        frame = self.adapter._validate_observation(observation)
        del frame
        if (
            self.last_observed_timestamp is not None
            and observation.timestamp_s < self.last_observed_timestamp - 1e-9
        ):
            raise ValueError("LiveCC observations must be monotonic")
        self.last_observed_timestamp = observation.timestamp_s
        self.pending.append(
            _PendingObservation(
                observation=observation,
                # Core stamps arrival immediately before calling the adapter.
                # Reuse that boundary so frame telemetry and Core observation
                # events share the same runtime clock sample.
                arrival_perf_ns=(
                    int(observation.arrival_perf_ns)
                    if isinstance(observation.arrival_perf_ns, int)
                    else time.perf_counter_ns()
                ),
            )
        )
        if (
            self.context.task is TaskName.PROACTIVE
            and not self.proactive_started
        ):
            instruction_time = self.context.record.instruction_time_s
            if observation.timestamp_s < instruction_time - 1e-9:
                return []
            self.proactive_started = True
            observations, self.pending = self.pending, []
            return self._run_batch(observations, None)
        observations, query = self._take_batch()
        if not observations and query is None:
            return []
        return self._run_batch(observations, query)

    def query(self, request: QueryRequest) -> list[ModelEvent]:
        if self.closed:
            raise RuntimeError("LiveCC session is closed")
        if self.context_overflowed:
            return []
        if self.context.task is TaskName.PROACTIVE:
            raise ValueError("LiveCC autonomous proactive session does not accept queries")
        if request.kind != "qa":
            raise ValueError("LiveCC QA session only accepts QA queries")
        # Core may dispatch a deferred QA query immediately before delivering
        # the question-time observation. The query is legal when its timestamp
        # is still inside the record; the batch selector enforces the visible
        # prefix once the next observation arrives.
        if request.logical_time_s > self.context.evidence_end_s + 1e-9:
            raise ValueError("LiveCC query is outside the visible record interval")
        if self.pending_query is not None:
            raise ValueError("LiveCC session already has a pending query")
        query = _PendingQuery(
            request=request,
            query_id=f"query-{self.query_index}",
            dispatch_perf_ns=(
                int(request.dispatch_perf_ns)
                if isinstance(request.dispatch_perf_ns, int)
                else time.perf_counter_ns()
            ),
        )
        self.query_index += 1
        self.pending_query = query
        return []

    def close(self) -> list[ModelEvent]:
        if self.closed:
            return []
        self.closed = True
        if self.context_overflowed:
            self.pending.clear()
            self.pending_query = None
            return []
        return self._flush_pending()

    def _flush_pending(self) -> list[ModelEvent]:
        events: list[ModelEvent] = []
        if self.pending:
            observations, self.pending = self.pending, []
            query, self.pending_query = self.pending_query, None
            events.extend(self._run_batch(observations, query))
        elif self.pending_query is not None:
            query, self.pending_query = self.pending_query, None
            events.extend(self._run_batch([], query))
        return events

    def flush(self) -> list[ModelEvent]:
        """Commit a final partial chunk while the scoring clock is still open."""

        if self.closed:
            return []
        if self.context_overflowed:
            self.pending.clear()
            self.pending_query = None
            return []
        return self._flush_pending()
