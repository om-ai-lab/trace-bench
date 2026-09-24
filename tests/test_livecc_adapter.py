from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from trace_bench.livecc_adapter import LiveCCAdapter, _resource_telemetry
from trace_bench.models import (
    EventKind,
    FatalEvaluationError,
    Observation,
    ProactiveRecord,
    QARecord,
    QueryRequest,
    RecordContext,
    RunConfig,
    TaskName,
)

torch = pytest.importorskip("torch")


class _Inputs(dict):
    def to(self, _device):
        return self


class _Tokenizer:
    def convert_tokens_to_ids(self, _tokens):
        return [999]

    def decode(self, token_ids, skip_special_tokens=False):
        del skip_special_tokens
        values = {
            701: "commentary",
            702: "A",
            703: "...",
        }
        return "".join(values.get(int(token_id), "") for token_id in token_ids)


class _Processor:
    def __init__(self):
        self.tokenizer = _Tokenizer()
        self.calls: list[dict[str, object]] = []

    def apply_chat_template(self, conversation, **_kwargs):
        self.last_conversation = conversation
        return "rendered"

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return _Inputs(input_ids=torch.tensor([[101, 999, 102]]))


class _Model:
    device = "cpu"

    def __init__(self, generated_ids=(702,), emit_stream_token=True, failure=None):
        self.config = SimpleNamespace(eos_token_id=2, max_position_embeddings=32768)
        self.generated_ids = list(generated_ids)
        self.emit_stream_token = emit_stream_token
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs):
        if self.failure is not None:
            raise self.failure
        self.calls.append(kwargs)
        input_ids = kwargs["input_ids"]
        streamer = kwargs["streamer"]
        streamer.put(input_ids.detach().cpu())
        generated = torch.tensor([self.generated_ids], dtype=torch.long)
        if self.emit_stream_token:
            for token_id in self.generated_ids:
                streamer.put(torch.tensor([[token_id]], dtype=torch.long))
        streamer.end()
        return SimpleNamespace(
            sequences=torch.cat([input_ids, generated], dim=1),
            past_key_values=object(),
        )


def _qa_context() -> RecordContext:
    record = QARecord(
        record_id="qa:livecc",
        source_id="qa:livecc",
        video_path="does-not-exist.mp4",
        question="Which option?",
        options=["A. yes", "B. no"],
        answer="A",
        question_time_s=1.0,
        evidence_anchor_s=0.0,
    )
    return RecordContext(
        record=record,
        task=TaskName.QA,
        video_path=record.video_path,
        evidence_start_s=0.0,
        evidence_end_s=1.0,
        config=RunConfig(release_dir="release", task="qa", adapter="test:adapter"),
    )


def _proactive_context(instruction_time_s=1.0) -> RecordContext:
    record = ProactiveRecord(
        record_id="proactive:livecc",
        source_id="proactive:livecc",
        video_path="does-not-exist.mp4",
        instruction="Describe what is happening.",
        instruction_time_s=instruction_time_s,
        deadline_s=2.0,
        windows=[],
    )
    return RecordContext(
        record=record,
        task=TaskName.PROACTIVE,
        video_path=record.video_path,
        evidence_start_s=0.0,
        evidence_end_s=2.0,
        config=RunConfig(
            release_dir="release",
            task="proactive",
            adapter="test:adapter",
        ),
    )


def _adapter(model: _Model, *, frames_per_chunk=2) -> LiveCCAdapter:
    adapter = LiveCCAdapter(
        model_id="/checkpoint",
        frames_per_chunk=frames_per_chunk,
        device="cpu",
    )
    processor = _Processor()
    adapter._runtime = {
        "torch": torch,
        "model": model,
        "processor": processor,
        "tokenizer": processor.tokenizer,
        "video_token_id": 999,
        "system_prompt_offset": 0,
    }
    return adapter


def _observation(timestamp_s: float, frame_index: int) -> Observation:
    return Observation(
        timestamp_s=timestamp_s,
        frame_index=frame_index,
        rgb=np.zeros((4, 5, 3), dtype=np.uint8),
        observation_id=f"obs-{frame_index}",
        arrival_perf_ns=100 + frame_index,
    )


def test_adapter_is_lazy_and_declares_rgb_native_capability():
    adapter = LiveCCAdapter(model_id="/checkpoint", device="cpu")

    assert adapter._runtime is None
    assert adapter.capabilities.evidence_delivery == "decoded_frames"
    assert adapter.capabilities.state_lifetime == "persistent"
    assert adapter.capabilities.response_mode == "autonomous"
    assert adapter.capabilities.qa_query_timing == "before_observation_deferred"
    assert adapter.metadata["visual_preprocessing"]["input_contract"].startswith("Core RGB")
    assert adapter.metadata["protocol"] == {
        "contract": "osb-contract-v4",
        "telemetry": "osb-evaluation-telemetry-v2",
        "scorer": "osb-scoring-v6",
        "preflight": "osb-preflight-v4",
        "proactive_track": "native_streaming_autonomous_logical_diagnostic",
    }
    assert adapter.metadata["prompt_contract"]["system_prompt"]["qa_explicit_message"] is False
    assert adapter.metadata["prompt_contract"]["system_prompt"]["proactive_explicit_message"] is True
    assert adapter.metadata["prompt_contract"]["native_silence_markers"] == []


def test_wall_clock_metadata_declares_primary_track():
    adapter = LiveCCAdapter(model_id="/checkpoint", device="cpu", pacing="wall_clock")
    assert adapter.metadata["protocol"]["proactive_track"] == (
        "native_streaming_autonomous_wall_clock"
    )


def test_process_gpu_resource_telemetry_preserves_attribution_and_increment():
    before = {
        "backend": "nvml-process-memory",
        "available": True,
        "attribution_ok": True,
        "sample_interval_ms": 100.0,
        "device_index": 7,
        "device_uuid": "GPU-7",
        "process_pid": 123,
        "other_compute_pids": [],
        "process_used_bytes": 100,
        "process_peak_bytes": 100,
    }
    after = {**before, "process_used_bytes": 160, "process_peak_bytes": 180}
    telemetry = _resource_telemetry(before, after)
    assert telemetry["attribution_ok"] is True
    assert telemetry["devices"][0]["baseline_bytes"] == 100
    assert telemetry["devices"][0]["peak_bytes"] == 180
    assert telemetry["devices"][0]["peak_increment_bytes"] == 80
    assert telemetry["devices"][0]["canonical_run_peak"] is True


def test_observation_requires_core_rgb_uint8():
    adapter = LiveCCAdapter(model_id="/checkpoint", device="cpu")

    with pytest.raises(ValueError, match="RGB uint8"):
        adapter._validate_observation(
            Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 2), dtype=np.uint8))
        )
    with pytest.raises(ValueError, match="RGB uint8"):
        adapter._validate_observation(
            Observation(
                timestamp_s=0.0,
                frame_index=0,
                rgb=np.zeros((2, 2, 3), dtype=np.float32),
            )
        )


def test_model_frame_resize_honors_max_pixels_without_upscaling_core_frames():
    assert LiveCCAdapter._resize_shape(540, 960, 301056) == (392, 728)
    assert LiveCCAdapter._resize_shape(540, 960, 156800) == (280, 504)
    assert LiveCCAdapter._resize_shape(4, 5, 301056) == (4, 5)


def test_qa_query_can_be_queued_before_question_time_frame():
    model = _Model(generated_ids=(702,))
    session = _adapter(model).open(_qa_context())

    assert session.query(
        QueryRequest(kind="qa", logical_time_s=1.0, text="Question?")
    ) == []
    assert session.observe(_observation(0.0, 0)) == []
    events = session.observe(_observation(1.0, 1))

    assert len(events) == 1
    event = events[0]
    assert event.kind is EventKind.ANSWER
    assert event.text == "A"
    telemetry = event.telemetry
    assert (
        telemetry["query_telemetry"]["dispatch_perf_ns"]
        <= telemetry["query_telemetry"]["completion_perf_ns"]
    )
    assert telemetry["query_telemetry"]["first_token_perf_ns"] is not None
    assert telemetry["query_telemetry"]["ttft_ms"] is not None
    assert [row["observation_id"] for row in telemetry["frame_telemetry"]] == [
        "obs-0",
        "obs-1",
    ]
    assert telemetry["adapter_submitted_frame_count"] == 2
    assert telemetry["adapter_submitted_pixel_count"] == 40
    assert telemetry["model_calls"][0]["input_text_tokens"] == 2
    assert telemetry["schema_version"] == "osb-evaluation-telemetry-v2"
    assert telemetry["benchmark_user_content_sha256"]
    assert telemetry["prompt_metadata"]["query_kind"] == "qa"
    assert telemetry["prompt_metadata"]["benchmark_user_content"] == "Question?"
    assert telemetry["model_calls"][0]["stage"] == "qa_query_answer"
    assert telemetry["model_calls"][0]["qa_phase"] == "query"
    content = session._runtime["processor"].last_conversation[0]["content"]
    assert content[-1] == {"type": "text", "text": "Question?"}
    assert all("Time=" not in str(item.get("text", "")) for item in content)


def test_qa_uses_core_dispatch_clock_and_marks_mixed_boundary_call():
    model = _Model(generated_ids=(702,))
    session = _adapter(model).open(_qa_context())
    query = QueryRequest(
        kind="qa",
        logical_time_s=1.0,
        text="Question?",
        dispatch_perf_ns=100,
    )
    assert session.query(query) == []
    before = _observation(0.0, 0)
    before.arrival_perf_ns = 99
    after = _observation(1.0, 1)
    after.arrival_perf_ns = 101
    assert session.observe(before) == []
    event = session.observe(after)[0]

    assert event.telemetry["query_dispatch_perf_ns"] == 100
    assert [row["arrival_perf_ns"] for row in event.telemetry["frame_telemetry"]] == [99, 101]
    assert event.telemetry["model_calls"][0]["stage"] == "qa_mixed_boundary"
    assert event.telemetry["model_calls"][0]["qa_phase"] == "mixed_boundary"


def test_proactive_suppresses_pre_instruction_and_emits_after_boundary():
    model = _Model(generated_ids=(701,))
    session = _adapter(model).open(_proactive_context())

    assert session.observe(_observation(0.0, 0)) == []
    events = session.observe(_observation(1.0, 1))

    assert len(events) == 1
    event = events[0]
    assert event.kind is EventKind.ANSWER
    assert event.text == "commentary"
    assert event.response_id == "episode-0"
    assert event.text_mode == "complete"
    assert event.is_final is True
    assert event.telemetry["visible_until"] == 1.0
    assert model.calls[0]["past_key_values"] is None
    conversation = session._runtime["processor"].last_conversation
    assert conversation[0]["role"] == "system"
    assert conversation[0]["content"][0]["text"] == LiveCCAdapter.PROACTIVE_WAIT_FALLBACK_PROMPT
    assert conversation[1]["role"] == "user"
    assert conversation[1]["content"][-1]["text"] == "Describe what is happening."
    assert event.telemetry["system_prompt_mode"] == "proactive_wait_fallback"


def test_pure_ellipsis_is_silent():
    model = _Model(generated_ids=(703,))
    session = _adapter(model).open(_proactive_context(instruction_time_s=1.0))

    assert session.observe(_observation(0.0, 0)) == []
    event = session.observe(_observation(1.0, 1))[0]

    assert event.kind is EventKind.WAIT
    assert event.text == "WAIT"
    assert event.response_decision == "silent"
    assert event.telemetry["first_token_perf_ns"] is None
    assert event.telemetry["silence_source"] == "provider_empty_continuation"
    assert event.raw_output["is_silent"] is True


def test_proactive_continuation_marker_is_not_declared_native_silence():
    adapter = LiveCCAdapter(model_id="/checkpoint", device="cpu")
    assert adapter.metadata["prompt_contract"]["native_silence_markers"] == []
    assert adapter.metadata["prompt_contract"]["provider_control_markers"] == ["..."]


def test_generation_budget_is_reduced_to_remaining_context():
    model = _Model(generated_ids=(702,))
    model.config.max_position_embeddings = 4
    session = _adapter(model).open(_qa_context())
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    session.observe(_observation(0.0, 0))
    event = session.observe(_observation(1.0, 1))[0]

    assert event.kind is EventKind.ANSWER
    assert model.calls[0]["max_new_tokens"] == 1
    assert event.telemetry["configured_max_new_tokens"] == 16
    assert event.telemetry["effective_max_new_tokens"] == 1


def test_missing_streamer_token_is_explicitly_unavailable():
    model = _Model(generated_ids=(702,), emit_stream_token=False)
    session = _adapter(model).open(_qa_context())
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    session.observe(_observation(0.0, 0))
    event = session.observe(_observation(1.0, 1))[0]

    assert event.telemetry["first_token_perf_ns"] is None
    assert event.telemetry["telemetry_coverage"]["ttft"] == "missing"
    assert event.telemetry["query_telemetry"]["ttft_ms"] is None


def test_missing_video_token_id_does_not_estimate_text_token_count():
    model = _Model(generated_ids=(702,))
    adapter = _adapter(model)
    adapter._runtime["video_token_id"] = None
    session = adapter.open(_qa_context())
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    session.observe(_observation(0.0, 0))
    event = session.observe(_observation(1.0, 1))[0]
    assert event.telemetry["input_text_tokens"] is None
    assert event.telemetry["telemetry_coverage"]["input_text_tokens"] == "missing_vision_token_id"


def test_context_overflow_is_recorded_before_generation():
    model = _Model(generated_ids=(702,))
    model.config.max_position_embeddings = 2
    session = _adapter(model).open(_qa_context())
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    session.observe(_observation(0.0, 0))
    event = session.observe(_observation(1.0, 1))[0]

    assert event.kind is EventKind.FAILURE
    assert "exceeds model context window" in event.failed_reason
    assert model.calls == []
    assert session.observe(_observation(2.0, 2)) == []
    assert session.close() == []


def test_fatal_cuda_error_does_not_become_record_failure():
    model = _Model(failure=RuntimeError("CUDA error: an illegal memory access"))
    session = _adapter(model).open(_qa_context())
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    session.observe(_observation(0.0, 0))

    with pytest.raises(FatalEvaluationError):
        session.observe(_observation(1.0, 1))


def test_each_session_starts_with_private_empty_kv_state():
    adapter = _adapter(_Model())
    first = adapter.open(_qa_context())
    second = adapter.open(_qa_context())

    assert first.state["past_ids"] is None
    assert first.state["past_key_values"] is None
    assert second.state["past_ids"] is None
    assert second.state["past_key_values"] is None
    assert first.state is not second.state


def test_proactive_instruction_is_dispatched_once_and_recorded():
    model = _Model(generated_ids=(701,))
    session = _adapter(model).open(_proactive_context())
    assert session.observe(_observation(0.0, 0)) == []
    event = session.observe(_observation(1.0, 1))[0]
    telemetry = event.telemetry
    assert isinstance(telemetry["instruction_dispatch_perf_ns"], int)
    assert telemetry["instruction_text_sha256"]
    assert telemetry["query_dispatch_perf_ns"] is None
    assert telemetry["model_calls"][0]["instruction_dispatch_perf_ns"] == telemetry[
        "instruction_dispatch_perf_ns"
    ]


def test_autonomous_proactive_rejects_polling_query():
    session = _adapter(_Model()).open(_proactive_context())
    with pytest.raises(ValueError, match="does not accept queries"):
        session.query(
            QueryRequest(
                kind="proactive",
                logical_time_s=1.0,
                text="Describe what is happening.",
            )
        )
