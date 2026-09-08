import numpy as np
import pytest
from types import SimpleNamespace

from open_stream_bench.models import (
    FatalEvaluationError,
    Observation,
    ProactiveRecord,
    QARecord,
    QueryRequest,
    RecordContext,
    RunConfig,
    TaskName,
)
from open_stream_bench.thinkstream_adapter import ThinkStreamAdapter, parse_thinkstream_output

torch = pytest.importorskip("torch")


class _Inputs(dict):
    def to(self, _device):
        return self


class _Tokenizer:
    vocab_size = 1000

    def __call__(self, _text, add_special_tokens=False):
        assert not add_special_tokens
        return SimpleNamespace(input_ids=[200])


class _Processor:
    tokenizer = _Tokenizer()

    def apply_chat_template(self, *_args, **_kwargs):
        return "rendered prompt"

    def __call__(self, **_kwargs):
        return _Inputs(input_ids=torch.tensor([[101, 999, 102]]))

    def batch_decode(self, _outputs, skip_special_tokens=False):
        assert not skip_special_tokens
        return ["<response>A<|im_end|>"]


class _SequenceProcessor(_Processor):
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def batch_decode(self, _outputs, skip_special_tokens=False):
        assert not skip_special_tokens
        return [next(self.outputs)]


class _RecordingSequenceProcessor(_SequenceProcessor):
    def __init__(self, outputs):
        super().__init__(outputs)
        self.prompts = []

    def apply_chat_template(self, messages, **kwargs):
        self.prompts.append(messages)
        return super().apply_chat_template(messages, **kwargs)


class _Engine:
    def __init__(self, failure=None):
        self.failure = failure
        self.reset_count = 0
        self.generate_count = 0
        self.generate_kwargs = []

    def reset(self):
        self.reset_count += 1

    def generate(self, **_kwargs):
        self.generate_count += 1
        self.generate_kwargs.append(_kwargs)
        if self.failure is not None:
            raise self.failure
        return [torch.tensor([301, 302, 303])]


class _SamplingEngine(_Engine):
    def generate(self, **kwargs):
        self.generate_count += 1
        self.generate_kwargs.append(kwargs)
        if self.failure is not None:
            raise self.failure
        kwargs["sample"]()
        return [torch.tensor([301, 302, 303])]


def _context() -> RecordContext:
    record = QARecord(
        record_id="qa:1",
        source_id="qa",
        video_path="unused.mp4",
        question="Question?",
        options=["A. yes", "B. no"],
        answer="A",
        question_time_s=1.0,
        evidence_anchor_s=0.0,
    )
    config = RunConfig(release_dir="release", task="qa", adapter="test:adapter")
    return RecordContext(
        record=record,
        task=TaskName.QA,
        video_path=record.video_path,
        evidence_start_s=0.0,
        evidence_end_s=1.0,
        config=config,
    )


def _adapter(engine: _Engine, processor=None) -> ThinkStreamAdapter:
    adapter = ThinkStreamAdapter(model_id="/checkpoint")
    adapter._runtime = {
        "torch": torch,
        "processor": processor or _Processor(),
        "engine": engine,
        "inference": SimpleNamespace(think_budget_sample_restricted=lambda **_kwargs: None),
        "data": SimpleNamespace(
            SYSTEM_PROMPT="system",
            QWEN_TEMPLATE_WO_SYSTEM="template",
            compute_position_ids=lambda inputs, processor, model_type: torch.tensor([[0]]),
        ),
        "token_ids": [10, 11, 12, 13],
        "video_token_id": 999,
    }
    return adapter


def test_parse_thinkstream_control_tokens():
    assert parse_thinkstream_output("<think>x</think><silent><|im_end|>") == ("silent", "", "x")
    assert parse_thinkstream_output("<think>x</think><response>A<|im_end|>") == ("response", "A", "x")


def test_adapter_is_lazy_and_declares_native_capability():
    adapter = ThinkStreamAdapter(model_id="/checkpoint")
    assert adapter._runtime is None
    assert adapter.max_len == 24576
    assert adapter.metadata["generation"]["max_len"] == 24576
    assert adapter.metadata["upstream"]["osb_alignment"]["max_len_matches_official_default"] is True
    assert adapter.metadata["protocol"]["contract"] == "osb-contract-v4"
    assert adapter.metadata["protocol"]["scorer"] == "osb-scoring-v5"
    assert adapter.capabilities.state_lifetime == "persistent"
    assert adapter.capabilities.response_mode == "autonomous"


def test_observation_requires_rgb_uint8():
    with pytest.raises(ValueError):
        ThinkStreamAdapter._validate_observation(  # type: ignore[attr-defined]
            Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 2), dtype=np.uint8))
        )


def test_chunk_telemetry_uses_actual_ids_and_observed_boundaries():
    engine = _Engine()
    session = _adapter(engine).open(_context())
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    assert session.observe(
        Observation(timestamp_s=0.0, frame_index=4, rgb=np.zeros((2, 3, 3), dtype=np.uint8))
    ) == []
    event = session.observe(
        Observation(timestamp_s=1.0, frame_index=8, rgb=np.zeros((4, 5, 3), dtype=np.uint8))
    )[0]

    telemetry = event.telemetry
    assert engine.generate_count == 1
    assert telemetry["actual_input_ids"] == [101, 999, 102]
    assert telemetry["actual_input_text_ids"] == [101, 102]
    assert telemetry["input_text_tokens"] == 2
    assert telemetry["generated_token_ids"] == [301, 302, 303]
    assert telemetry["output_tokens"] == 3
    assert telemetry["model_call_count"] == 1
    assert telemetry["model_calls"][0]["submitted_frame_occurrences"] == 2
    assert telemetry["model_calls"][0]["input_text_tokens"] == 2
    assert telemetry["model_calls"][0]["output_tokens"] == 3
    assert telemetry["model_call"]["start_perf_ns"] <= telemetry["model_call"]["end_perf_ns"]
    assert telemetry["adapter_submitted_frame_count"] == 2
    assert telemetry["adapter_unique_submitted_frame_count"] == 2
    assert telemetry["adapter_submitted_pixel_count"] == 26
    frames = telemetry["frame_telemetry"]
    assert [frame["video_time_s"] for frame in frames] == [0.0, 1.0]
    assert [(frame["submitted_width"], frame["submitted_height"]) for frame in frames] == [(3, 2), (5, 4)]
    assert all(frame["arrival_perf_ns"] <= frame["commit_perf_ns"] for frame in frames)
    query = telemetry["query_telemetry"]
    assert query["dispatch_perf_ns"] <= query["completion_perf_ns"]
    assert query["first_token_perf_ns"] is None
    assert query["ttft_ms"] is None
    assert telemetry["telemetry_coverage"]["ttft"] == "missing"
    assert telemetry["gpu_memory"]["before"]["canonical_run_peak"] is False
    assert telemetry["resource_telemetry"]["attribution_ok"] is False
    assert telemetry["resource_telemetry"]["devices"] == []


def test_qa_generation_uses_full_vocab_for_actual_option_parser():
    engine = _Engine()
    session = _adapter(engine).open(_context())
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    session.observe(
        Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    session.observe(
        Observation(timestamp_s=1.0, frame_index=1, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )

    sample_kwargs = engine.generate_kwargs[-1]["sample_kwargs"]
    assert sample_kwargs["allow_deferral"] is False
    assert sample_kwargs["restricted_token_ids"] == list(range(_Processor.tokenizer.vocab_size))
    assert sample_kwargs["restricted_token_ids"][4] == 4  # E is not hard-coded away.


def test_autonomous_first_token_is_persisted_outside_query_telemetry():
    adapter = _adapter(_SamplingEngine())
    context = _context()
    context.task = TaskName.PROACTIVE
    session = adapter.open(context)
    session.query(QueryRequest(kind="proactive", logical_time_s=1.0, text="Instruction"))
    session.observe(
        Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    session.observe(
        Observation(timestamp_s=1.0, frame_index=1, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    # The first chunk consumes the one autonomous instruction.  The second
    # chunk is observation-only and must retain its own response timing.
    emitted = session.observe(
        Observation(timestamp_s=2.0, frame_index=2, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    emitted.extend(
        session.observe(
            Observation(timestamp_s=3.0, frame_index=3, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
        )
    )
    events = emitted + session.close()
    assert events
    telemetry = events[-1].telemetry
    assert telemetry["query_telemetry"] is None
    assert isinstance(telemetry["first_token_perf_ns"], int)
    assert telemetry["model_calls"][0]["first_token_perf_ns"] == telemetry["first_token_perf_ns"]
    assert telemetry["model_calls"][0]["completion_perf_ns"] == telemetry[
        "response_completion_perf_ns"
    ]


def test_generation_failure_preserves_failure_and_missing_commit_telemetry():
    session = _adapter(_Engine(failure=RuntimeError("generation failed"))).open(_context())
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    session.observe(
        Observation(timestamp_s=0.0, frame_index=4, rgb=np.zeros((2, 3, 3), dtype=np.uint8))
    )
    event = session.observe(
        Observation(timestamp_s=1.0, frame_index=8, rgb=np.zeros((2, 3, 3), dtype=np.uint8))
    )[0]

    assert event.status == "failed"
    assert event.failed_reason == "generation failed"
    assert event.telemetry["failure_stage"] == "model_generation"
    assert event.telemetry["failure_type"] == "RuntimeError"
    assert event.telemetry["commit_perf_ns"] is None
    assert event.telemetry["output_tokens"] is None
    assert event.telemetry["telemetry_coverage"]["frames"] == "missing_commit"


def test_query_telemetry_is_not_reused_on_later_autonomous_chunks():
    engine = _Engine()
    adapter = _adapter(engine)
    context = _context()
    context.task = TaskName.PROACTIVE
    session = adapter.open(context)
    request = QueryRequest(kind="proactive", logical_time_s=1.0, text="Instruction")
    session.query(request)
    # This fixture uses an explicit query to stand in for the already-consumed
    # autonomous instruction; real Core runs set this at the instruction
    # boundary inside ``_run_chunk``.
    session.instruction_injected = True
    first = session.observe(
        Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    # A second observation is a new autonomous chunk and must not inherit the
    # first query's dispatch timestamp.
    second = session.observe(
        Observation(timestamp_s=1.0, frame_index=1, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    assert first == []
    # The first response fragment is held until the next model boundary so
    # the adapter can mark its final fragment without using chunk_index.
    assert second == []

    third = session.observe(
        Observation(timestamp_s=2.0, frame_index=2, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    fourth = session.observe(
        Observation(timestamp_s=3.0, frame_index=3, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    assert third == []
    assert fourth[0].telemetry["query_telemetry"] is not None
    assert all(
        kwargs["sample_kwargs"]["is_query_window"]
        for kwargs in engine.generate_kwargs
    )
    # The current autonomous fragment has no query telemetry and is flushed at
    # record close.
    closed = session.close()
    assert closed[0].telemetry["query_telemetry"] is None


def test_autonomous_instruction_is_injected_once_and_prefill_is_suppressed():
    processor = _RecordingSequenceProcessor(
        ["<response>prefill<|im_end|>", "<response>answer<|im_end|>"]
    )
    engine = _Engine()
    adapter = _adapter(engine, processor=processor)
    record = ProactiveRecord(
        record_id="proactive-instruction",
        source_id="proactive-instruction",
        video_path="unused.mp4",
        instruction="raw benchmark instruction",
        instruction_time_s=2.0,
        windows=[{"start_s": 2.0, "end_s": 4.0, "expected_answer": "answer"}],
    )
    context = RecordContext(
        record=record,
        task=TaskName.PROACTIVE,
        video_path=record.video_path,
        evidence_start_s=0.0,
        evidence_end_s=3.0,
        config=RunConfig(release_dir="release", task="proactive", adapter="test:adapter", pacing="wall_clock"),
    )
    session = adapter.open(context)
    assert session.observe(
        Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    ) == []
    prefill = session.observe(
        Observation(timestamp_s=1.0, frame_index=1, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    assert len(prefill) == 1
    assert prefill[0].kind.value == "telemetry"
    assert prefill[0].telemetry["provider_output_suppressed"] is True

    # The boundary triggers an immediate one-frame call rather than waiting
    # for a future observation to complete the adapter-local chunk.
    assert session.observe(
        Observation(timestamp_s=2.0, frame_index=2, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    ) == []
    final = session.close()
    assert len(final) == 1
    assert final[0].text == "answer"
    assert final[0].telemetry["query_telemetry"]["query_kind"] == "proactive"
    instruction_prompts = [
        message
        for prompt in processor.prompts
        for message in prompt
        if isinstance(message, dict)
        and any(
            isinstance(item, dict)
            and item.get("text") == "raw benchmark instruction"
            for item in message.get("content", [])
            if isinstance(message.get("content"), list)
        )
    ]
    assert len(instruction_prompts) == 1
    assert engine.generate_kwargs[0]["sample_kwargs"]["is_query_window"] is False
    assert engine.generate_kwargs[-1]["sample_kwargs"]["is_query_window"] is True


def test_proactive_fragments_share_episode_and_finalize_on_wait():
    processor = _SequenceProcessor(
        [
            "<response>She<|im_end|>",
            "<response>walks<|im_end|>",
            "<silent><|im_end|>",
        ]
    )
    adapter = _adapter(_Engine(), processor=processor)
    context = _context()
    context.task = TaskName.PROACTIVE
    session = adapter.open(context)
    session.query(QueryRequest(kind="proactive", logical_time_s=1.0, text="Instruction"))

    assert session.observe(
        Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    ) == []
    first = session.observe(
        Observation(timestamp_s=1.0, frame_index=1, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    assert first == []  # The first fragment is held until its boundary is known.
    assert session.observe(
        Observation(timestamp_s=2.0, frame_index=2, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    ) == []
    second = session.observe(
        Observation(timestamp_s=3.0, frame_index=3, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    assert len(second) == 1
    assert second[0].text == "She"
    assert second[0].response_id == "episode-0"
    assert second[0].sequence_id == 0
    assert second[0].text_mode == "delta"
    assert second[0].is_final is False

    assert session.observe(
        Observation(timestamp_s=4.0, frame_index=4, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    ) == []
    third = session.observe(
        Observation(timestamp_s=5.0, frame_index=5, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    assert [event.kind.value for event in third] == ["answer", "wait"]
    final, wait = third
    assert final.text == "walks"
    assert final.response_id == "episode-0"
    assert final.sequence_id == 1
    assert final.is_final is True
    assert wait.sequence_id == 2
    assert wait.response_decision == "silent"
    assert wait.text == "WAIT"


def test_proactive_close_marks_last_fragment_final():
    processor = _SequenceProcessor(["<response>She<|im_end|>"])
    adapter = _adapter(_Engine(), processor=processor)
    context = _context()
    context.task = TaskName.PROACTIVE
    session = adapter.open(context)
    session.observe(
        Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    )
    assert session.observe(
        Observation(timestamp_s=1.0, frame_index=1, rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    ) == []
    final = session.close()
    assert len(final) == 1
    assert final[0].response_id == "episode-0"
    assert final[0].is_final is True


def test_cuda_device_assert_aborts_process_instead_of_becoming_record_failure():
    session = _adapter(_Engine(failure=RuntimeError("CUDA error: device-side assert triggered"))).open(
        _context()
    )
    session.query(QueryRequest(kind="qa", logical_time_s=1.0, text="Question?"))
    session.observe(
        Observation(timestamp_s=0.0, frame_index=4, rgb=np.zeros((2, 3, 3), dtype=np.uint8))
    )
    with pytest.raises(FatalEvaluationError, match="fatal CUDA error"):
        session.observe(
            Observation(timestamp_s=1.0, frame_index=8, rgb=np.zeros((2, 3, 3), dtype=np.uint8))
        )
