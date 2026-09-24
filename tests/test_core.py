from __future__ import annotations

import json
import time
from types import SimpleNamespace

import numpy as np
import pytest

from trace_bench.bundle import RunBundle
from trace_bench.config import resolve_config
from trace_bench.core import (
    _ObservationClock,
    _align_response_events_to_stream_clock,
    _annotate_proactive_response_latency,
    _call_observe,
    _last_prediction,
    _proactive_evaluation_end_s,
    _proactive_record,
    _qa_record,
    run,
)
from trace_bench.models import (
    AdapterCapabilities,
    EventKind,
    FatalEvaluationError,
    ModelEvent,
    Observation,
    ProactiveRecord,
    QARecord,
    RunConfig,
    TaskName,
)
from trace_bench.sampling import SampledVideo


def test_qa_vertical_slice(synthetic_release):
    release, video_root = synthetic_release
    output = video_root / "qa-run"
    config = resolve_config(
        release_dir=release,
        task=TaskName.QA,
        subset="tiny",
        adapter="trace_bench.adapters:TestDoubleAdapter",
        output_dir=output,
        video_root=str(video_root),
        overrides={"stream_fps": 1.0, "qa_window_s": 1.0},
        synthetic=True,
    )
    run(config)
    assert RunBundle(output).validate()["valid"] is True
    assert (output / "metrics.json").read_text(encoding="utf-8").find('"accuracy": 1.0') >= 0
    resolved = json.loads((output / "resolved_config.json").read_text(encoding="utf-8"))
    assert resolved["preflight"]["visual_input"]["stream_fps"] == 1.0
    assert resolved["preflight"]["visual_input"]["resize_policy"].startswith("width_at_most")


def test_proactive_vertical_slice(synthetic_release):
    release, video_root = synthetic_release
    output = video_root / "proactive-run"
    config = resolve_config(
        release_dir=release,
        task=TaskName.PROACTIVE,
        subset="tiny",
        adapter="trace_bench.adapters:TestDoubleAdapter",
        output_dir=output,
        video_root=str(video_root),
        overrides={"stream_fps": 1.0, "proactive_window_s": 5.0, "proactive_step_s": 1.0},
        synthetic=True,
    )
    run(config)
    assert RunBundle(output).validate()["valid"] is True
    assert (output / "metrics.json").read_text(encoding="utf-8").find('"window_accuracy": 1.0') >= 0


def test_autonomous_proactive_does_not_inject_polling_queries(monkeypatch, tmp_path):
    observations = [
        Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 3, 3), dtype=np.uint8)),
        Observation(timestamp_s=1.0, frame_index=1, rgb=np.zeros((2, 3, 3), dtype=np.uint8)),
        Observation(timestamp_s=2.0, frame_index=2, rgb=np.zeros((2, 3, 3), dtype=np.uint8)),
    ]
    monkeypatch.setattr(
        "trace_bench.core.sample_video",
        lambda *_args, **_kwargs: SampledVideo(
            observations=observations,
            source_fps=1.0,
            source_frame_count=len(observations),
            video_sha256="synthetic",
            decoder="test",
        ),
    )
    monkeypatch.setattr("trace_bench.core.video_duration_s", lambda _path: 2.0)

    class Session:
        def query(self, _request):
            raise AssertionError("autonomous proactive must not receive a polling query")

        def observe(self, observation):
            return [
                ModelEvent(
                    kind=EventKind.WAIT,
                    logical_time_s=observation.timestamp_s,
                    text="WAIT",
                )
            ]

        def close(self):
            return []

    class Adapter:
        capabilities = AdapterCapabilities(
            state_lifetime="persistent",
            response_mode="autonomous",
        )

        def open(self, _context):
            return Session()

    record = ProactiveRecord(
        record_id="proactive-autonomous",
        source_id="proactive-autonomous",
        video_path="unused.mp4",
        instruction="Describe the event.",
        instruction_time_s=1.0,
        deadline_s=2.0,
        windows=[],
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.PROACTIVE,
        adapter="unused:Adapter",
        proactive_window_s=5.0,
    )

    result, _events = _proactive_record(
        record, tmp_path / "unused.mp4", config, Adapter(), Adapter.capabilities
    )
    assert result["status"] == "completed"
    assert result["evaluation_end_s"] == record.instruction_time_s


def test_proactive_evaluation_end_preserves_final_strict_window():
    record = ProactiveRecord(
        record_id="proactive-final-grace",
        source_id="proactive-final-grace",
        video_path="unused.mp4",
        instruction="Describe the event.",
        instruction_time_s=0.0,
        windows=[{"start_s": 9.0, "end_s": 9.1, "expected_answer": "event"}],
    )
    assert _proactive_evaluation_end_s(record, 5.0, video_end_s=10.0) == 14.0


def test_proactive_evidence_does_not_stream_source_tail(monkeypatch, tmp_path):
    sampled_args = {}
    observations = [
        Observation(
            timestamp_s=float(index),
            frame_index=index,
            rgb=np.zeros((2, 3, 3), dtype=np.uint8),
        )
        for index in range(7)
    ]

    def sample_video_stub(_path, timestamps, **_kwargs):
        sampled_args["timestamps"] = timestamps
        return SampledVideo(
            observations=observations,
            source_fps=1.0,
            source_frame_count=7,
            video_sha256="synthetic",
            decoder="test",
        )

    monkeypatch.setattr("trace_bench.core.sample_video", sample_video_stub)
    monkeypatch.setattr("trace_bench.core.video_duration_s", lambda _path: 100.0)

    class Session:
        def observe(self, _observation):
            return []

        def close(self):
            return []

    class Adapter:
        capabilities = AdapterCapabilities(
            state_lifetime="persistent",
            response_mode="autonomous",
        )

        def open(self, _context):
            return Session()

    record = ProactiveRecord(
        record_id="proactive-bounded",
        source_id="proactive-bounded",
        video_path="unused.mp4",
        instruction="Describe the event.",
        instruction_time_s=0.0,
        windows=[{"start_s": 1.0, "end_s": 1.1, "expected_answer": "event"}],
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.PROACTIVE,
        adapter="unused:Adapter",
        proactive_window_s=5.0,
    )

    result, _events = _proactive_record(
        record, tmp_path / "unused.mp4", config, Adapter(), Adapter.capabilities
    )

    assert result["video_duration_s"] == 100.0
    assert result["evaluation_end_s"] == 6.0
    assert result["evidence_end_s"] == 6.0
    assert result["proactive_evidence_end_policy"] == "last_strict_window_end_clamped_to_video"
    assert sampled_args["timestamps"][-1] == 6.0


def test_proactive_1469_stops_at_gt_window_when_source_duration_is_unknown(
    monkeypatch, tmp_path
):
    sampled_args = {}

    def sample_video_stub(_path, timestamps, **_kwargs):
        sampled_args["timestamps"] = timestamps
        return SampledVideo(
            observations=[
                Observation(
                    timestamp_s=timestamp,
                    frame_index=index,
                    rgb=np.zeros((2, 3, 3), dtype=np.uint8),
                )
                for index, timestamp in enumerate(timestamps)
            ],
            source_fps=24.0,
            source_frame_count=None,
            video_sha256="synthetic",
            decoder="test",
        )

    monkeypatch.setattr("trace_bench.core.sample_video", sample_video_stub)
    monkeypatch.setattr("trace_bench.core.video_duration_s", lambda _path: None)

    class Session:
        def observe(self, _observation):
            return []

        def close(self):
            return []

    class Adapter:
        capabilities = AdapterCapabilities(
            state_lifetime="persistent",
            response_mode="autonomous",
        )

        def open(self, _context):
            return Session()

    record = ProactiveRecord(
        record_id="ovo_bench_proactive:1469",
        source_id="ovo_bench_proactive:1469",
        video_path="tt0048028.mp4",
        instruction="Describe the event.",
        instruction_time_s=310.0,
        deadline_s=347.0,
        windows=[
            {"start_s": 317.0, "end_s": 322.0, "expected_answer": "walks past him"}
        ],
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.PROACTIVE,
        adapter="unused:Adapter",
        proactive_window_s=5.0,
    )

    result, _events = _proactive_record(
        record, tmp_path / "tt0048028.mp4", config, Adapter(), Adapter.capabilities
    )

    assert result["deadline_s"] == 347.0
    assert result["video_duration_s"] is None
    assert result["evaluation_end_s"] == 322.0
    assert result["evidence_end_s"] == 322.0
    assert result["video_duration_policy"] == "unavailable_not_scanned"
    assert sampled_args["timestamps"][-1] == 322.0


def test_autonomous_wall_clock_applies_only_remaining_final_window_grace(
    monkeypatch, tmp_path
):
    observations = [
        Observation(
            timestamp_s=float(index),
            frame_index=index,
            rgb=np.zeros((2, 3, 3), dtype=np.uint8),
        )
        for index in range(3)
    ]
    monkeypatch.setattr(
        "trace_bench.core.sample_video",
        lambda *_args, **_kwargs: SampledVideo(
            observations=observations,
            source_fps=1.0,
            source_frame_count=len(observations),
            video_sha256="synthetic",
            decoder="test",
        ),
    )
    monkeypatch.setattr("trace_bench.core.video_duration_s", lambda _path: 2.0)

    class FakeClock:
        latest = None

        def __init__(self, timestamps, pacing):
            self.pacing = pacing
            self.video_start_s = timestamps[0]
            self.run_start_perf_ns = 0
            self.waited_video_times = []
            FakeClock.latest = self

        def scheduled_perf_ns(self, video_time_s):
            return int((video_time_s - self.video_start_s) * 1_000_000_000)

        def video_time_for_perf_ns(self, perf_ns):
            return self.video_start_s + perf_ns / 1_000_000_000

        def wait(self, video_time_s):
            self.waited_video_times.append(video_time_s)
            return self.scheduled_perf_ns(video_time_s)

    monkeypatch.setattr("trace_bench.core._ObservationClock", FakeClock)

    class Session:
        def query(self, _request):
            raise AssertionError("autonomous grace must not inject polling queries")

        def observe(self, _observation):
            return []

        def close(self):
            return [
                ModelEvent(
                    kind=EventKind.ANSWER,
                    logical_time_s=2.0,
                    text="event",
                    telemetry={"first_token_perf_ns": 6_000_000_000},
                )
            ]

    class Adapter:
        capabilities = AdapterCapabilities(
            state_lifetime="persistent",
            response_mode="autonomous",
            pacing="wall_clock",
        )

        def open(self, _context):
            return Session()

    record = ProactiveRecord(
        record_id="proactive-grace",
        source_id="proactive-grace",
        video_path="unused.mp4",
        instruction="Describe the event.",
        instruction_time_s=0.0,
        windows=[{"start_s": 1.5, "end_s": 1.6, "expected_answer": "event"}],
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.PROACTIVE,
        adapter="unused:Adapter",
        pacing="wall_clock",
        proactive_window_s=5.0,
    )

    result, events = _proactive_record(
        record, tmp_path / "unused.mp4", config, Adapter(), Adapter.capabilities
    )
    assert result["evaluation_end_s"] == 6.5
    assert result["post_stream_response_grace_s"] == 4.5
    assert result["post_stream_scoring_grace_applied"] is True
    assert FakeClock.latest.waited_video_times == [0.0, 1.0, 2.0, 6.5]
    answer = next(event for event in events if event["kind"] == "answer")
    assert answer["logical_time_s"] == 6.0
    assert answer["telemetry"]["post_stream_response"] is True
    assert answer["telemetry"]["within_evaluation_end"] is True


def test_autonomous_flushes_final_partial_chunk_before_grace(monkeypatch, tmp_path):
    observations = [
        Observation(
            timestamp_s=float(index),
            frame_index=index,
            rgb=np.zeros((2, 3, 3), dtype=np.uint8),
        )
        for index in range(3)
    ]
    monkeypatch.setattr(
        "trace_bench.core.sample_video",
        lambda *_args, **_kwargs: SampledVideo(
            observations=observations,
            source_fps=1.0,
            source_frame_count=len(observations),
            video_sha256="synthetic",
            decoder="test",
        ),
    )
    monkeypatch.setattr("trace_bench.core.video_duration_s", lambda _path: 2.0)

    order = []

    class FakeClock:
        def __init__(self, timestamps, pacing):
            self.pacing = pacing
            self.video_start_s = timestamps[0]
            self.run_start_perf_ns = 0

        def scheduled_perf_ns(self, video_time_s):
            return int((video_time_s - self.video_start_s) * 1_000_000_000)

        def video_time_for_perf_ns(self, perf_ns):
            return self.video_start_s + perf_ns / 1_000_000_000

        def wait(self, video_time_s):
            order.append(("wait", video_time_s))
            return self.scheduled_perf_ns(video_time_s)

    monkeypatch.setattr("trace_bench.core._ObservationClock", FakeClock)

    class Session:
        def observe(self, _observation):
            return []

        def query(self, _request):
            raise AssertionError("autonomous flush test must not receive a query")

        def flush(self):
            order.append(("flush", None))
            return [
                ModelEvent(
                    kind=EventKind.ANSWER,
                    logical_time_s=2.0,
                    text="event",
                    telemetry={"first_token_perf_ns": 2_500_000_000},
                )
            ]

        def close(self):
            order.append(("close", None))
            return []

    class Adapter:
        capabilities = AdapterCapabilities(
            state_lifetime="persistent",
            response_mode="autonomous",
            pacing="wall_clock",
        )

        def open(self, _context):
            return Session()

    record = ProactiveRecord(
        record_id="proactive-flush",
        source_id="proactive-flush",
        video_path="unused.mp4",
        instruction="Describe the event.",
        instruction_time_s=0.0,
        windows=[{"start_s": 1.5, "end_s": 1.6, "expected_answer": "event"}],
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.PROACTIVE,
        adapter="unused:Adapter",
        pacing="wall_clock",
        proactive_window_s=5.0,
    )

    result, events = _proactive_record(
        record, tmp_path / "unused.mp4", config, Adapter(), Adapter.capabilities
    )

    assert result["post_stream_response_grace_s"] == 4.5
    assert order.index(("flush", None)) < order.index(("wait", 6.5))
    assert order.index(("wait", 6.5)) < order.index(("close", None))
    answer = next(event for event in events if event["kind"] == "answer")
    assert answer["logical_time_s"] == 2.5
    assert answer["telemetry"]["within_evaluation_end"] is True


def test_committed_failed_record_is_terminal_and_finalized_bundle_is_immutable(synthetic_release):
    release, video_root = synthetic_release
    output = video_root / "resume-run"
    missing_root = video_root / "missing"
    missing_root.mkdir()
    first = resolve_config(
        release_dir=release,
        task=TaskName.QA,
        subset="tiny",
        adapter="trace_bench.adapters:TestDoubleAdapter",
        output_dir=output,
        video_root=str(missing_root),
        synthetic=True,
    )
    run(first)
    second = resolve_config(
        release_dir=release,
        task=TaskName.QA,
        subset="tiny",
        adapter="trace_bench.adapters:TestDoubleAdapter",
        output_dir=output,
        video_root=str(video_root),
        synthetic=True,
    )
    import pytest

    with pytest.raises(ValueError, match="immutable"):
        run(second)
    rows = RunBundle(output).records()
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    events = [
        line for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(events) == 1


def test_qa_query_sees_question_time_observation(monkeypatch, tmp_path):
    observation = Observation(
        timestamp_s=10.0,
        frame_index=7,
        rgb=np.zeros((2, 3, 3), dtype=np.uint8),
    )
    monkeypatch.setattr(
        "trace_bench.core.sample_video",
        lambda *_args, **_kwargs: SampledVideo(
            observations=[observation],
            source_fps=30.0,
            source_frame_count=1,
            video_sha256="synthetic",
            decoder="test",
        ),
    )

    class Session:
        def __init__(self):
            self.observed: list[int] = []

        def observe(self, item):
            assert item.observation_id == "frame-7"
            assert isinstance(item.arrival_perf_ns, int)
            assert item.visible_until_s == 10.0
            self.observed.append(item.frame_index)
            return [
                ModelEvent(
                    kind=EventKind.TELEMETRY,
                    logical_time_s=item.timestamp_s,
                    telemetry={
                        "frame_commit": True,
                        "commit_perf_ns": time.perf_counter_ns(),
                    },
                )
            ]

        def query(self, request):
            assert self.observed == [7]
            return [
                ModelEvent(
                    kind=EventKind.ANSWER,
                    logical_time_s=request.logical_time_s,
                    text="A",
                )
            ]

        def close(self):
            return []

    class Adapter:
        capabilities = AdapterCapabilities()

        def open(self, _context):
            return Session()

    record = QARecord(
        record_id="qa-order",
        source_id="qa-order",
        video_path="unused.mp4",
        question="Which?",
        options=["A. first", "B. second"],
        answer="A",
        question_time_s=10.0,
        evidence_anchor_s=10.0,
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.QA,
        adapter="unused:Adapter",
    )
    result, _events = _qa_record(record, tmp_path / "unused.mp4", config, Adapter())
    assert result["prediction"] == "A"
    import hashlib

    expected_hash = hashlib.sha256(result["qa_user_content"].encode("utf-8")).hexdigest()
    assert result["qa_user_content_sha256"] == expected_hash


def test_qa_query_is_queued_before_question_time_frame_for_batched_adapters(monkeypatch, tmp_path):
    observations = [
        Observation(timestamp_s=0.0, frame_index=0, rgb=np.zeros((2, 3, 3), dtype=np.uint8)),
        Observation(timestamp_s=1.0, frame_index=1, rgb=np.zeros((2, 3, 3), dtype=np.uint8)),
    ]
    monkeypatch.setattr(
        "trace_bench.core.sample_video",
        lambda *_args, **_kwargs: SampledVideo(
            observations=observations,
            source_fps=30.0,
            source_frame_count=2,
            video_sha256="synthetic",
            decoder="test",
        ),
    )

    class Session:
        def __init__(self):
            self.queued = False
            self.observed = []

        def query(self, request):
            self.queued = True
            assert self.observed == [0]
            return []

        def observe(self, item):
            self.observed.append(item.frame_index)
            if len(self.observed) == 2:
                assert self.queued is True
                return [
                    ModelEvent(
                        kind=EventKind.ANSWER,
                        logical_time_s=item.timestamp_s,
                        text="A",
                        telemetry={"query_dispatch_perf_ns": 1},
                    )
                ]
            return []

        def close(self):
            return []

    class Adapter:
        capabilities = AdapterCapabilities(qa_query_timing="before_observation_deferred")

        def open(self, _context):
            return Session()

    record = QARecord(
        record_id="qa-batched-order",
        source_id="qa-batched-order",
        video_path="unused.mp4",
        question="Which?",
        options=["A. first", "B. second"],
        answer="A",
        question_time_s=1.0,
        evidence_anchor_s=0.0,
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.QA,
        adapter="unused:Adapter",
    )
    result, _events = _qa_record(record, tmp_path / "unused.mp4", config, Adapter())
    assert result["prediction"] == "A"


def test_delayed_batch_commits_update_each_observation_event():
    class BatchSession:
        def __init__(self):
            self.items = []

        def observe(self, observation):
            self.items.append(observation)
            if len(self.items) < 2:
                return []
            committed = time.perf_counter_ns()
            return [
                ModelEvent(
                    kind=EventKind.TELEMETRY,
                    logical_time_s=observation.timestamp_s,
                    telemetry={
                        "frame_telemetry": [
                            {
                                "observation_id": f"frame-{item.frame_index}",
                                "commit_perf_ns": committed,
                            }
                            for item in self.items
                        ]
                    },
                )
            ]

    session = BatchSession()
    registry = {}
    first_events, first = _call_observe(
        session,
        Observation(0.0, 1, np.zeros((2, 2, 3), dtype=np.uint8)),
        scheduled_arrival_perf_ns=None,
        next_scheduled_arrival_perf_ns=None,
        observation_events=registry,
    )
    assert first_events == []
    assert first.telemetry["commit_perf_ns"] is None

    _second_events, second = _call_observe(
        session,
        Observation(1.0, 2, np.zeros((2, 2, 3), dtype=np.uint8)),
        scheduled_arrival_perf_ns=None,
        next_scheduled_arrival_perf_ns=None,
        observation_events=registry,
    )
    assert isinstance(first.telemetry["commit_perf_ns"], int)
    assert isinstance(second.telemetry["commit_perf_ns"], int)
    assert first.telemetry["commit_perf_ns"] == second.telemetry["commit_perf_ns"]


def test_keyboard_interrupt_checkpoint_resumes_without_duplicates(monkeypatch, tmp_path):
    records = [
        QARecord(
            record_id=f"qa:{index}",
            source_id=f"qa:{index}",
            video_path="unused.mp4",
            question="Which?",
            options=["A. first"],
            answer="A",
            question_time_s=1.0,
            evidence_anchor_s=0.0,
        )
        for index in (1, 2)
    ]

    class Manifest:
        release_id = "resume-test"
        schema_version = "test-v1"
        status = "private_provisional"
        files = {}

        @staticmethod
        def model_dump(mode="json"):
            del mode
            return {
                "release_id": "resume-test",
                "schema_version": "test-v1",
                "status": "private_provisional",
                "files": {},
            }

    release = SimpleNamespace(
        manifest=Manifest(),
        records=lambda _task, _subset: records,
    )
    adapter = SimpleNamespace(
        metadata={},
        capabilities=AdapterCapabilities(),
    )
    monkeypatch.setattr("trace_bench.core.load_release", lambda _path: release)
    monkeypatch.setattr("trace_bench.core.load_adapter", lambda *_args: adapter)
    monkeypatch.setattr(
        "trace_bench.core.validate_adapter",
        lambda *_args: AdapterCapabilities(),
    )
    monkeypatch.setattr(
        "trace_bench.core.build_preflight_snapshot",
        lambda *_args, **_kwargs: {
            "protocol": {},
            "data": {},
            "visual_input": {},
            "generation": {},
            "adapter": {},
            "telemetry_contract": {},
            "environment": {},
        },
    )

    calls: list[str] = []

    def interrupted(record, *_args):
        calls.append(record.record_id)
        if record.record_id == "qa:2":
            raise KeyboardInterrupt
        return (
            {"record_id": record.record_id, "status": "completed", "answer": "A"},
            [{"record_id": record.record_id, "kind": "answer", "text": "A"}],
        )

    monkeypatch.setattr("trace_bench.core._qa_record", interrupted)
    output = tmp_path / "resume"
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.QA,
        subset="tiny",
        adapter="unused:Adapter",
        output_dir=str(output),
        checkpoint_every_records=1,
    )
    with __import__("pytest").raises(KeyboardInterrupt):
        run(config)
    assert RunBundle(output).is_finalized() is False
    assert [row["record_id"] for row in RunBundle(output).records()] == ["qa:1"]

    monkeypatch.setattr(
        "trace_bench.core._qa_record",
        lambda record, *_args: (
            {"record_id": record.record_id, "status": "completed", "answer": "A"},
            [{"record_id": record.record_id, "kind": "answer", "text": "A"}],
        ),
    )
    run(config)
    assert calls == ["qa:1", "qa:2"]
    assert [row["record_id"] for row in RunBundle(output).records()] == ["qa:1", "qa:2"]
    event_ids = [event["record_id"] for event in RunBundle(output).events()]
    assert event_ids == ["qa:1", "qa:2"]


def test_fatal_adapter_error_checkpoints_and_does_not_finalize(monkeypatch, tmp_path):
    records = [
        QARecord(
            record_id=f"qa:{index}",
            source_id=f"qa:{index}",
            video_path="unused.mp4",
            question="Which?",
            options=["A. first"],
            answer="A",
            question_time_s=1.0,
            evidence_anchor_s=0.0,
        )
        for index in (1, 2)
    ]

    class Manifest:
        release_id = "fatal-test"
        schema_version = "test-v1"
        status = "private_provisional"
        files = {}

        @staticmethod
        def model_dump(mode="json"):
            del mode
            return {
                "release_id": "fatal-test",
                "schema_version": "test-v1",
                "status": "private_provisional",
                "files": {},
            }

    release = SimpleNamespace(
        manifest=Manifest(),
        records=lambda _task, _subset: records,
    )
    adapter = SimpleNamespace(
        metadata={},
        capabilities=AdapterCapabilities(),
    )
    monkeypatch.setattr("trace_bench.core.load_release", lambda _path: release)
    monkeypatch.setattr("trace_bench.core.load_adapter", lambda *_args: adapter)
    monkeypatch.setattr(
        "trace_bench.core.validate_adapter",
        lambda *_args: AdapterCapabilities(),
    )
    monkeypatch.setattr(
        "trace_bench.core.build_preflight_snapshot",
        lambda *_args, **_kwargs: {
            "protocol": {},
            "data": {},
            "visual_input": {},
            "generation": {},
            "adapter": {},
            "telemetry_contract": {},
            "environment": {},
        },
    )

    def interrupted(record, *_args):
        if record.record_id == "qa:2":
            raise FatalEvaluationError("ThinkStream model process became unusable after a fatal CUDA error")
        return (
            {"record_id": record.record_id, "status": "completed", "answer": "A"},
            [{"record_id": record.record_id, "kind": "answer", "text": "A"}],
        )

    monkeypatch.setattr("trace_bench.core._qa_record", interrupted)
    output = tmp_path / "fatal-run"
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.QA,
        subset="tiny",
        adapter="unused:Adapter",
        output_dir=str(output),
        checkpoint_every_records=1,
    )
    with pytest.raises(FatalEvaluationError, match="fatal CUDA error"):
        run(config)
    bundle = RunBundle(output)
    assert bundle.is_finalized() is False
    assert [row["record_id"] for row in bundle.records()] == ["qa:1"]
    with pytest.raises(ValueError, match="not finalized"):
        bundle.validate()


def test_proactive_close_answer_receives_response_latency():
    record = ProactiveRecord(
        record_id="proactive-close",
        source_id="proactive-close",
        video_path="unused.mp4",
        instruction="Describe changes",
        instruction_time_s=0.0,
        deadline_s=2.0,
        windows=[{"start_s": 1.0, "end_s": 2.0, "expected_answer": "change"}],
    )
    events = [
        ModelEvent(
            kind=EventKind.OBSERVATION,
            logical_time_s=1.0,
            telemetry={"arrival_perf_ns": 1_000_000_000},
        ),
        ModelEvent(
            kind=EventKind.ANSWER,
            logical_time_s=1.5,
            text="change",
            telemetry={"arrival_perf_ns": 1_250_000_000},
        ),
    ]
    _annotate_proactive_response_latency(events, record)
    assert events[1].telemetry["proactive_response_latency_ms"] == 250.0


def test_proactive_response_latency_uses_half_open_window():
    record = ProactiveRecord(
        record_id="proactive-boundary",
        source_id="proactive-boundary",
        video_path="unused.mp4",
        instruction="Describe changes",
        instruction_time_s=0.0,
        deadline_s=3.0,
        windows=[{"start_s": 1.0, "end_s": 2.0, "expected_answer": "change"}],
    )
    events = [
        ModelEvent(
            kind=EventKind.OBSERVATION,
            logical_time_s=1.0,
            telemetry={"arrival_perf_ns": 1_000_000_000},
        ),
        ModelEvent(
            kind=EventKind.ANSWER,
            logical_time_s=6.0,
            text="change",
            telemetry={"arrival_perf_ns": 1_250_000_000},
        ),
    ]
    _annotate_proactive_response_latency(events, record)
    assert "proactive_response_latency_ms" not in events[1].telemetry


def test_qa_prediction_ignores_pre_query_autonomous_answers():
    events = [
        ModelEvent(kind=EventKind.ANSWER, logical_time_s=1.0, text="B"),
        ModelEvent(
            kind=EventKind.ANSWER,
            logical_time_s=2.0,
            text="A",
            telemetry={"query_dispatch_perf_ns": 100},
        ),
    ]
    assert _last_prediction(events) == "A"
    assert _last_prediction(events[:1]) == ""


def test_wall_clock_response_uses_core_completion_fallback_without_faking_first_token():
    clock = _ObservationClock([], "wall_clock")
    clock.video_start_s = 0.0
    clock.run_start_perf_ns = 1_000_000_000
    event = ModelEvent(
        kind=EventKind.ANSWER,
        logical_time_s=0.0,
        text="event",
        telemetry={"core_event_receive_perf_ns": 3_000_000_000},
    )
    _align_response_events_to_stream_clock(
        [event], clock, video_end_s=10.0, evaluation_end_s=5.0
    )
    assert event.logical_time_s == 2.0
    assert event.telemetry["evaluation_time_source"] == (
        "core_event_receive_perf_ns_completion_fallback"
    )
    assert event.telemetry["first_token_timing_observed"] is False
    assert event.telemetry.get("first_token_perf_ns") is None


def test_polling_query_at_frame_timestamp_observes_that_frame_first(monkeypatch, tmp_path):
    observations = [
        Observation(
            timestamp_s=float(index),
            frame_index=index,
            rgb=np.zeros((2, 3, 3), dtype=np.uint8),
        )
        for index in range(2)
    ]
    monkeypatch.setattr(
        "trace_bench.core.sample_video",
        lambda *_args, **_kwargs: SampledVideo(
            observations=observations,
            source_fps=1.0,
            source_frame_count=2,
            video_sha256="synthetic",
            decoder="test",
        ),
    )
    monkeypatch.setattr("trace_bench.core.video_duration_s", lambda _path: 1.0)
    calls = []

    class Session:
        def observe(self, observation):
            calls.append(("observe", observation.timestamp_s))
            return []

        def query(self, request):
            calls.append(("query", request.logical_time_s))
            return []

        def close(self):
            return []

    class Adapter:
        capabilities = AdapterCapabilities(response_mode="polling")

        def open(self, _context):
            return Session()

    record = ProactiveRecord(
        record_id="polling-order",
        source_id="polling-order",
        video_path="unused.mp4",
        instruction="Watch.",
        instruction_time_s=1.0,
        windows=[{"start_s": 1.0, "end_s": 2.0, "expected_answer": "event"}],
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.PROACTIVE,
        adapter="unused:Adapter",
        proactive_step_s=5.0,
    )
    _proactive_record(
        record, tmp_path / "unused.mp4", config, Adapter(), Adapter.capabilities
    )
    assert calls.index(("observe", 1.0)) < calls.index(("query", 1.0))


def test_proactive_history_window_is_independent_from_response_tolerance(
    monkeypatch, tmp_path
):
    sampled = {}

    def sample_stub(_path, timestamps, **_kwargs):
        sampled["timestamps"] = timestamps
        return SampledVideo(
            observations=[],
            source_fps=1.0,
            source_frame_count=0,
            video_sha256="synthetic",
            decoder="test",
        )

    monkeypatch.setattr("trace_bench.core.sample_video", sample_stub)
    monkeypatch.setattr("trace_bench.core.video_duration_s", lambda _path: 30.0)

    class Session:
        def observe(self, _observation):
            return []

        def close(self):
            return []

    class Adapter:
        capabilities = AdapterCapabilities(
            state_lifetime="persistent", response_mode="autonomous"
        )

        def open(self, _context):
            return Session()

    record = ProactiveRecord(
        record_id="history-independent",
        source_id="history-independent",
        video_path="unused.mp4",
        instruction="Watch.",
        instruction_time_s=10.0,
        windows=[{"start_s": 12.0, "end_s": 13.0, "expected_answer": "event"}],
    )
    config = RunConfig(
        release_dir=str(tmp_path),
        task=TaskName.PROACTIVE,
        adapter="unused:Adapter",
        proactive_history_window_s=5.0,
        proactive_window_s=10.0,
    )
    result, _ = _proactive_record(
        record, tmp_path / "unused.mp4", config, Adapter(), Adapter.capabilities
    )
    assert sampled["timestamps"][0] == 5.0
    assert result["proactive_history_window_s"] == 5.0
