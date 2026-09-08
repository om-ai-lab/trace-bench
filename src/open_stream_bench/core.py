"""Local QA and Proactive Response execution Core."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .adapters import Adapter, AdapterSession, load_adapter, validate_adapter
from .bundle import RunBundle
from .config import stable_hash
from .data import load_release
from .models import (
    AdapterCapabilities,
    EventKind,
    FatalEvaluationError,
    ModelEvent,
    Observation,
    ProactiveRecord,
    QARecord,
    QueryRequest,
    RecordContext,
    RunConfig,
    TaskName,
)
from .preflight import build_preflight_snapshot
from .prompts import build_qa_prompt
from .sampling import MediaError, sample_video, timestamp_plan, video_duration_s
from .scoring import (
    JudgeRouter,
    _proactive_window_specs,
    assess_official_eligibility,
    assemble_response_episodes,
    judge_from_settings,
    prediction_from_query_events,
    score_records,
    summarize_telemetry,
)


def _video_path(record_path: str, video_root: str | None) -> Path:
    candidate = Path(record_path)
    if candidate.is_absolute() or candidate.is_file():
        return candidate
    if video_root:
        return Path(video_root) / record_path
    return candidate


def _sha256_text(value: str) -> str:
    """Hash the exact UTF-8 prompt bytes recorded in the Run Bundle."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event_payload(record_id: str, event: ModelEvent) -> dict[str, Any]:
    payload = event.model_dump(mode="json")
    payload["record_id"] = record_id
    return payload


def _last_prediction(events: list[ModelEvent]) -> str:
    event_rows = [event.model_dump(mode="json") for event in events]
    assembled = prediction_from_query_events(event_rows)
    if assembled is not None:
        return assembled
    for event in reversed(events):
        if (
            event.kind == EventKind.ANSWER
            and isinstance(event.telemetry.get("query_dispatch_perf_ns"), int)
            and event.text.strip()
            and event.text.strip().upper() != "WAIT"
        ):
            return event.text
    return ""


def _failure_reason(events: list[ModelEvent]) -> str | None:
    failures = [
        event.failed_reason
        for event in events
        if event.kind == EventKind.FAILURE and event.failed_reason
    ]
    return "; ".join(str(value) for value in failures) if failures else None


def _annotate_proactive_response_latency(
    events: list[ModelEvent], record: ProactiveRecord, proactive_window_s: float = 5.0
) -> None:
    event_rows = [event.model_dump(mode="json") for event in events]
    episodes = assemble_response_episodes(event_rows)
    observations = [
        (index, event)
        for index, event in enumerate(events)
        if event.kind == EventKind.OBSERVATION
    ]
    window_specs = _proactive_window_specs(record.model_dump(mode="json"), proactive_window_s)
    assigned_episodes: set[int] = set()
    for episode in episodes:
        start_s = float(episode["start_video_time_s"])
        window_index = next(
            (
                index
                for index, window in enumerate(window_specs)
                if index not in assigned_episodes
                and window["start_s"] <= start_s < window["end_s"]
            ),
            None,
        )
        if window_index is None:
            continue
        assigned_episodes.add(window_index)
        window = window_specs[window_index]
        trigger = next(
            (
                event
                for _index, event in observations
                if event.logical_time_s >= window["start_s"] - 1e-9
                and isinstance(event.telemetry.get("arrival_perf_ns"), int)
            ),
            None,
        )
        source_index = (episode.get("source_event_indices") or [None])[0]
        answer = events[source_index] if isinstance(source_index, int) else None
        if trigger is None or answer is None:
            continue
        trigger_ns = int(trigger.telemetry["arrival_perf_ns"])
        answer_ns = episode.get("scoring_perf_ns")
        if not isinstance(answer_ns, int):
            answer_ns = episode.get("first_token_perf_ns")
        if not isinstance(answer_ns, int):
            answer_ns = answer.telemetry.get("core_event_receive_perf_ns")
        if not isinstance(answer_ns, int):
            # Compatibility for already persisted v3 events. New Core events
            # always carry core_event_receive_perf_ns.
            answer_ns = answer.telemetry.get("arrival_perf_ns")
        if not isinstance(answer_ns, int) or answer_ns < trigger_ns:
            continue
        answer.telemetry["proactive_window_index"] = window_index
        answer.telemetry["proactive_trigger_video_time_s"] = trigger.logical_time_s
        answer.telemetry["proactive_trigger_arrival_perf_ns"] = trigger_ns
        answer.telemetry["proactive_response_arrival_perf_ns"] = answer_ns
        answer.telemetry["proactive_response_latency_ms"] = (answer_ns - trigger_ns) / 1_000_000


def _context(
    record: QARecord | ProactiveRecord,
    task: TaskName,
    path: Path,
    start_s: float,
    end_s: float,
    config: RunConfig,
) -> RecordContext:
    return RecordContext(
        record=record,
        task=task,
        video_path=str(path),
        evidence_start_s=start_s,
        evidence_end_s=end_s,
        config=config,
    )


class _ObservationClock:
    def __init__(self, timestamps: list[float], pacing: str):
        self.pacing = pacing
        self.video_start_s = timestamps[0] if timestamps else 0.0
        self.run_start_perf_ns = time.perf_counter_ns()

    def wait(self, video_time_s: float) -> int | None:
        if self.pacing != "wall_clock":
            return None
        scheduled = self.scheduled_perf_ns(video_time_s)
        remaining_ns = scheduled - time.perf_counter_ns()
        if remaining_ns > 0:
            time.sleep(remaining_ns / 1_000_000_000)
        return scheduled

    def scheduled_perf_ns(self, video_time_s: float) -> int:
        return self.run_start_perf_ns + int(
            max(0.0, video_time_s - self.video_start_s) * 1_000_000_000
        )

    def video_time_for_perf_ns(self, perf_ns: int) -> float:
        return self.video_start_s + max(0, perf_ns - self.run_start_perf_ns) / 1_000_000_000


def _proactive_evaluation_end_s(
    record: ProactiveRecord,
    proactive_window_s: float,
    video_end_s: float | None,
) -> float:
    """Return the bounded Proactive evaluation endpoint.

    The source-video duration is provenance and only clamps the evidence
    interval when the source ends before the final GT window.  It must not
    extend a record past the last strict response window: otherwise a long
    no-score tail is fed to the model and can change its state/cache.
    """
    windows = _proactive_window_specs(record.model_dump(mode="json"), proactive_window_s)
    # A malformed record without GT windows must not fall back to the source
    # duration: that would reintroduce the historical full-video tail. Keep
    # only the pre-instruction history bounded by the instruction boundary.
    return max(
        (float(window["end_s"]) for window in windows),
        default=max(0.0, float(record.instruction_time_s)),
    )


def _align_response_events_to_stream_clock(
    events: list[ModelEvent],
    clock: _ObservationClock,
    *,
    video_end_s: float | None,
    evaluation_end_s: float,
) -> None:
    """Map an observed response boundary onto the wall-clock stream axis.

    First-token time is preferred. If an adapter cannot expose it, Core receipt
    of the completed event is a conservative, directly observed fallback. The
    fallback never pretends to be first-token telemetry.
    """

    if clock.pacing != "wall_clock":
        return
    for event in events:
        if event.kind != EventKind.ANSWER:
            continue
        response_ns = event.telemetry.get("first_token_perf_ns")
        time_source = "first_token_perf_ns_wall_clock"
        if not isinstance(response_ns, int):
            if event.telemetry.get("session_close_event") is True:
                event.telemetry.setdefault("adapter_logical_time_s", event.logical_time_s)
                event.telemetry["evaluation_time_source"] = "unobservable_close_time"
                event.telemetry["within_evaluation_end"] = False
                event.telemetry["eligible_for_scoring"] = False
                event.telemetry.setdefault("suppression_reason", "unobservable_close_time")
                event.logical_time_s = evaluation_end_s
                continue
            response_ns = event.telemetry.get("core_event_receive_perf_ns")
            if not isinstance(response_ns, int):
                event.telemetry.setdefault("adapter_logical_time_s", event.logical_time_s)
                event.telemetry["evaluation_time_source"] = "missing_observable_response_time"
                event.telemetry["eligible_for_scoring"] = False
                event.telemetry.setdefault(
                    "suppression_reason", "missing_observable_response_time"
                )
                continue
            time_source = "core_event_receive_perf_ns_completion_fallback"
            event.telemetry["first_token_timing_observed"] = False
        else:
            event.telemetry["first_token_timing_observed"] = True
        mapped_time_s = clock.video_time_for_perf_ns(response_ns)
        event.telemetry.setdefault("adapter_logical_time_s", event.logical_time_s)
        event.telemetry["evaluation_time_source"] = time_source
        event.telemetry["response_scoring_perf_ns"] = response_ns
        event.telemetry["evaluation_time_s"] = mapped_time_s
        event.telemetry["post_stream_response"] = (
            mapped_time_s > video_end_s + 1e-9 if video_end_s is not None else None
        )
        event.telemetry["within_evaluation_end"] = mapped_time_s < evaluation_end_s
        if mapped_time_s >= evaluation_end_s - 1e-9:
            event.telemetry["eligible_for_scoring"] = False
            event.telemetry.setdefault("suppression_reason", "after_evaluation_end")
        event.logical_time_s = mapped_time_s


def _call_query(
    session: AdapterSession,
    request: QueryRequest,
) -> list[ModelEvent]:
    dispatch_ns = time.perf_counter_ns()
    request.dispatch_perf_ns = dispatch_ns
    events = session.query(request)
    completion_ns = time.perf_counter_ns()
    for event in events:
        event.telemetry.setdefault("core_event_receive_perf_ns", completion_ns)
        event.telemetry.setdefault("query_dispatch_perf_ns", dispatch_ns)
        event.telemetry.setdefault("response_completion_perf_ns", completion_ns)
        event.telemetry.setdefault("response_total_ms", (completion_ns - dispatch_ns) / 1_000_000)
    return events


def _reconcile_observation_commits(
    events: list[ModelEvent],
    observation_events: dict[str, ModelEvent],
    *,
    fallback_observation_id: str | None = None,
) -> None:
    commits: dict[str, int] = {}
    for event in events:
        event_telemetry = event.telemetry
        frame_rows = event_telemetry.get("frame_telemetry", [])
        if isinstance(frame_rows, list):
            for row in frame_rows:
                if not isinstance(row, dict):
                    continue
                row_id = row.get("observation_id")
                commit_ns = row.get("commit_perf_ns")
                if isinstance(row_id, str) and isinstance(commit_ns, int):
                    commits[row_id] = max(commits.get(row_id, commit_ns), commit_ns)
        commit_ns = event_telemetry.get("commit_perf_ns")
        if not isinstance(commit_ns, int):
            continue
        event_observation_id = event_telemetry.get("observation_id")
        if isinstance(event_observation_id, str):
            commits[event_observation_id] = max(
                commits.get(event_observation_id, commit_ns), commit_ns
            )
        elif event_telemetry.get("frame_commit") is True and fallback_observation_id:
            commits[fallback_observation_id] = max(
                commits.get(fallback_observation_id, commit_ns), commit_ns
            )

    for committed_id, commit_ns in commits.items():
        committed_event = observation_events.get(committed_id)
        if committed_event is None:
            continue
        frame = committed_event.telemetry
        frame["commit_perf_ns"] = commit_ns
        frame["frame_processing_ms"] = (commit_ns - int(frame["arrival_perf_ns"])) / 1_000_000
        scheduled_ns = frame.get("scheduled_arrival_perf_ns")
        frame["frame_lag_ms"] = (
            max(0, commit_ns - scheduled_ns) / 1_000_000 if isinstance(scheduled_ns, int) else None
        )
        deadline_ns = frame.get("frame_deadline_perf_ns")
        frame["on_time"] = commit_ns <= deadline_ns if isinstance(deadline_ns, int) else None


def _call_observe(
    session: AdapterSession,
    observation: Observation,
    *,
    scheduled_arrival_perf_ns: int | None,
    next_scheduled_arrival_perf_ns: int | None,
    observation_events: dict[str, ModelEvent],
) -> tuple[list[ModelEvent], ModelEvent]:
    arrival_ns = time.perf_counter_ns()
    observation_id = observation.observation_id or f"frame-{observation.frame_index}"
    observation.observation_id = observation_id
    observation.scheduled_arrival_perf_ns = scheduled_arrival_perf_ns
    observation.arrival_perf_ns = arrival_ns
    observation.visible_until_s = observation.timestamp_s
    events = session.observe(observation)
    receive_ns = time.perf_counter_ns()
    for event in events:
        event.telemetry.setdefault("arrival_perf_ns", arrival_ns)
        event.telemetry.setdefault("core_event_receive_perf_ns", receive_ns)
    height, width = observation.rgb.shape[:2]
    telemetry = {
        "observation_id": observation_id,
        "frame_index": observation.frame_index,
        "submitted_width": int(width),
        "submitted_height": int(height),
        "scheduled_arrival_perf_ns": scheduled_arrival_perf_ns,
        "arrival_perf_ns": arrival_ns,
        "commit_perf_ns": None,
        "frame_processing_ms": None,
        "frame_lag_ms": None,
        "frame_deadline_perf_ns": next_scheduled_arrival_perf_ns,
        "on_time": None,
        "core_delivered_frame_count": 1,
    }
    observation_event = ModelEvent(
        kind=EventKind.OBSERVATION,
        logical_time_s=observation.timestamp_s,
        telemetry=telemetry,
    )
    observation_events[observation_id] = observation_event

    _reconcile_observation_commits(
        events,
        observation_events,
        fallback_observation_id=observation_id,
    )
    return events, observation_event


def _iterate_observations(
    observations: list[Observation],
    pacing: str,
    callback: Callable[[Observation, int | None, int | None], None],
) -> _ObservationClock:
    timestamps = [observation.timestamp_s for observation in observations]
    clock = _ObservationClock(timestamps, pacing)
    for index, observation in enumerate(observations):
        scheduled = clock.wait(observation.timestamp_s)
        next_scheduled = None
        if pacing == "wall_clock" and index + 1 < len(observations):
            next_scheduled = clock.scheduled_perf_ns(observations[index + 1].timestamp_s)
        callback(observation, scheduled, next_scheduled)
    return clock


def _qa_record(
    record: QARecord,
    video_path: Path,
    config: RunConfig,
    adapter: Adapter,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start_s = max(0.0, record.evidence_anchor_s - config.qa_window_s)
    end_s = record.question_time_s
    timestamps = timestamp_plan(start_s, end_s, config.stream_fps)
    sampled = sample_video(video_path, timestamps, max_width=config.max_width)
    session = adapter.open(_context(record, TaskName.QA, video_path, start_s, end_s, config))
    qa_user_content = build_qa_prompt(record.question, record.options)
    events: list[ModelEvent] = []
    observation_events: dict[str, ModelEvent] = {}
    query_injected = False
    query_dispatch_count = 0
    semantic_query_arrival_ns: int | None = None

    qa_query_timing = getattr(adapter.capabilities, "qa_query_timing", "after_observation")

    def consume(
        observation: Observation,
        scheduled: int | None,
        next_scheduled: int | None,
    ) -> None:
        nonlocal query_injected, query_dispatch_count, semantic_query_arrival_ns
        # Queue the QA request before delivering the question-time frame.  An
        # adapter may batch observations (ThinkStream consumes two Core
        # frames per model call); dispatching after an even-sized final chunk
        # would leave the request in an empty buffer and produce no answer.
        # The queued request is still evaluated only with observations through
        # this timestamp, so no future frame becomes visible.
        query_events: list[ModelEvent] = []
        if (
            semantic_query_arrival_ns is None
            and observation.timestamp_s >= record.question_time_s - 1e-9
        ):
            semantic_query_arrival_ns = time.perf_counter_ns()
        if (
            qa_query_timing == "before_observation_deferred"
            and not query_injected
            and observation.timestamp_s >= record.question_time_s - 1e-9
        ):
            query_dispatch_count += 1
            query_events = _call_query(
                session,
                QueryRequest(
                    kind="qa",
                    logical_time_s=record.question_time_s,
                    text=qa_user_content,
                ),
            )
            for event in query_events:
                event.telemetry.setdefault(
                    "semantic_query_arrival_perf_ns", semantic_query_arrival_ns
                )
            query_injected = True
        model_events, observation_event = _call_observe(
            session,
            observation,
            scheduled_arrival_perf_ns=scheduled,
            next_scheduled_arrival_perf_ns=next_scheduled,
            observation_events=observation_events,
        )
        events.append(observation_event)
        if semantic_query_arrival_ns is not None:
            for event in model_events:
                if isinstance(event.telemetry.get("query_dispatch_perf_ns"), int):
                    event.telemetry.setdefault(
                        "semantic_query_arrival_perf_ns", semantic_query_arrival_ns
                    )
        events.extend(model_events)
        _reconcile_observation_commits(query_events, observation_events)
        events.extend(query_events)
        if (
            qa_query_timing != "before_observation_deferred"
            and not query_injected
            and observation.timestamp_s >= record.question_time_s - 1e-9
        ):
            query_dispatch_count += 1
            query_events = _call_query(
                session,
                QueryRequest(
                    kind="qa",
                    logical_time_s=record.question_time_s,
                    text=qa_user_content,
                ),
            )
            for event in query_events:
                event.telemetry.setdefault(
                    "semantic_query_arrival_perf_ns", semantic_query_arrival_ns
                )
            _reconcile_observation_commits(query_events, observation_events)
            events.extend(query_events)
            query_injected = True

    _iterate_observations(sampled.observations, config.pacing, consume)
    if not query_injected:
        semantic_query_arrival_ns = time.perf_counter_ns()
        query_dispatch_count += 1
        query_events = _call_query(
            session,
            QueryRequest(
                kind="qa",
                logical_time_s=record.question_time_s,
                text=qa_user_content,
            ),
        )
        for event in query_events:
            event.telemetry.setdefault(
                "semantic_query_arrival_perf_ns", semantic_query_arrival_ns
            )
        _reconcile_observation_commits(query_events, observation_events)
        events.extend(query_events)
    close_events = session.close()
    close_receive_ns = time.perf_counter_ns()
    for event in close_events:
        event.telemetry.setdefault("session_close_event", True)
        event.telemetry.setdefault("core_event_receive_perf_ns", close_receive_ns)
    _reconcile_observation_commits(close_events, observation_events)
    events.extend(close_events)
    failure = _failure_reason(events)
    prompt_metadata_rows = [
        event.telemetry.get("prompt_metadata")
        for event in events
        if isinstance(event.telemetry.get("prompt_metadata"), dict)
    ]
    prompt_metadata = next(
        (
            row
            for row in prompt_metadata_rows
            if row.get("query_kind") == "qa"
        ),
        prompt_metadata_rows[0] if prompt_metadata_rows else None,
    )
    output = {
        "record_id": record.record_id,
        "task": "qa",
        "status": "failed" if failure else "completed",
        "video_path": record.video_path,
        "task_type": record.task_type,
        "memory_length": record.memory_length,
        "question": record.question,
        "options": record.options,
        "answer": record.answer,
        "qa_user_content": qa_user_content,
        "qa_user_content_sha256": _sha256_text(qa_user_content),
        "qa_user_content_policy": "byte_identical_core_prompt",
        "qa_template_policy": "mechanical_role_control_serialization_only",
        "qa_prompt_metadata": prompt_metadata,
        "qa_query_count": query_dispatch_count,
        "qa_query_policy": "exactly_one_core_dispatch",
        "qa_semantic_query_arrival_perf_ns": semantic_query_arrival_ns,
        "qa_ttft_start_policy": "core_semantic_query_arrival",
        "question_time_s": record.question_time_s,
        "evidence_anchor_s": record.evidence_anchor_s,
        "evidence_start_s": start_s,
        "evidence_end_s": end_s,
        "prediction": _last_prediction(events),
        "failed_reason": failure,
        "observation_count": len(sampled.observations),
        "observation_timestamps": timestamps,
        "resolved_frame_indices": [observation.frame_index for observation in sampled.observations],
        "source_fps": sampled.source_fps,
        "video_sha256": sampled.video_sha256,
        "decoder": sampled.decoder,
    }
    return output, [_event_payload(record.record_id, event) for event in events]


def _proactive_record(
    record: ProactiveRecord,
    video_path: Path,
    config: RunConfig,
    adapter: Adapter,
    capabilities: AdapterCapabilities,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start_s = max(0.0, record.instruction_time_s - config.proactive_history_window_s)
    try:
        video_end_s = video_duration_s(video_path)
    except MediaError:
        # Synthetic unit tests historically supplied a fake sampler and a
        # source deadline. Keep that test-only fallback; real runs may also
        # proceed with an unknown metadata duration without scanning the tail.
        if config.synthetic and record.deadline_s is not None:
            video_end_s = record.deadline_s
        else:
            raise
    evaluation_end_s = _proactive_evaluation_end_s(
        record, config.proactive_window_s, video_end_s
    )
    # Feed only the legal evidence needed to cover the final strict window.
    # If the source ends first, the wall-clock autonomous grace below may
    # finish that window without inventing or repeating observations.
    end_s = max(
        start_s,
        min(video_end_s, evaluation_end_s) if video_end_s is not None else evaluation_end_s,
    )
    post_stream_response_grace_s = (
        max(0.0, evaluation_end_s - video_end_s) if video_end_s is not None else 0.0
    )
    timestamps = timestamp_plan(start_s, end_s, config.stream_fps)
    sampled = sample_video(video_path, timestamps, max_width=config.max_width)
    session = adapter.open(_context(record, TaskName.PROACTIVE, video_path, start_s, end_s, config))
    events: list[ModelEvent] = []
    observation_events: dict[str, ModelEvent] = {}
    # Autonomous adapters receive the instruction through RecordContext and
    # decide when to emit responses from observations.  Injecting the
    # instruction as a polling query as well leaves a pending query in an
    # autonomous session; the adapter may then try to consume it at close()
    # with observations that are legitimately later than the instruction.
    # Polling/query adapters still receive the instruction-time query.
    query_times = [] if capabilities.response_mode == "autonomous" else [
        record.instruction_time_s
    ]
    if capabilities.response_mode != "autonomous":
        current = record.instruction_time_s + config.proactive_step_s
        while current <= end_s + 1e-9:
            query_times.append(round(current, 9))
            current += config.proactive_step_s
    query_index = 0

    def dispatch_query(query_time: float) -> None:
        nonlocal query_index
        query_events = _call_query(
            session,
            QueryRequest(
                kind="proactive",
                logical_time_s=query_time,
                text=record.instruction,
            ),
        )
        _reconcile_observation_commits(query_events, observation_events)
        events.extend(query_events)
        query_index += 1

    def consume(
        observation: Observation,
        scheduled: int | None,
        next_scheduled: int | None,
    ) -> None:
        nonlocal query_index
        # Queries strictly before this observation must not see the future
        # frame. A query exactly at the frame timestamp is dispatched after the
        # frame so evidence visible at t is consistently <= t.
        while (
            query_index < len(query_times)
            and query_times[query_index] < observation.timestamp_s - 1e-9
        ):
            dispatch_query(query_times[query_index])
        model_events, observation_event = _call_observe(
            session,
            observation,
            scheduled_arrival_perf_ns=scheduled,
            next_scheduled_arrival_perf_ns=next_scheduled,
            observation_events=observation_events,
        )
        events.append(observation_event)
        events.extend(model_events)
        while (
            query_index < len(query_times)
            and query_times[query_index] <= observation.timestamp_s + 1e-9
        ):
            dispatch_query(query_times[query_index])

    observation_clock = _iterate_observations(sampled.observations, config.pacing, consume)
    while query_index < len(query_times):
        dispatch_query(query_times[query_index])
    # A chunking adapter may still hold the final observation at the bounded
    # evidence endpoint. Flush that evidence before any remaining strict-window
    # grace starts; close() is reserved for the later shutdown drain and must
    # not start a newly scoreable model call after the evaluation boundary.
    flush = getattr(session, "flush", None)
    if callable(flush):
        flush_events = flush()
        flush_receive_ns = time.perf_counter_ns()
        for event in flush_events:
            event.telemetry.setdefault("core_event_receive_perf_ns", flush_receive_ns)
        _reconcile_observation_commits(flush_events, observation_events)
        events.extend(flush_events)
    scoring_grace_applied = (
        capabilities.state_lifetime == "persistent"
        and capabilities.response_mode == "autonomous"
        and config.pacing == "wall_clock"
    )
    if scoring_grace_applied and post_stream_response_grace_s > 0:
        observation_clock.wait(evaluation_end_s)
    evaluation_end_perf_ns = (
        observation_clock.scheduled_perf_ns(evaluation_end_s)
        if config.pacing == "wall_clock"
        else None
    )
    close_events = session.close()
    close_receive_ns = time.perf_counter_ns()
    for event in close_events:
        event.telemetry.setdefault("session_close_event", True)
        event.telemetry.setdefault("core_event_receive_perf_ns", close_receive_ns)
        # A synchronous adapter may flush a partial chunk after the scoring
        # grace. Preserve its raw output, but mark any model call that starts
        # after the evaluation boundary as shutdown-drain telemetry only.
        model_calls = event.telemetry.get("model_calls", [])
        if evaluation_end_perf_ns is not None and isinstance(model_calls, list):
            starts = [
                int(call["start_perf_ns"])
                for call in model_calls
                if isinstance(call, dict) and isinstance(call.get("start_perf_ns"), int)
            ]
            if starts and min(starts) >= evaluation_end_perf_ns:
                event.telemetry["shutdown_drain"] = True
                event.telemetry["eligible_for_scoring"] = False
                event.telemetry["suppression_reason"] = "shutdown_drain"
    _reconcile_observation_commits(close_events, observation_events)
    events.extend(close_events)
    _align_response_events_to_stream_clock(
        events,
        observation_clock,
        video_end_s=video_end_s,
        evaluation_end_s=evaluation_end_s,
    )
    _annotate_proactive_response_latency(events, record, config.proactive_window_s)
    failure = _failure_reason(events)
    output = {
        "record_id": record.record_id,
        "task": "proactive",
        "status": "failed" if failure else "completed",
        "video_path": record.video_path,
        "task_type": record.task_type,
        "memory_length": record.memory_length,
        "metadata": record.metadata,
        "instruction": record.instruction,
        "instruction_time_s": record.instruction_time_s,
        # Retain the source field for provenance/resume compatibility.  It is
        # not an evaluation cutoff; evidence_end_s is the bounded GT endpoint.
        "deadline_s": record.deadline_s,
        "video_duration_s": video_end_s,
        "evaluation_end_s": evaluation_end_s,
        "post_stream_response_grace_s": post_stream_response_grace_s,
        "evaluation_end_perf_ns": evaluation_end_perf_ns,
        "post_stream_scoring_grace_applied": scoring_grace_applied,
        "post_stream_response_policy": "remaining_strict_window",
        "proactive_evidence_end_policy": (
            "last_strict_window_end_clamped_to_video"
            if video_end_s is not None
            else "last_strict_window_end_source_duration_unavailable"
        ),
        "video_duration_policy": (
            "opencv_frame_count_metadata"
            if video_end_s is not None
            else "unavailable_not_scanned"
        ),
        "proactive_window_s": config.proactive_window_s,
        "proactive_history_window_s": config.proactive_history_window_s,
        "window_boundary": "half_open",
        "legacy_deadline_used": False,
        "windows": [window.model_dump(mode="json") for window in record.windows],
        "evidence_start_s": start_s,
        "evidence_end_s": end_s,
        "events": [event.model_dump(mode="json") for event in events],
        "failed_reason": failure,
        "observation_count": len(sampled.observations),
        "observation_timestamps": timestamps,
        "resolved_frame_indices": [observation.frame_index for observation in sampled.observations],
        "source_fps": sampled.source_fps,
        "video_sha256": sampled.video_sha256,
        "decoder": sampled.decoder,
    }
    return output, [_event_payload(record.record_id, event) for event in events]


def _failure_result(
    record: QARecord | ProactiveRecord,
    task: TaskName,
    exc: Exception,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reason = str(exc)
    event = ModelEvent(
        kind=EventKind.FAILURE,
        logical_time_s=0.0,
        status="failed",
        failed_reason=reason,
        telemetry={"failure_stage": "core_record_execution"},
    )
    result = {
        "record_id": record.record_id,
        "task": task.value,
        "status": "failed",
        "video_path": record.video_path,
        "failed_reason": reason,
        "prediction": "",
        "events": [event.model_dump(mode="json")],
    }
    if isinstance(record, ProactiveRecord):
        # Preserve the GT windows on a failed record so strict-all scoring
        # keeps the failed sample in its denominator instead of silently
        # dropping every window from the record.
        result.update(
            {
                "task_type": record.task_type,
                "metadata": record.metadata,
                "instruction": record.instruction,
                "instruction_time_s": record.instruction_time_s,
                "deadline_s": record.deadline_s,
                "video_duration_s": None,
                "windows": [window.model_dump(mode="json") for window in record.windows],
            }
        )
    else:
        qa_user_content = build_qa_prompt(record.question, record.options)
        result.update(
            {
                "question": record.question,
                "options": record.options,
                "answer": record.answer,
                "qa_user_content": qa_user_content,
                "qa_user_content_sha256": _sha256_text(qa_user_content),
                "qa_user_content_policy": "byte_identical_core_prompt",
                "qa_template_policy": "mechanical_role_control_serialization_only",
                "qa_prompt_metadata": None,
                "qa_query_count": 0,
                "qa_query_policy": "exactly_one_core_dispatch",
                "question_time_s": record.question_time_s,
                "evidence_anchor_s": record.evidence_anchor_s,
            }
        )
    return result, [_event_payload(record.record_id, event)]


def _resolved_config(
    config: RunConfig,
    capabilities: AdapterCapabilities,
    adapter_metadata: dict[str, Any],
    *,
    release_id: str,
    schema_version: str,
    release_manifest: dict[str, Any],
    preflight: dict[str, Any],
    judge: JudgeRouter,
) -> dict[str, Any]:
    if callable(adapter_metadata):
        adapter_metadata = adapter_metadata()
    if not isinstance(adapter_metadata, dict):
        adapter_metadata = {}
    resolved = config.model_dump(mode="json")
    resolved.update(
        {
            "release_id": release_id,
            "schema_version": schema_version,
            "release_manifest_hash": stable_hash(release_manifest),
            "release_file_hashes": release_manifest.get("files", {}),
            "adapter_capabilities": capabilities.model_dump(mode="json"),
            "adapter_metadata": adapter_metadata,
            "sampler": "opencv-v0",
            "decoder_policy": "opencv-random-access-rgb",
            "image_resolution_policy": {
                "mode": "width_at_most_max_width_preserve_aspect_no_upscale",
                "configured_max_width": config.max_width,
                "core_resize_applied": config.max_width is not None,
            },
            "leaderboard_category": (
                "Native Streaming"
                if capabilities.state_lifetime == "persistent"
                else "Non-native Streaming"
            ),
            "response_triggering": capabilities.response_mode,
            "proactive_response_track": (
                "autonomous_primary"
                if capabilities.state_lifetime == "persistent"
                and capabilities.response_mode == "autonomous"
                and config.pacing == "wall_clock"
                else "polling_baseline"
            )
            if config.task is TaskName.PROACTIVE
            else None,
            "proactive_track": (
                "autonomous_primary"
                if capabilities.state_lifetime == "persistent"
                and capabilities.response_mode == "autonomous"
                and config.pacing == "wall_clock"
                else "polling_or_diagnostic_baseline"
            )
            if config.task is TaskName.PROACTIVE
            else "not_applicable",
            "proactive_primary_eligible": (
                capabilities.state_lifetime == "persistent"
                and capabilities.response_mode == "autonomous"
                and config.pacing == "wall_clock"
            )
            if config.task is TaskName.PROACTIVE
            else None,
            "execution_mode": "incremental_core_observations",
            "window_boundary": "half_open",
            "proactive_eventual_end": "next_trigger_or_final_strict_window_end",
            "proactive_evidence_end": (
                "last_strict_window_end_clamped_to_metadata_video_end_when_available"
            ),
            "video_duration_probe": "metadata_only_never_full_decode",
            "post_stream_response_policy": "remaining_strict_window",
            "legacy_deadline_used": False,
            "scoring": judge.metadata,
            "preflight": preflight,
        }
    )
    preflight_identity = {
        key: preflight.get(key)
        for key in (
            "protocol",
            "data",
            "visual_input",
            "generation",
            "adapter",
            "telemetry_contract",
            "environment",
            "code_identities",
        )
    }
    identity = {
        key: value
        for key, value in resolved.items()
        if key
        not in {
            "output_dir",
            "resume",
            "checkpoint_every_records",
            "preflight",
            "config_hash",
        }
    }
    identity["preflight"] = preflight_identity
    resolved["config_hash"] = stable_hash(identity)
    return resolved


def run(config: RunConfig) -> Path:
    release = load_release(Path(config.release_dir))
    records = release.records(config.task.value, config.subset)
    adapter = load_adapter(config.adapter, config.adapter_config)
    capabilities = validate_adapter(adapter, config.task, config)
    judge = judge_from_settings(config.model_dump(mode="python"))
    preflight = build_preflight_snapshot(
        config, release, adapter, capabilities, record_count=len(records)
    )
    resolved = _resolved_config(
        config,
        capabilities,
        getattr(adapter, "metadata", {}),
        release_id=release.manifest.release_id,
        schema_version=release.manifest.schema_version,
        release_manifest=release.manifest.model_dump(mode="json"),
        preflight=preflight,
        judge=judge,
    )
    output_dir = Path(config.output_dir)
    bundle = RunBundle(output_dir)
    if bundle.is_finalized():
        raise ValueError(f"finalized bundle is immutable: {output_dir}")
    target_ids = {record.record_id for record in records}
    previous_records: list[dict[str, Any]] = []
    previous_events: list[dict[str, Any]] = []
    if config.resume:
        previous_records, previous_events = bundle.resume_state(
            expected_config_hash=resolved["config_hash"]
        )
    bundle.prepare(resolved)
    terminal = {
        row.get("record_id")
        for row in previous_records
        if row.get("record_id") in target_ids and row.get("status") in {"completed", "failed"}
    }
    record_by_id = {
        row["record_id"]: row
        for row in previous_records
        if row.get("record_id") in target_ids and isinstance(row.get("record_id"), str)
    }
    rerun_ids = target_ids - terminal
    raw_events = [event for event in previous_events if event.get("record_id") not in rerun_ids]
    newly_terminal = 0

    def checkpoint() -> None:
        raw_records = [
            record_by_id[record.record_id] for record in records if record.record_id in record_by_id
        ]
        bundle.checkpoint(
            resolved_config=resolved,
            records=raw_records,
            events=raw_events,
        )

    try:
        for record in records:
            if record.record_id in terminal:
                continue
            video_path = _video_path(record.video_path, config.video_root)
            try:
                if config.task is TaskName.QA:
                    result, events = _qa_record(
                        record,
                        video_path,
                        config,
                        adapter,  # type: ignore[arg-type]
                    )
                else:
                    result, events = _proactive_record(
                        record,
                        video_path,
                        config,
                        adapter,
                        capabilities,  # type: ignore[arg-type]
                    )
            except FatalEvaluationError:
                # An adapter uses this exception for process-fatal failures
                # (for example a poisoned CUDA context).  Do not turn it into
                # a terminal record failure: continuing would make every
                # subsequent sample a misleading cascade failure.  The outer
                # handler checkpoints already completed records and leaves the
                # bundle resumable but not finalized.
                raise
            except (MediaError, ValueError, OSError, RuntimeError) as exc:
                result, events = _failure_result(record, config.task, exc)
            record_by_id[record.record_id] = result
            raw_events = [
                event for event in raw_events if event.get("record_id") != record.record_id
            ]
            raw_events.extend(events)
            newly_terminal += 1
            if newly_terminal % config.checkpoint_every_records == 0:
                checkpoint()
    except BaseException:
        if newly_terminal % config.checkpoint_every_records:
            checkpoint()
        close_adapter = getattr(adapter, "close", None)
        if callable(close_adapter):
            close_adapter()
        raise

    if newly_terminal % config.checkpoint_every_records:
        checkpoint()
    raw_records = [
        record_by_id[record.record_id] for record in records if record.record_id in record_by_id
    ]
    metrics = score_records(
        config.task.value,
        list(raw_records),
        judge=judge,
        events=raw_events,
        proactive_window_s=config.proactive_window_s,
        window_boundary="half_open",
    )
    scored_records = metrics.pop("scored_records", [])
    metrics["execution_track"] = resolved.get("preflight", {}).get("execution_track", {})
    metrics["telemetry"] = summarize_telemetry(raw_events, scored_records)
    official_eligibility = assess_official_eligibility(
        config.task.value,
        metrics,
        synthetic=config.synthetic,
        provisional=release.manifest.status != "public",
    )
    metrics["official_eligibility"] = official_eligibility
    try:
        bundle.write(
            resolved_config=resolved,
            records=scored_records,
            events=raw_events,
            metrics=metrics,
            synthetic=config.synthetic,
            provisional=release.manifest.status != "public",
            official_eligibility=official_eligibility,
        )
        bundle.discard_checkpoints()
    finally:
        close_adapter = getattr(adapter, "close", None)
        if callable(close_adapter):
            close_adapter()
    return output_dir
