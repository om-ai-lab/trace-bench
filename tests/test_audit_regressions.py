from pathlib import Path
from types import SimpleNamespace

import pytest

from open_stream_bench import core
from open_stream_bench.models import ModelEvent, QARecord, RunConfig
from open_stream_bench.scoring import assemble_response_episodes, extract_choice


@pytest.mark.parametrize("text", ["The answer is B", "B. on the desk", "I saw a cat",
                                  "A or B"])
def test_qa_requires_only_actual_label(text):
    assert extract_choice(text) is None
    assert extract_choice(" B ", {"B"}) == "B"
    assert extract_choice("B", {"A"}) is None
    assert extract_choice("A", set()) is None
    assert extract_choice(": B") == "B"
    assert extract_choice("B.") == "B"


def test_drain_can_finish_but_not_start_or_reopen_response():
    clock = core._ObservationClock([0], "wall_clock")
    clock.run_start_perf_ns = 0
    events = [
        ModelEvent(kind="answer", logical_time_s=4, text="She picks", response_id="r",
                   text_mode="delta", telemetry={"first_token_perf_ns": 4_000_000_000}),
        ModelEvent(kind="answer", logical_time_s=6, text=" it up", response_id="r",
                   text_mode="delta", is_final=True,
                   telemetry={"first_token_perf_ns": 6_000_000_000}),
        ModelEvent(kind="answer", logical_time_s=7, text="new", response_id="r",
                   text_mode="delta", telemetry={"first_token_perf_ns": 7_000_000_000}),
    ]
    core._align_response_events_to_stream_clock(events, clock, video_end_s=4, evaluation_end_s=5)
    assert [e["text"] for e in assemble_response_episodes(
        [e.model_dump(mode="json") for e in events]
    )] == ["She picks it up"]
    events[1].telemetry["shutdown_drain"] = True
    assert [e["text"] for e in assemble_response_episodes(
        [e.model_dump(mode="json") for e in events[:2]]
    )] == ["She picks"]


def test_record_exception_closes_and_preserves_partial_events(monkeypatch):
    class Session:
        closed = False

        def close(self):
            self.closed = True
            return [ModelEvent(kind="telemetry", logical_time_s=0, telemetry={"calls": 1})]

    session = Session()
    adapter = SimpleNamespace(open=lambda context: session,
                              capabilities=SimpleNamespace(qa_query_timing="after_observation"))
    monkeypatch.setattr(core, "sample_video", lambda *a, **kw: SimpleNamespace(observations=[]))

    def fail(*args):
        raise ValueError("simulated observation failure")

    monkeypatch.setattr(core, "_iterate_observations", fail)
    record = QARecord(record_id="audit", source_id="audit", video_path="fake.mp4",
                      question="Which?", options=["A. one", "B. two"], answer="A",
                      question_time_s=1, evidence_anchor_s=0)
    config = RunConfig(release_dir="unused", task="qa", adapter="unused")
    result, events = core._qa_record(record, Path("fake.mp4"), config, adapter)
    assert session.closed
    assert result["status"] == "failed"
    assert events[0]["telemetry"]["calls"] == 1
    assert "simulated observation failure" in result["failed_reason"]


def test_explicit_video_root_overrides_cwd(monkeypatch, tmp_path):
    (tmp_path / "video.mp4").touch()
    monkeypatch.chdir(tmp_path)
    assert core._video_path("video.mp4", "/explicit") == Path("/explicit/video.mp4")


def test_query_clock_includes_delivery_backlog(monkeypatch, tmp_path):
    import numpy as np
    from open_stream_bench.models import Observation
    from open_stream_bench.sampling import SampledVideo

    observation = Observation(timestamp_s=1, frame_index=1,
                              rgb=np.zeros((2, 2, 3), dtype=np.uint8))
    monkeypatch.setattr(core, "sample_video", lambda *a, **kw: SampledVideo(
        observations=[observation], source_fps=1, source_frame_count=2,
        video_sha256="test", decoder="test"))
    monkeypatch.setattr(core, "_iterate_observations",
                        lambda observations, pacing, callback: callback(observations[0], 100, None))

    class Session:
        def observe(self, observation):
            return []

        def query(self, query):
            return [ModelEvent(kind="answer", text="A", logical_time_s=1)]

        def close(self):
            return []

    adapter = SimpleNamespace(open=lambda context: Session(),
                              capabilities=SimpleNamespace(qa_query_timing="after_observation"))
    record = QARecord(record_id="clock", source_id="clock", video_path="fake.mp4",
                      question="Which?", options=["A. one"], answer="A",
                      question_time_s=1, evidence_anchor_s=0)
    config = RunConfig(release_dir="unused", task="qa", adapter="unused", pacing="wall_clock")
    _, events = core._qa_record(record, tmp_path / "fake.mp4", config, adapter)
    answer = next(e for e in events if e["kind"] == "answer")
    assert answer["telemetry"]["semantic_query_arrival_perf_ns"] == 100
    assert answer["telemetry"]["query_dispatch_perf_ns"] > 100
