"""Pure V0 scoring functions, based on current vlx_eval behavior."""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

DEFAULT_SEMANTIC_TASK_TYPES = frozenset({"SSR", "CRR"})
SCORER_VERSION = "osb-scoring-v6"
VLM_JUDGE_PROMPT_VERSION = "osb-vlm-judge-v1"
VLM_JUDGE_PROMPT = """\
You are an expert evaluator for a video question answering task.

Task Type: {task_type}
Question: {question}
Reference Answer: {gt_answer}
Model Prediction: {prediction}

Evaluate whether the model prediction correctly conveys the same meaning as the
reference answer. Return only one decimal number between 0 and 1.

Scoring guide:
- 1.0: fully correct and semantically equivalent.
- 0.7-0.9: mostly correct with a minor omission or slight imprecision.
- 0.4-0.6: partially correct but missing important information.
- 0.1-0.3: mostly wrong but contains a small relevant element.
- 0.0: wrong, irrelevant, empty, or WAIT.

For SSR, compare the recognized action or step. For CRR, compare the causal
relationship or action. Output only the numeric score.
Score:"""


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _distribution(values: list[float], population_count: int, unit: str) -> dict[str, Any]:
    return {
        "unit": unit,
        "population_count": population_count,
        "observed_count": len(values),
        "coverage": len(values) / population_count if population_count else None,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def _union_seconds(intervals: list[tuple[int, int]]) -> float | None:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if end < start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    if not merged:
        return None
    return sum(end - start for start, end in merged) / 1_000_000_000


@dataclass(frozen=True)
class JudgeResult:
    """One observable scoring decision, including judge coverage metadata."""

    score: float
    method: str
    model: str | None = None
    prompt_version: str | None = None
    raw_response: str | None = None
    error: str | None = None
    requested: bool = True
    cached: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": float(max(0.0, min(1.0, self.score))),
            "method": self.method,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "raw_response": self.raw_response,
            "error": self.error,
            "requested": self.requested,
            "cached": self.cached,
        }


class ExactJudge:
    """Deterministic normalized text matcher used for label-like tasks."""

    def score(
        self,
        *,
        question: str,
        gt_answer: str,
        prediction: str,
        task_type: str,
    ) -> JudgeResult:
        del question, task_type
        predicted = normalize_text(prediction)
        expected = normalize_text(gt_answer)
        return JudgeResult(
            score=float(bool(predicted) and predicted == expected),
            method="exact_match",
            requested=True,
        )


def _parse_judge_score(raw_text: str) -> float | None:
    """Parse the numeric-only judge contract without accepting arbitrary text."""

    candidate = raw_text.strip().strip("`").strip()
    try:
        value = float(candidate)
    except ValueError:
        match = re.search(r"(?<![\d.])(?:0(?:\.\d+)?|1(?:\.0+)?)(?![\d.])", candidate)
        if match is None:
            return None
        value = float(match.group(0))
    return value if 0.0 <= value <= 1.0 else None


class VLMJudge:
    """OpenAI-compatible text judge with explicit, persisted failure coverage."""

    def __init__(
        self,
        *,
        base_url: str | None,
        model: str = "Qwen3.5-35B-A3B",
        api_key: str | None = None,
        api_key_env: str = "TRACE_VLM_JUDGE_API_KEY",
        timeout_s: float = 60.0,
        temperature: float = 0.0,
        prompt_template: str = VLM_JUDGE_PROMPT,
        prompt_version: str = VLM_JUDGE_PROMPT_VERSION,
        transport: Callable[[urllib.request.Request, float], bytes] | None = None,
    ):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.model = model
        self.api_key_env = api_key_env
        self.api_key = api_key or ""
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.prompt_template = prompt_template
        self.prompt_version = prompt_version
        self.transport = transport

    def _unavailable(self, error: str) -> JudgeResult:
        return JudgeResult(
            score=0.0,
            method="vlm_unavailable",
            model=self.model,
            prompt_version=self.prompt_version,
            error=error,
        )

    def score(
        self,
        *,
        question: str,
        gt_answer: str,
        prediction: str,
        task_type: str,
    ) -> JudgeResult:
        clean_prediction = normalize_text(prediction)
        if not clean_prediction:
            return JudgeResult(
                score=0.0,
                method="vlm_empty_prediction",
                model=self.model,
                prompt_version=self.prompt_version,
            )
        if not self.base_url:
            return self._unavailable("judge endpoint is not configured")

        prompt = self.prompt_template.format(
            task_type=task_type,
            question=question,
            gt_answer=gt_answer,
            prediction=clean_prediction,
        )
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            if self.transport is None:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    body = response.read()
            else:
                body = self.transport(request, self.timeout_s)
            result = json.loads(body.decode("utf-8") if isinstance(body, bytes) else str(body))
            content = result["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            raw_response = str(content).strip()
            value = _parse_judge_score(raw_response)
            if value is None:
                return JudgeResult(
                    score=0.0,
                    method="vlm_invalid_response",
                    model=self.model,
                    prompt_version=self.prompt_version,
                    raw_response=raw_response,
                    error="judge response did not contain a score in [0, 1]",
                )
            return JudgeResult(
                score=value,
                method="vlm",
                model=self.model,
                prompt_version=self.prompt_version,
                raw_response=raw_response,
            )
        except urllib.error.HTTPError as exc:
            return self._unavailable(f"HTTPError: {exc.code}")
        except (OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            return self._unavailable(f"{type(exc).__name__}: {exc}")


class JudgeRouter:
    """Select exact or semantic judging without embedding model-specific rules."""

    def __init__(
        self,
        *,
        mode: str = "auto",
        base_url: str | None = None,
        model: str = "Qwen3.5-35B-A3B",
        api_key: str | None = None,
        api_key_env: str = "TRACE_VLM_JUDGE_API_KEY",
        timeout_s: float = 60.0,
        temperature: float = 0.0,
        semantic_task_types: set[str] | frozenset[str] | list[str] | None = None,
        transport: Callable[[urllib.request.Request, float], bytes] | None = None,
    ):
        if mode not in {"auto", "exact", "vlm"}:
            raise ValueError("judge mode must be one of: auto, exact, vlm")
        self.mode = mode
        self.base_url = base_url.rstrip("/") if base_url else None
        self.model = model
        self.api_key_env = api_key_env
        self.semantic_task_types = {
            str(value).strip().upper()
            for value in (semantic_task_types or DEFAULT_SEMANTIC_TASK_TYPES)
            if str(value).strip()
        }
        self.exact = ExactJudge()
        self.vlm = VLMJudge(
            base_url=self.base_url,
            model=model,
            api_key=api_key,
            api_key_env=api_key_env,
            timeout_s=timeout_s,
            temperature=temperature,
            transport=transport,
        )
        self._cache: dict[tuple[str, str, str, str], JudgeResult] = {}

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "scorer_version": SCORER_VERSION,
            "response_assembly": "response-episode-v2",
            "window_boundary": "half_open",
            "judge_mode": self.mode,
            "semantic_task_types": sorted(self.semantic_task_types),
            "judge_model": self.model if self.mode != "exact" else None,
            "judge_base_url": self.base_url,
            "judge_api_key_env": self.api_key_env,
            "judge_prompt_version": VLM_JUDGE_PROMPT_VERSION if self.mode != "exact" else None,
            "judge_endpoint_configured": bool(self.base_url),
        }

    def _should_use_vlm(self, task_type: str) -> bool:
        if self.mode == "vlm":
            return True
        return self.mode == "auto" and str(task_type).strip().upper() in self.semantic_task_types

    def score(
        self,
        *,
        question: str,
        gt_answer: str,
        prediction: str,
        task_type: str,
    ) -> JudgeResult:
        cache_key = (
            str(task_type).strip().upper(),
            normalize_text(question),
            normalize_text(gt_answer),
            normalize_text(prediction),
        )
        if cache_key in self._cache:
            return replace(self._cache[cache_key], cached=True)

        if not self._should_use_vlm(task_type):
            result = self.exact.score(
                question=question,
                gt_answer=gt_answer,
                prediction=prediction,
                task_type=task_type,
            )
        elif self.mode == "auto" and not self.base_url:
            exact = self.exact.score(
                question=question,
                gt_answer=gt_answer,
                prediction=prediction,
                task_type=task_type,
            )
            result = replace(
                exact,
                method="exact_fallback_no_vlm",
                model=self.model,
                prompt_version=VLM_JUDGE_PROMPT_VERSION,
                error="judge endpoint is not configured",
            )
        else:
            result = self.vlm.score(
                question=question,
                gt_answer=gt_answer,
                prediction=prediction,
                task_type=task_type,
            )
        self._cache[cache_key] = result
        return result


def judge_from_settings(settings: Mapping[str, Any]) -> JudgeRouter:
    """Build a router from resolved config or CLI overrides without a secret."""

    def value(name: str, default: Any = None) -> Any:
        if hasattr(settings, name):
            return getattr(settings, name)
        return settings.get(name, default)

    api_key_env = str(value("judge_api_key_env", "TRACE_VLM_JUDGE_API_KEY"))
    # The legacy OSB_* key name stays accepted for runs configured before the
    # TRACE rename; an explicitly configured custom env name is used as-is.
    api_key = os.getenv(api_key_env)
    if not api_key and api_key_env == "TRACE_VLM_JUDGE_API_KEY":
        api_key = os.getenv("OSB_VLM_JUDGE_API_KEY")
    return JudgeRouter(
        mode=str(value("judge_mode", "auto")),
        base_url=value("judge_base_url") or os.getenv("TRACE_VLM_JUDGE_BASE_URL")
        or os.getenv("OSB_VLM_JUDGE_BASE_URL"),
        model=str(value("judge_model", "Qwen3.5-35B-A3B")),
        api_key=api_key,
        api_key_env=api_key_env,
        timeout_s=float(value("judge_timeout_s", 60.0)),
        temperature=float(value("judge_temperature", 0.0)),
        semantic_task_types=value("semantic_task_types", DEFAULT_SEMANTIC_TASK_TYPES),
    )


@dataclass
class ResponseEpisode:
    """A complete proactive response assembled from one or more model events."""

    response_id: str
    text: str
    start_video_time_s: float
    end_video_time_s: float
    first_token_perf_ns: int | None = None
    scoring_perf_ns: int | None = None
    scoring_time_source: str | None = None
    completion_perf_ns: int | None = None
    source_event_ids: list[str] = field(default_factory=list)
    source_event_indices: list[int] = field(default_factory=list)
    assembly_mode: str = "complete"

    def as_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "text": self.text,
            "start_video_time_s": self.start_video_time_s,
            "end_video_time_s": self.end_video_time_s,
            "first_token_perf_ns": self.first_token_perf_ns,
            "scoring_perf_ns": self.scoring_perf_ns,
            "scoring_time_source": self.scoring_time_source,
            "completion_perf_ns": self.completion_perf_ns,
            "source_event_ids": list(self.source_event_ids),
            "source_event_indices": list(self.source_event_indices),
            "assembly_mode": self.assembly_mode,
        }


def _event_value(event: Mapping[str, Any], name: str, *telemetry_names: str) -> Any:
    value = event.get(name)
    telemetry = event.get("telemetry", {})
    if isinstance(telemetry, Mapping):
        for telemetry_name in telemetry_names or (name,):
            telemetry_value = telemetry.get(telemetry_name)
            if telemetry_value is None:
                continue
            # ModelEvent's backward-compatible default is text_mode=complete.
            # Let an older adapter's explicit telemetry field override that
            # default; a non-default top-level mode always remains authoritative.
            if name == "text_mode" and value in {None, "complete"}:
                return telemetry_value
            if value is None:
                return telemetry_value
    if value is not None:
        return value
    return None


def _event_answer_text(event: Mapping[str, Any]) -> str:
    return str(event.get("text") or "").strip()


def _event_kind(event: Mapping[str, Any]) -> str:
    value = event.get("kind", "")
    value = getattr(value, "value", value)
    return str(value).lower().rsplit(".", 1)[-1]


def _append_delta_text(existing: str, fragment: str) -> str:
    """Join word-level deltas while preserving explicit whitespace/punctuation."""

    if not existing:
        return fragment
    if not fragment:
        return existing
    if existing[-1].isspace() or fragment[0].isspace():
        return existing + fragment
    if existing[-1].isalnum() and fragment[0].isalnum():
        return existing + " " + fragment
    return existing + fragment


def _event_score_eligible(event: Mapping[str, Any]) -> bool:
    """Return whether an emitted answer may enter a scored episode.

    Raw provider output is intentionally kept even when it was produced during
    autonomous prefill or shutdown drain. Those boundaries are telemetry, not
    benchmark response time, and must be filtered before episode assignment.
    """

    telemetry = event.get("telemetry", {})
    if not isinstance(telemetry, Mapping):
        return True
    if telemetry.get("provider_output_suppressed") is True:
        return False
    if telemetry.get("eligible_for_scoring") is False:
        return False
    if telemetry.get("within_evaluation_end") is False:
        return False
    return True


def _event_sequence_key(item: tuple[int, Mapping[str, Any]]) -> tuple[int, float, int]:
    index, event = item
    sequence = _event_value(event, "sequence_id")
    if isinstance(sequence, bool):
        return (1, float(index), index)
    if isinstance(sequence, (int, float)):
        return (0, float(sequence), index)
    if isinstance(sequence, str) and re.fullmatch(r"\d+(?:\.\d+)?", sequence.strip()):
        return (0, float(sequence), index)
    return (1, float(index), index)


def assemble_response_episodes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assemble normalized response fragments into scored response episodes.

    Complete events remain one episode each for backward compatibility. Delta or
    snapshot events must provide ``response_id``; ``is_final`` closes an
    episode, while a WAIT/silent event also closes any active episode. This
    keeps Core independent of provider-specific output syntax.
    """

    episodes: list[ResponseEpisode] = []
    active: dict[str, ResponseEpisode] = {}

    def close(response_key: str) -> None:
        episode = active.pop(response_key, None)
        if episode is not None and episode.text.strip():
            episodes.append(episode)

    def close_all() -> None:
        for response_key in list(active):
            close(response_key)

    ordered_events = sorted(enumerate(events), key=_event_sequence_key)
    for index, event in ordered_events:
        kind = _event_kind(event)
        decision = str(_event_value(event, "response_decision") or "").lower()
        if kind in {"wait", "failure"} or decision == "silent":
            close_all()
            continue
        if not _event_score_eligible(event):
            # A time cutoff forbids starting an episode, not completing a
            # timely, still-open one. Never revive prefill, a new model call
            # during shutdown, a complete answer, or an already closed ID.
            telemetry = event.get("telemetry", {})
            response_id = str(_event_value(event, "response_id") or "")
            reason = telemetry.get("suppression_reason")
            continuation = (
                kind == "answer"
                and response_id in active
                and _event_value(event, "text_mode") in {"delta", "snapshot"}
                and reason in {"after_evaluation_end", "unobservable_close_time"}
                and telemetry.get("provider_output_suppressed") is not True
                and telemetry.get("shutdown_drain") is not True
            )
            if not continuation:
                continue
        if kind != "answer" or not _event_answer_text(event):
            continue

        text = _event_answer_text(event)
        mode = str(_event_value(event, "text_mode") or "complete").lower()
        if mode not in {"complete", "delta", "snapshot"}:
            mode = "complete"
        raw_response_id = _event_value(event, "response_id")
        response_id = str(raw_response_id) if raw_response_id is not None else ""
        if mode == "complete" or not response_id:
            # Without an identity/boundary contract, treating a fragment as a
            # complete answer is the only non-speculative compatibility choice.
            close_all()
            first_token = _event_value(event, "first_token_perf_ns")
            scoring_time = _event_value(event, "response_scoring_perf_ns")
            scoring_source = _event_value(event, "evaluation_time_source")
            completion = _event_value(
                event, "completion_perf_ns", "response_completion_perf_ns", "arrival_perf_ns"
            )
            event_id = _event_value(event, "event_id") or f"event-{index}"
            episodes.append(
                ResponseEpisode(
                    response_id=response_id or f"legacy-{index}",
                    text=text,
                    start_video_time_s=float(event.get("logical_time_s", 0.0)),
                    end_video_time_s=float(event.get("logical_time_s", 0.0)),
                    first_token_perf_ns=first_token if isinstance(first_token, int) else None,
                    scoring_perf_ns=(
                        scoring_time
                        if isinstance(scoring_time, int)
                        else first_token if isinstance(first_token, int) else None
                    ),
                    scoring_time_source=(
                        str(scoring_source)
                        if scoring_source is not None
                        else "first_token_perf_ns" if isinstance(first_token, int) else None
                    ),
                    completion_perf_ns=completion if isinstance(completion, int) else None,
                    source_event_ids=[str(event_id)],
                    source_event_indices=[index],
                    assembly_mode="complete" if mode == "complete" else "legacy_complete",
                )
            )
            continue

        response_key = response_id
        episode = active.get(response_key)
        if episode is None:
            first_token = _event_value(event, "first_token_perf_ns")
            scoring_time = _event_value(event, "response_scoring_perf_ns")
            scoring_source = _event_value(event, "evaluation_time_source")
            completion = _event_value(
                event, "completion_perf_ns", "response_completion_perf_ns", "arrival_perf_ns"
            )
            event_id = _event_value(event, "event_id") or f"event-{index}"
            active[response_key] = ResponseEpisode(
                response_id=response_id,
                text=text if mode == "snapshot" else text,
                start_video_time_s=float(event.get("logical_time_s", 0.0)),
                end_video_time_s=float(event.get("logical_time_s", 0.0)),
                first_token_perf_ns=first_token if isinstance(first_token, int) else None,
                scoring_perf_ns=(
                    scoring_time
                    if isinstance(scoring_time, int)
                    else first_token if isinstance(first_token, int) else None
                ),
                scoring_time_source=(
                    str(scoring_source)
                    if scoring_source is not None
                    else "first_token_perf_ns" if isinstance(first_token, int) else None
                ),
                completion_perf_ns=completion if isinstance(completion, int) else None,
                source_event_ids=[str(event_id)],
                source_event_indices=[index],
                assembly_mode=mode,
            )
        else:
            first_token = _event_value(event, "first_token_perf_ns")
            scoring_time = _event_value(event, "response_scoring_perf_ns")
            scoring_source = _event_value(event, "evaluation_time_source")
            completion = _event_value(
                event, "completion_perf_ns", "response_completion_perf_ns", "arrival_perf_ns"
            )
            event_id = _event_value(event, "event_id") or f"event-{index}"
            episode.end_video_time_s = float(event.get("logical_time_s", 0.0))
            if mode == "snapshot":
                episode.text = text
            else:
                episode.text = _append_delta_text(episode.text, text)
            episode.source_event_ids.append(str(event_id))
            episode.source_event_indices.append(index)
            if episode.first_token_perf_ns is None and isinstance(first_token, int):
                episode.first_token_perf_ns = first_token
            if episode.scoring_perf_ns is None:
                if isinstance(scoring_time, int):
                    episode.scoring_perf_ns = scoring_time
                    episode.scoring_time_source = (
                        str(scoring_source) if scoring_source is not None else None
                    )
                elif isinstance(first_token, int):
                    episode.scoring_perf_ns = first_token
                    episode.scoring_time_source = "first_token_perf_ns"
            if isinstance(completion, int):
                episode.completion_perf_ns = completion
        if _event_value(event, "is_final") is True:
            close(response_key)

    close_all()
    episodes.sort(key=lambda episode: (episode.start_video_time_s, episode.source_event_indices[0]))
    return [episode.as_dict() for episode in episodes]


def summarize_telemetry(
    events: list[dict[str, Any]], records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Aggregate directly observed telemetry without filling missing boundaries."""

    record_count = len(records)
    completed = sum(record.get("status") == "completed" for record in records)
    failed = sum(record.get("status") == "failed" for record in records)
    telemetries = [event.get("telemetry", {}) for event in events]
    observations = [event for event in events if _event_kind(event) == "observation"]
    committed = [
        event
        for event in observations
        if isinstance(event.get("telemetry", {}).get("commit_perf_ns"), int)
    ]
    frame_processing = [
        value
        for event in observations
        if (value := _number(event.get("telemetry", {}).get("frame_processing_ms"))) is not None
    ]
    frame_lag = [
        value
        for event in observations
        if (value := _number(event.get("telemetry", {}).get("frame_lag_ms"))) is not None
    ]
    on_time = [
        telemetry["on_time"]
        for event in observations
        if isinstance((telemetry := event.get("telemetry", {})).get("on_time"), bool)
    ]

    query_events = [
        event
        for event in events
        if _event_kind(event) in {"answer", "wait", "failure"}
        and isinstance(event.get("telemetry", {}).get("query_dispatch_perf_ns"), int)
    ]
    query_groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in query_events:
        telemetry = event.get("telemetry", {})
        dispatch = telemetry.get("query_dispatch_perf_ns")
        query_id = telemetry.get("query_id") or event.get("query_id")
        identity = str(query_id) if query_id is not None else f"dispatch:{dispatch}"
        query_groups[(str(event.get("record_id", "")), identity)].append(event)
    ttft: list[float] = []
    response_total: list[float] = []
    # Proactive latency is a window metric, not a pooled response-episode
    # metric.  A native autonomous model may emit many valid answer episodes
    # before or after a GT window; those episodes are intentionally reported as
    # intrusion/redundancy, but they are not latency observations for a GT
    # response window.  ``score_proactive`` persists the strict assignment on
    # each scored record, so use its in-window rows as the denominator.
    proactive_latency: list[float] = []
    proactive_latency_population = 0
    scored_window_rows_available = False
    for record in records:
        task = str(record.get("task") or "proactive")
        if task != "proactive":
            continue
        rows = record.get("per_window_results")
        if not isinstance(rows, list):
            continue
        scored_window_rows_available = True
        for row in rows:
            if not isinstance(row, dict) or row.get("source") != "in_window":
                continue
            if not row.get("is_answered"):
                continue
            proactive_latency_population += 1
            value = _number(row.get("latency_ms"))
            if value is not None:
                proactive_latency.append(value)
    if not scored_window_rows_available:
        # Keep direct summarize_telemetry callers and pre-v5 legacy records
        # useful. New Core runs always provide per-window scored rows above.
        proactive_latency = [
            value
            for event in events
            if _event_kind(event) == "answer"
            and (
                value := _number(
                    event.get("telemetry", {}).get("proactive_response_latency_ms")
                )
            )
            is not None
        ]
        proactive_latency_population = len(proactive_latency)
    for group in query_groups.values():
        group_telemetry = [event.get("telemetry", {}) for event in group]
        semantic_starts = [
            value
            for telemetry in group_telemetry
            if isinstance((value := telemetry.get("semantic_query_arrival_perf_ns")), int)
        ]
        dispatches = [
            value
            for telemetry in group_telemetry
            if isinstance((value := telemetry.get("query_dispatch_perf_ns")), int)
        ]
        ttft_start = min(semantic_starts or dispatches) if semantic_starts or dispatches else None
        first_tokens = [
            value
            for telemetry in group_telemetry
            if isinstance((value := telemetry.get("first_token_perf_ns")), int)
        ]
        completions = [
            value
            for telemetry in group_telemetry
            if isinstance((value := telemetry.get("response_completion_perf_ns")), int)
        ]
        first = min(first_tokens) if first_tokens else None
        completion = max(completions) if completions else None
        if isinstance(first, int) and isinstance(ttft_start, int) and first >= ttft_start:
            ttft.append((first - ttft_start) / 1_000_000)
        else:
            reported = [
                value
                for telemetry in group_telemetry
                if (value := _number(telemetry.get("ttft_ms"))) is not None
            ]
            if reported:
                ttft.append(min(reported))
        if (
            isinstance(completion, int)
            and isinstance(ttft_start, int)
            and completion >= ttft_start
        ):
            response_total.append((completion - ttft_start) / 1_000_000)
        else:
            reported = [
                value
                for telemetry in group_telemetry
                if (value := _number(telemetry.get("response_total_ms"))) is not None
            ]
            if reported:
                response_total.append(max(reported))

    calls: list[dict[str, Any]] = []
    for event, telemetry in zip(events, telemetries):
        candidates = telemetry.get("model_calls", telemetry.get("calls", []))
        if isinstance(candidates, list):
            for call in candidates:
                if isinstance(call, dict):
                    call_row = dict(call)
                    call_row["_record_id"] = str(event.get("record_id", ""))
                    calls.append(call_row)
    call_intervals = [
        (start, end)
        for call in calls
        if isinstance((start := call.get("start_perf_ns")), int)
        and isinstance((end := call.get("end_perf_ns")), int)
        and end >= start
    ]
    records_by_id = {str(record.get("record_id", "")): record for record in records}
    qa_record_ids = {
        record_id
        for record_id, record in records_by_id.items()
        if str(record.get("task") or ("qa" if "question" in record else "")) == "qa"
    }
    qa_query_dispatch: dict[str, int] = {}
    for event in events:
        record_id = str(event.get("record_id", ""))
        if record_id not in qa_record_ids:
            continue
        telemetry = event.get("telemetry", {})
        dispatch = telemetry.get("semantic_query_arrival_perf_ns")
        if not isinstance(dispatch, int):
            dispatch = telemetry.get("query_dispatch_perf_ns")
        if isinstance(dispatch, int):
            qa_query_dispatch[record_id] = min(qa_query_dispatch.get(record_id, dispatch), dispatch)

    qa_observations = [
        event
        for event in observations
        if str(event.get("record_id", "")) in qa_record_ids
    ]
    qa_history_frame_processing = [
        value
        for event in qa_observations
        if (value := _number(event.get("telemetry", {}).get("frame_processing_ms"))) is not None
    ]
    qa_history_elapsed_s: list[float] = []
    for record_id, dispatch in qa_query_dispatch.items():
        arrivals = [
            event.get("telemetry", {}).get("arrival_perf_ns")
            for event in qa_observations
            if str(event.get("record_id", "")) == record_id
            and isinstance(event.get("telemetry", {}).get("arrival_perf_ns"), int)
        ]
        if arrivals and dispatch >= min(arrivals):
            qa_history_elapsed_s.append((dispatch - min(arrivals)) / 1_000_000_000)

    qa_history_calls: list[dict[str, Any]] = []
    qa_mixed_boundary_calls: list[dict[str, Any]] = []
    for call in calls:
        record_id = str(call.get("_record_id", ""))
        dispatch = qa_query_dispatch.get(record_id)
        start = call.get("start_perf_ns")
        end = call.get("end_perf_ns")
        if dispatch is None or not isinstance(start, int) or not isinstance(end, int):
            continue
        stage = str(call.get("stage") or "")
        if stage in {"qa_history_processing", "history"} or end <= dispatch:
            qa_history_calls.append(call)
        elif stage in {"qa_mixed_boundary", "mixed_boundary"} or start < dispatch < end:
            qa_mixed_boundary_calls.append(call)
    qa_history_call_intervals = [
        (int(call["start_perf_ns"]), int(call["end_perf_ns"]))
        for call in qa_history_calls
    ]
    qa_mixed_call_intervals = [
        (int(call["start_perf_ns"]), int(call["end_perf_ns"]))
        for call in qa_mixed_boundary_calls
    ]

    def call_sum(rows: list[dict[str, Any]], field: str) -> float | None:
        values = [value for row in rows if (value := _number(row.get(field))) is not None]
        return sum(values) if values else None
    input_tokens = [
        value for call in calls if (value := _number(call.get("input_text_tokens"))) is not None
    ]
    output_tokens = [
        value for call in calls if (value := _number(call.get("output_tokens"))) is not None
    ]
    submitted_frames = [
        value
        for call in calls
        if (value := _number(call.get("submitted_frame_occurrences"))) is not None
    ]
    submitted_pixels = [
        value for call in calls if (value := _number(call.get("submitted_pixels"))) is not None
    ]
    cached_tokens = [
        value for call in calls if (value := _number(call.get("num_cached_tokens"))) is not None
    ]

    submitted_by_observation: dict[tuple[str, str], int] = {}
    for event in events:
        record_id = str(event.get("record_id", ""))
        telemetry = event.get("telemetry", {})
        if not isinstance(telemetry, dict):
            continue
        frame_rows = telemetry.get("frame_telemetry", [])
        if not isinstance(frame_rows, list):
            continue
        for row in frame_rows:
            if not isinstance(row, dict):
                continue
            observation_id = row.get("observation_id")
            occurrences = _number(row.get("submitted_occurrences"))
            if (
                isinstance(observation_id, str)
                and occurrences is not None
                and occurrences > 0
            ):
                key = (record_id, observation_id)
                submitted_by_observation[key] = max(
                    submitted_by_observation.get(key, 0), int(occurrences)
                )

    failure_types: Counter[str] = Counter()
    failure_stages: Counter[str] = Counter()
    for record in records:
        if record.get("status") == "failed":
            failure_types[str(record.get("failed_reason") or "unspecified")] += 1
    for event in events:
        if _event_kind(event) == "failure" and event.get("telemetry", {}).get("failure_stage"):
            failure_stages[str(event["telemetry"]["failure_stage"])] += 1

    gpu_devices: dict[str, dict[str, Any]] = {}
    gpu_backend = None
    gpu_interval = None
    gpu_attribution_samples: list[bool] = []
    for telemetry in telemetries:
        resource = telemetry.get("gpu") or telemetry.get("resource_telemetry")
        if not isinstance(resource, dict):
            continue
        gpu_backend = resource.get("backend") or gpu_backend
        gpu_interval = resource.get("sample_interval_ms", gpu_interval)
        gpu_attribution_samples.append(resource.get("attribution_ok") is True)
        for device in resource.get("devices", []):
            if isinstance(device, dict):
                key = str(device.get("uuid") or device.get("device_id") or "unknown")
                current = gpu_devices.setdefault(key, dict(device))
                for field in (
                    "baseline_bytes",
                    "peak_bytes",
                    "peak_increment_bytes",
                    "peak_minus_baseline_bytes",
                ):
                    value = _number(device.get(field))
                    previous = _number(current.get(field))
                    if value is not None and (previous is None or value > previous):
                        current[field] = int(value)

    transport_frames = sum(
        int(value)
        for telemetry in telemetries
        if (value := _number(telemetry.get("transport_uploaded_image_count"))) is not None
    )
    transport_bytes = sum(
        int(value)
        for telemetry in telemetries
        if (value := _number(telemetry.get("transport_uploaded_image_total_bytes"))) is not None
    )
    events_by_record: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        events_by_record[str(event.get("record_id", ""))].append(event)
    answer_episodes = [
        episode
        for record_events in events_by_record.values()
        for episode in assemble_response_episodes(record_events)
    ]
    answer_count = len(answer_episodes)
    answer_first_token_count = sum(
        isinstance(episode.get("first_token_perf_ns"), int)
        for episode in answer_episodes
    )
    unique_submitted = len(submitted_by_observation)
    submitted_occurrence_total = sum(submitted_frames) if submitted_frames else None
    duplicate_frames = (
        max(0, int(submitted_occurrence_total) - unique_submitted)
        if submitted_occurrence_total is not None
        else None
    )
    dropped_frames = max(0, len(observations) - unique_submitted)
    gpu_attribution = bool(gpu_attribution_samples) and all(gpu_attribution_samples)

    return {
        "responsiveness": {
            "ttft_ms": _distribution(ttft, len(query_groups), "ms"),
            "response_total_ms": _distribution(response_total, len(query_groups), "ms"),
            "proactive_response_latency_ms": {
                **_distribution(
                    proactive_latency,
                    proactive_latency_population,
                    "ms",
                ),
                "population": "strict_in_window_answer_windows",
            },
            "frame_processing_ms": _distribution(frame_processing, len(observations), "ms"),
            "frame_lag_ms": _distribution(frame_lag, len(observations), "ms"),
            "on_time_frame_rate": {
                "numerator": sum(on_time),
                "denominator": len(on_time),
                "value": sum(on_time) / len(on_time) if on_time else None,
                "coverage": len(on_time) / len(observations) if observations else None,
            },
            "stream_completion_rate": {
                "numerator": len(committed),
                "denominator": len(observations),
                "value": len(committed) / len(observations) if observations else None,
            },
            "dropped_frame_rate": {
                "numerator": dropped_frames,
                "denominator": len(observations),
                "value": dropped_frames / len(observations)
                if observations
                else None,
            },
        },
        "visual_workload": {
            "core_delivered_frames": len(observations),
            "submitted_frame_occurrences": submitted_occurrence_total,
            "unique_submitted_frames": unique_submitted,
            "duplicate_frame_occurrences": duplicate_frames,
            "dropped_frames": dropped_frames,
            "submitted_pixels": sum(submitted_pixels) if submitted_pixels else None,
            "transport_uploaded_images": transport_frames,
            "transport_uploaded_bytes": transport_bytes,
            "model_call_frame_coverage": len(submitted_frames) / len(calls) if calls else None,
            "model_call_pixel_coverage": len(submitted_pixels) / len(calls) if calls else None,
        },
        "text_and_inference": {
            "input_text_tokens": sum(input_tokens) if input_tokens else None,
            "output_tokens": sum(output_tokens) if output_tokens else None,
            "prefix_cached_tokens": sum(cached_tokens) if cached_tokens else None,
            "input_token_coverage": len(input_tokens) / len(calls) if calls else None,
            "output_token_coverage": len(output_tokens) / len(calls) if calls else None,
            "prefix_cache_coverage": len(cached_tokens) / len(calls) if calls else None,
            "model_call_count": len(calls),
            "inference_wall_time_s": _union_seconds(call_intervals),
            "model_call_interval_coverage": len(call_intervals) / len(calls) if calls else None,
            "calls_by_stage": dict(Counter(str(call.get("stage", "unknown")) for call in calls)),
        },
        "qa_history_processing": {
            "record_count": len(qa_record_ids),
            "query_boundary_count": len(qa_query_dispatch),
            "history_elapsed_wall_time_s": _distribution(
                qa_history_elapsed_s, len(qa_record_ids), "s"
            ),
            "frame_processing_ms": _distribution(
                qa_history_frame_processing, len(qa_observations), "ms"
            ),
            "model_call_count": len(qa_history_calls),
            "mixed_boundary_model_call_count": len(qa_mixed_boundary_calls),
            "inference_wall_time_s": _union_seconds(qa_history_call_intervals),
            "mixed_boundary_inference_wall_time_s": _union_seconds(
                qa_mixed_call_intervals
            ),
            "submitted_frame_occurrences": call_sum(
                qa_history_calls, "submitted_frame_occurrences"
            ),
            "submitted_pixels": call_sum(qa_history_calls, "submitted_pixels"),
            "input_text_tokens": call_sum(qa_history_calls, "input_text_tokens"),
            "output_tokens": call_sum(qa_history_calls, "output_tokens"),
            "mixed_boundary_submitted_frame_occurrences": call_sum(
                qa_mixed_boundary_calls, "submitted_frame_occurrences"
            ),
            "mixed_boundary_submitted_pixels": call_sum(
                qa_mixed_boundary_calls, "submitted_pixels"
            ),
            "mixed_boundary_input_text_tokens": call_sum(
                qa_mixed_boundary_calls, "input_text_tokens"
            ),
            "mixed_boundary_output_tokens": call_sum(
                qa_mixed_boundary_calls, "output_tokens"
            ),
            "model_call_interval_coverage": (
                len(qa_history_calls)
                / (len(qa_history_calls) + len(qa_mixed_boundary_calls))
                if qa_history_calls or qa_mixed_boundary_calls
                else None
            ),
        },
        "gpu_memory": {
            "backend": gpu_backend,
            "sample_interval_ms": gpu_interval,
            "attribution_ok": gpu_attribution,
            "devices": list(gpu_devices.values()),
            "telemetry_available": bool(gpu_devices),
        },
        "reliability": {
            "record_completion_rate": {
                "numerator": completed,
                "denominator": record_count,
                "value": completed / record_count if record_count else None,
            },
            "failure_rate": {
                "numerator": failed,
                "denominator": record_count,
                "value": failed / record_count if record_count else None,
            },
            "failure_types": dict(failure_types),
            "failure_stages": dict(failure_stages),
            "timeout_count": sum(bool(record.get("timed_out")) for record in records),
            "retry_count": sum(int(record.get("retry_count", 0) or 0) for record in records),
        },
        "telemetry_coverage": {
            "frame_commit": len(committed) / len(observations) if observations else None,
            "frame_processing": len(frame_processing) / len(observations) if observations else None,
            "frame_lag": len(frame_lag) / len(observations) if observations else None,
            "on_time_frame": len(on_time) / len(observations) if observations else None,
            "query_ttft": len(ttft) / len(query_groups) if query_groups else None,
            "query_response_total": len(response_total) / len(query_groups)
            if query_groups
            else None,
            "proactive_response_latency": len(proactive_latency)
            / proactive_latency_population
            if proactive_latency_population
            else None,
            "response_first_token": answer_first_token_count / answer_count
            if answer_count
            else None,
            "model_call_intervals": len(call_intervals) / len(calls) if calls else None,
            "submitted_frames": len(submitted_frames) / len(calls) if calls else None,
            "submitted_pixels": len(submitted_pixels) / len(calls) if calls else None,
            "input_text_tokens": len(input_tokens) / len(calls) if calls else None,
            "output_tokens": len(output_tokens) / len(calls) if calls else None,
            "prefix_cache": len(cached_tokens) / len(calls) if calls else None,
            "gpu_memory": bool(gpu_devices) and gpu_attribution,
        },
    }


def assess_official_eligibility(
    task: str,
    metrics: Mapping[str, Any],
    *,
    synthetic: bool,
    provisional: bool,
) -> dict[str, Any]:
    """Return a publication gate without conflating validity with eligibility."""

    reasons: list[str] = []
    if synthetic:
        reasons.append("synthetic_run")
    if provisional:
        reasons.append("provisional_data_release")

    execution = metrics.get("execution_track", {})
    if not isinstance(execution, Mapping):
        execution = {}
    if execution.get("pacing") == "logical":
        reasons.append("logical_pacing_diagnostic")
    if task == "proactive" and execution.get("proactive_primary_eligible") is not True:
        reasons.append("proactive_not_native_autonomous_wall_clock")
    if task == "proactive":
        trigger_metadata = metrics.get("trigger_metadata", {})
        if (
            not isinstance(trigger_metadata, Mapping)
            or trigger_metadata.get("complete") is not True
        ):
            reasons.append("missing_or_invalid_trigger_annotations")

    telemetry = metrics.get("telemetry", {})
    if not isinstance(telemetry, Mapping):
        telemetry = {}
    coverage = telemetry.get("telemetry_coverage", {})
    if not isinstance(coverage, Mapping):
        coverage = {}

    required_coverage = [
        "model_call_intervals",
        "submitted_frames",
        "submitted_pixels",
        "input_text_tokens",
        "output_tokens",
    ]
    if execution.get("visual_state") == "Native Streaming":
        required_coverage.extend(["frame_commit", "frame_processing"])
    if task == "qa":
        required_coverage.extend(["query_ttft", "query_response_total"])
    else:
        required_coverage.extend(["proactive_response_latency", "response_first_token"])

    for name in required_coverage:
        value = coverage.get(name)
        # No emitted response makes response-only coverage inapplicable rather
        # than missing; misses remain in the quality denominator.
        if value is None and name in {"proactive_response_latency", "response_first_token"}:
            continue
        if not isinstance(value, (int, float)) or float(value) < 1.0 - 1e-12:
            reasons.append(f"incomplete_telemetry:{name}")

    gpu = telemetry.get("gpu_memory", {})
    if not isinstance(gpu, Mapping) or gpu.get("attribution_ok") is not True:
        reasons.append("incomplete_telemetry:gpu_memory_attribution")

    judge = metrics.get("judge", {})
    if isinstance(judge, Mapping):
        errors = judge.get("error_counts", {})
        if isinstance(errors, Mapping) and any(int(value or 0) > 0 for value in errors.values()):
            reasons.append("judge_incomplete")

    return {
        "official_eligible": not reasons,
        "reasons": sorted(set(reasons)),
        "policy": "osb-official-eligibility-v2",
    }


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<think>[\s\S]*?</think>\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("<think>", "").replace("</think>", "")
    text = re.split(r"\n\s*(?:user|assistant|system)\s*\n", text, maxsplit=1, flags=re.IGNORECASE)[
        0
    ]
    # Some local generation templates leave a standalone answer delimiter
    # before the actual response (for example, ": 1").  Treat that delimiter
    # as formatting while preserving all substantive punctuation and text.
    text = re.sub(r"^\s*[:：]\s*", "", text)
    return " ".join(text.strip().lower().split())


def extract_choice(value: Any, option_labels: set[str] | None = None) -> str | None:
    # Preserve existing single-label formatting normalization. Do not mine
    # prose or option-plus-text for incidental letters. Raw text is immutable.
    text = normalize_text(value).upper()
    labels = {"A", "B", "C", "D"} if option_labels is None else option_labels
    if not labels:
        return None
    label_class = "".join(sorted(re.escape(label) for label in labels))
    exact = re.fullmatch(rf"\s*[\[(]?([{label_class}])[\])]?[.)]?\s*", text)
    if exact:
        return exact.group(1)
    return None


def prediction_from_query_events(events: list[dict[str, Any]]) -> str | None:
    """Assemble the answer episode emitted after a QA query dispatch.

    Streaming adapters emit delta fragments (for example ``A`` followed by
    ``.``).  The last fragment is not the answer.  Use the response episode
    assembler and restrict selection to fragments carrying the QA query
    dispatch timestamp so pre-query WAIT/answer events cannot become the QA
    prediction.
    """

    episodes = assemble_response_episodes(events)
    query_episodes: list[dict[str, Any]] = []
    for episode in episodes:
        source_indices = episode.get("source_event_indices", [])
        source_events = [
            events[index]
            for index in source_indices
            if isinstance(index, int) and 0 <= index < len(events)
        ]
        if any(
            isinstance(event.get("telemetry", {}).get("query_dispatch_perf_ns"), int)
            for event in source_events
        ):
            query_episodes.append(episode)
    if query_episodes:
        return str(query_episodes[-1].get("text") or "")
    return None


def score_qa(
    records: list[dict[str, Any]],
    *,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events_by_record: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events or []:
        events_by_record[str(event.get("record_id", ""))].append(event)
    scored: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        assembled_prediction = prediction_from_query_events(
            events_by_record.get(str(record.get("record_id", "")), [])
        )
        if assembled_prediction is not None:
            prediction = assembled_prediction
            item["prediction_stored"] = record.get("prediction", "")
            item["prediction_source"] = "assembled_events"
        else:
            prediction = record.get("prediction", "")
            item["prediction_source"] = "record"
        expected = str(record.get("answer", "")).strip().upper()
        option_labels = {
            match.group(1).upper()
            for option in record.get("options", [])
            if (match := re.match(r"^\s*([A-Z])(?:[.)]|\s)", str(option)))
        }
        if not option_labels:
            option_labels = {"A", "B", "C", "D"}
        choice = extract_choice(prediction, option_labels)
        item["prediction"] = prediction
        item["prediction_choice"] = choice
        item["score"] = int(choice == expected and expected in option_labels)
        scored.append(item)
    correct = sum(item["score"] for item in scored)
    failures = sum(1 for item in scored if item.get("failed_reason"))
    return {
        "task": "qa",
        "record_count": len(scored),
        "correct": correct,
        "accuracy": correct / len(scored) if scored else 0.0,
        "failure_count": failures,
        "scored_records": scored,
    }


def _answered(event: dict[str, Any]) -> bool:
    return _event_kind(event) == "answer" and normalize_text(event.get("text")) not in {"", "wait"}


def _legacy_events(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read the old ``model_steps`` shape without mutating the raw record."""

    events: list[dict[str, Any]] = []
    for index, step in enumerate(record.get("model_steps", []) or []):
        if not isinstance(step, Mapping):
            continue
        prediction = str(step.get("prediction") or "")
        kind = "wait" if normalize_text(prediction) in {"", "wait"} else "answer"
        telemetry = {}
        if isinstance(step.get("ttft_ms"), (int, float)):
            telemetry["ttft_ms"] = float(step["ttft_ms"])
        events.append(
            {
                "event_id": f"legacy-step-{index}",
                "kind": kind,
                "logical_time_s": float(step.get("step_t", 0.0)),
                "text": "WAIT" if kind == "wait" else prediction,
                "telemetry": telemetry,
            }
        )
    return events


def _window_contains(time_s: float, start_s: float, end_s: float, boundary: str) -> bool:
    if boundary == "inclusive":
        return start_s <= time_s <= end_s
    if boundary == "half_open":
        return start_s <= time_s < end_s
    raise ValueError("window boundary must be inclusive or half_open")


def _record_video_end_s(record: Mapping[str, Any]) -> float | None:
    """Return the measured source endpoint persisted by Core, if available.

    ``deadline_s`` is deliberately absent from this provenance helper. The
    score window endpoint is determined by GT windows, not by source duration.
    """

    value = record.get("video_duration_s")
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return max(0.0, float(value))
    return None


def _trigger_annotations(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    metadata = record.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return []
    annotations = metadata.get("trigger_annotations", [])
    if not isinstance(annotations, list):
        return []
    return [item for item in annotations if isinstance(item, Mapping)]


def _trigger_metadata_status(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Report whether every Proactive record carries aligned trigger metadata.

    Legacy releases remain scoreable for diagnostics through the point-trigger
    fallback below, but a missing annotation cannot support an official v4
    result because it is impossible to distinguish point and state windows.
    """
    missing: list[str] = []
    malformed: list[str] = []
    for record in records:
        record_id = str(record.get("record_id", ""))
        metadata = record.get("metadata")
        annotations = (
            metadata.get("trigger_annotations")
            if isinstance(metadata, Mapping)
            else None
        )
        windows = record.get("windows", []) or []
        if not isinstance(annotations, list):
            missing.append(record_id)
            continue
        if len(annotations) != len(windows):
            malformed.append(record_id)
            continue
        if windows and not annotations:
            missing.append(record_id)
            continue
        if any(not isinstance(annotation, Mapping) for annotation in annotations):
            malformed.append(record_id)
    invalid = missing + malformed
    return {
        "required": True,
        "complete": not invalid,
        "record_count": len(records),
        "valid_record_count": len(records) - len(invalid),
        "missing_record_count": len(missing),
        "malformed_record_count": len(malformed),
        "missing_record_ids_sample": missing[:10],
        "malformed_record_ids_sample": malformed[:10],
    }


def _proactive_window_specs(
    record: Mapping[str, Any], proactive_window_s: float
) -> list[dict[str, Any]]:
    """Materialize the versioned strict windows without mutating raw GT.

    V1 annotations carry point-trigger metadata for the fixed-tolerance track
    and state intervals for SSR-style tasks.  A legacy record without metadata
    is treated as a sequence of point triggers at its stored window starts so
    that v0 snapshots can still be evaluated under the new 5/10-second rule.
    """

    if proactive_window_s not in {5.0, 10.0}:
        raise ValueError("proactive_window_s must be exactly 5.0 or 10.0 seconds")
    raw_windows = record.get("windows", []) or []
    annotations = _trigger_annotations(record)
    starts: list[float] = []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_windows):
        if not isinstance(raw, Mapping):
            continue
        annotation = annotations[index] if index < len(annotations) else {}
        raw_start = float(raw.get("start_s", 0.0))
        annotation_start = annotation.get("response_window_start_s")
        if annotation_start is None:
            annotation_start = annotation.get("point_trigger_s")
        start = float(annotation_start) if annotation_start is not None else raw_start
        trigger_type = str(annotation.get("trigger_type") or "legacy_point")
        policy = str(annotation.get("response_policy") or "")
        is_state = trigger_type == "state_interval" or policy == "reviewed_state_interval"
        expected = str(annotation.get("answer") or raw.get("expected_answer", ""))
        normalized.append(
            {
                "index": index,
                "start_s": start,
                "raw_end_s": float(raw.get("end_s", start)),
                "expected_answer": expected,
                "trigger_type": trigger_type,
                "response_policy": policy or ("reviewed_state_interval" if is_state else "fixed_point_window"),
                "event_id": annotation.get("event_id"),
                "is_state_interval": is_state,
                "annotation": dict(annotation),
            }
        )
        starts.append(start)

    for position, spec in enumerate(normalized):
        next_start = next(
            (candidate for candidate in starts[position + 1:] if candidate > spec["start_s"]),
            None,
        )
        if spec["is_state_interval"]:
            annotation = spec["annotation"]
            end_value = annotation.get("response_window_end_s")
            if end_value is None:
                end_value = annotation.get("interval_end_s")
            end = float(end_value) if end_value is not None else spec["raw_end_s"]
            strict_kind = "state_interval"
        else:
            end = spec["start_s"] + proactive_window_s
            if next_start is not None:
                end = min(end, next_start)
            strict_kind = "point_trigger"
        end = max(end, spec["start_s"])
        spec["end_s"] = end
        spec["next_trigger_s"] = next_start
        spec["inter_trigger_gap_s"] = (
            next_start - spec["start_s"] if next_start is not None else None
        )
        spec["effective_window_duration_s"] = max(0.0, end - spec["start_s"])
        spec["crowded_window"] = bool(
            not spec["is_state_interval"]
            and next_start is not None
            and next_start - spec["start_s"] < proactive_window_s
        )
        spec["strict_kind"] = strict_kind
        if spec["is_state_interval"]:
            spec["eventual_end_s"] = end
        else:
            spec["eventual_end_s"] = (
                next_start
                if next_start is not None
                else end
            )
        spec["boundary"] = "half_open"
    return normalized


def _window_observation_count(
    events: list[dict[str, Any]], start_s: float, end_s: float | None
) -> int:
    count = 0
    for event in events:
        if _event_kind(event) != "observation":
            continue
        timestamp = float(event.get("logical_time_s", 0.0))
        if timestamp < start_s:
            continue
        if end_s is not None and timestamp >= end_s:
            continue
        count += 1
    return count


def _window_observable(events: list[dict[str, Any]], start_s: float, end_s: float | None) -> bool:
    return _window_observation_count(events, start_s, end_s) > 0


def _view_summary(
    rows: list[dict[str, Any]], *, unit: str, total_count: int | None = None
) -> dict[str, Any]:
    count = len(rows)
    score_sum = sum(float(row.get("score", 0.0)) for row in rows)
    fully_correct = sum(float(row.get("score", 0.0)) >= 1.0 for row in rows)
    answered = sum(bool(row.get("is_answered")) for row in rows)
    source_distribution = Counter(str(row.get("source", "unknown")) for row in rows)
    observable = sum(bool(row.get("observable")) for row in rows)
    summary: dict[str, Any] = {
        f"{unit}_count": count,
        "correct_windows" if unit == "window" else "correct_events": score_sum,
        "fully_correct_windows" if unit == "window" else "fully_correct_events": fully_correct,
        "window_score_sum" if unit == "window" else "eventual_score_sum": score_sum,
        "window_accuracy" if unit == "window" else "eventual_accuracy": score_sum / count if count else 0.0,
        "answered_window_count" if unit == "window" else "answered_event_count": answered,
        "no_output_count": sum(row.get("source") == "no_output" for row in rows),
        "before_window_count": sum(row.get("source") == "before_window" for row in rows),
        "observable_count": observable,
        "unobservable_count": count - observable,
        "observable_coverage": observable / count if count else None,
        "source_distribution": dict(source_distribution),
    }
    if total_count is not None:
        summary["total_window_count"] = total_count
    return summary


def _trigger_arrival_perf_ns(events: list[dict[str, Any]], start_s: float) -> int | None:
    for event in events:
        if _event_kind(event) != "observation":
            continue
        if float(event.get("logical_time_s", 0.0)) < start_s:
            continue
        arrival = _event_value(event, "arrival_perf_ns")
        if isinstance(arrival, int):
            return arrival
    return None


def _episode_latency_ms(
    episode: Mapping[str, Any], events: list[dict[str, Any]], window_start_s: float
) -> tuple[float | None, str | None]:
    trigger_ns = _trigger_arrival_perf_ns(events, window_start_s)
    response_ns = episode.get("scoring_perf_ns")
    source = episode.get("scoring_time_source")
    if not isinstance(response_ns, int):
        response_ns = episode.get("first_token_perf_ns")
        source = "first_token_perf_ns" if isinstance(response_ns, int) else None
    if isinstance(trigger_ns, int) and isinstance(response_ns, int) and response_ns >= trigger_ns:
        return (response_ns - trigger_ns) / 1_000_000, str(source) if source else None
    return None, None


def _not_scored_judge(method: str) -> JudgeResult:
    return JudgeResult(score=0.0, method=method, requested=False)


def score_proactive(
    records: list[dict[str, Any]],
    *,
    judge: JudgeRouter | None = None,
    proactive_window_s: float = 5.0,
    window_boundary: str = "half_open",
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score fixed point/state windows and a separate eventual-response view.

    ``deadline_s`` from old release records is never consulted. Point-event
    eventual credit ends at the next trigger. For the final point it ends at
    the final strict-window end; the Core never feeds an unbounded source-video
    tail after that window. State-event eventual credit ends at the annotated
    state interval.
    """

    judge = judge or JudgeRouter(mode="exact")
    scored: list[dict[str, Any]] = []
    outside = redundant = eventual_outside = eventual_redundant = failures = 0
    source_counts: Counter[str] = Counter()
    judge_methods_by_view: dict[str, Counter[str]] = {
        "strict": Counter(),
        "eventual": Counter(),
    }
    judge_errors_by_view: dict[str, Counter[str]] = {
        "strict": Counter(),
        "eventual": Counter(),
    }

    def record_judge(result: JudgeResult, view: str) -> None:
        judge_methods_by_view[view][result.method] += 1
        if result.error:
            judge_errors_by_view[view][result.method] += 1

    def score_episode(
        *,
        episode: Mapping[str, Any] | None,
        events: list[dict[str, Any]],
        expected_raw: str,
        question: str,
        task_type: str,
        source: str,
        start_s: float,
        view: str,
    ) -> tuple[float, JudgeResult, float | None, str]:
        prediction_raw = str(episode.get("text", "")) if episode else ""
        prediction = normalize_text(prediction_raw)
        if source in {"in_window", "eventual"} and episode is not None and prediction:
            judge_result = judge.score(
                question=question,
                gt_answer=expected_raw,
                prediction=prediction_raw,
                task_type=task_type,
            )
            score = float(judge_result.score)
            latency, _latency_source = _episode_latency_ms(episode, events, start_s)
        elif source == "before_window":
            judge_result = _not_scored_judge("before_window")
            score = 0.0
            latency = None
        else:
            judge_result = _not_scored_judge("no_output")
            score = 0.0
            latency = None
        record_judge(judge_result, view)
        return score, judge_result, latency, prediction

    events_by_record: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events or []:
        events_by_record[str(event.get("record_id", ""))].append(event)
    sidecar_is_authoritative = events is not None

    for record in records:
        record_events = (
            events_by_record.get(str(record.get("record_id", "")), [])
            if sidecar_is_authoritative
            else record.get("events", []) or _legacy_events(record)
        )
        episodes = assemble_response_episodes(record_events)
        answered_episodes = [episode for episode in episodes if normalize_text(episode.get("text"))]
        windows = _proactive_window_specs(record, proactive_window_s)
        per_window: list[dict[str, Any]] = []
        per_eventual: list[dict[str, Any]] = []
        task_type = str(record.get("task_type") or "")
        question = str(record.get("instruction") or record.get("question") or "")
        used_window_episodes: set[int] = set()
        for window in windows:
            start_s = float(window["start_s"])
            end_s = float(window["end_s"])
            in_window = [
                (index, episode)
                for index, episode in enumerate(answered_episodes)
                if _window_contains(
                    float(episode["start_video_time_s"]),
                    start_s,
                    end_s,
                    window_boundary,
                )
            ]
            before_window = [
                (index, episode)
                for index, episode in enumerate(answered_episodes)
                if index not in used_window_episodes
                and float(episode["start_video_time_s"]) < start_s
            ]
            available_in_window = [item for item in in_window if item[0] not in used_window_episodes]
            chosen_index: int | None = None
            if available_in_window:
                chosen_index, chosen = available_in_window[0]
                source = "in_window"
            elif before_window:
                chosen_index, chosen = before_window[-1]
                source = "before_window"
            else:
                chosen = None
                source = "no_output"
            if chosen_index is not None:
                used_window_episodes.add(chosen_index)
            expected_raw = str(window["expected_answer"])
            score, judge_result, _unused_latency_ms, prediction = score_episode(
                episode=chosen,
                events=record_events,
                expected_raw=expected_raw,
                question=question,
                task_type=task_type,
                source=source,
                start_s=start_s,
                view="strict",
            )
            latency_ms, latency_time_source = (
                _episode_latency_ms(chosen, record_events, start_s)
                if chosen is not None and source == "in_window"
                else (None, None)
            )
            observed_frame_count = _window_observation_count(record_events, start_s, end_s)
            observable = observed_frame_count > 0
            per_window.append(
                {
                    "start_s": start_s,
                    "end_s": end_s,
                    "expected_answer": expected_raw,
                    "trigger_type": window["trigger_type"],
                    "response_policy": window["response_policy"],
                    "event_id": window.get("event_id"),
                    "next_trigger_s": window.get("next_trigger_s"),
                    "inter_trigger_gap_s": window.get("inter_trigger_gap_s"),
                    "effective_window_duration_s": window["effective_window_duration_s"],
                    "crowded_window": window["crowded_window"],
                    "prediction": str(chosen.get("text", "")) if chosen else "",
                    "prediction_clean": prediction,
                    "response_id": chosen.get("response_id") if chosen else None,
                    "response_start_s": chosen.get("start_video_time_s") if chosen else None,
                    "response_end_s": chosen.get("end_video_time_s") if chosen else None,
                    "source_event_ids": chosen.get("source_event_ids", []) if chosen else [],
                    "source": source,
                    "score": score,
                    "is_answered": bool(chosen),
                    "latency_ms": latency_ms,
                    "latency_time_source": latency_time_source,
                    "observable": observable,
                    "observed_frame_count": observed_frame_count,
                    "observability_status": "observable" if observable else "protocol_unobservable",
                    "score_method": judge_result.method,
                    "judge": judge_result.as_dict(),
                }
            )
            source_counts[source] += 1
        # Eventual matching is a separate assignment view.  It deliberately
        # does not reuse the strict-window assignment or its before-trigger
        # diagnostics.
        used_eventual_episodes: set[int] = set()
        for window in windows:
            start_s = float(window["start_s"])
            eventual_end = window.get("eventual_end_s")
            eventual_end_s = float(eventual_end) if eventual_end is not None else None
            candidates = [
                (index, episode)
                for index, episode in enumerate(answered_episodes)
                if index not in used_eventual_episodes
                and float(episode["start_video_time_s"]) >= start_s
                and (eventual_end_s is None or float(episode["start_video_time_s"]) < eventual_end_s)
            ]
            if candidates:
                chosen_index, chosen = candidates[0]
                used_eventual_episodes.add(chosen_index)
                source = "eventual"
            else:
                chosen = None
                source = "no_output"
            expected_raw = str(window["expected_answer"])
            score, judge_result, _unused_latency_ms, prediction = score_episode(
                episode=chosen,
                events=record_events,
                expected_raw=expected_raw,
                question=question,
                task_type=task_type,
                source=source,
                start_s=start_s,
                view="eventual",
            )
            latency_ms, latency_time_source = (
                _episode_latency_ms(chosen, record_events, start_s)
                if chosen is not None and source == "eventual"
                else (None, None)
            )
            observed_frame_count = _window_observation_count(
                record_events, start_s, eventual_end_s
            )
            observable = observed_frame_count > 0
            per_eventual.append(
                {
                    "start_s": start_s,
                    "end_s": eventual_end_s,
                    "expected_answer": expected_raw,
                    "trigger_type": window["trigger_type"],
                    "response_policy": window["response_policy"],
                    "event_id": window.get("event_id"),
                    "next_trigger_s": window.get("next_trigger_s"),
                    "inter_trigger_gap_s": window.get("inter_trigger_gap_s"),
                    "effective_window_duration_s": window["effective_window_duration_s"],
                    "crowded_window": window["crowded_window"],
                    "prediction": str(chosen.get("text", "")) if chosen else "",
                    "prediction_clean": prediction,
                    "response_id": chosen.get("response_id") if chosen else None,
                    "response_start_s": chosen.get("start_video_time_s") if chosen else None,
                    "response_end_s": chosen.get("end_video_time_s") if chosen else None,
                    "source_event_ids": chosen.get("source_event_ids", []) if chosen else [],
                    "source": source,
                    "score": score,
                    "is_answered": bool(chosen),
                    "latency_ms": latency_ms,
                    "latency_time_source": latency_time_source,
                    "observable": observable,
                    "observed_frame_count": observed_frame_count,
                    "observability_status": "observable" if observable else "protocol_unobservable",
                    "score_method": judge_result.method,
                    "judge": judge_result.as_dict(),
                }
            )
        for episode in answered_episodes:
            in_any = any(
                _window_contains(
                    float(episode["start_video_time_s"]),
                    float(window["start_s"]),
                    float(window["end_s"]),
                    window_boundary,
                )
                for window in windows
            )
            if not in_any:
                outside += 1
        for window in windows:
            in_window = [
                episode
                for episode in answered_episodes
                if _window_contains(
                    float(episode["start_video_time_s"]),
                    float(window["start_s"]),
                    float(window["end_s"]),
                    window_boundary,
                )
            ]
            redundant += max(0, len(in_window) - 1)
            eventual_in_window = [
                episode
                for episode in answered_episodes
                if float(episode["start_video_time_s"]) >= float(window["start_s"])
                and (
                    window.get("eventual_end_s") is None
                    or float(episode["start_video_time_s"]) < float(window["eventual_end_s"])
                )
            ]
            eventual_redundant += max(0, len(eventual_in_window) - 1)
        eventual_outside += sum(
            not any(
                float(episode["start_video_time_s"]) >= float(window["start_s"])
                and (
                    window.get("eventual_end_s") is None
                    or float(episode["start_video_time_s"]) < float(window["eventual_end_s"])
                )
                for window in windows
            )
            for episode in answered_episodes
        )
        failures += int(bool(record.get("failed_reason")))
        strict_all = _view_summary(per_window, unit="window")
        strict_observable = _view_summary(
            [row for row in per_window if row["observable"]],
            unit="window",
            total_count=len(per_window),
        )
        crowded = _view_summary(
            [row for row in per_window if row["crowded_window"]], unit="window"
        )
        non_crowded = _view_summary(
            [row for row in per_window if not row["crowded_window"]], unit="window"
        )
        eventual = _view_summary(per_eventual, unit="event")
        item = dict(record)
        item["response_episodes"] = episodes
        item["response_episode_count"] = len(episodes)
        item["per_window_results"] = per_window
        item["per_eventual_results"] = per_eventual
        item["proactive_score_views"] = {
            "strict_all_window": strict_all,
            "strict_observable_window": strict_observable,
            "post_trigger_eventual": eventual,
        }
        item["window_density_views"] = {
            "crowded_window": crowded,
            "non_crowded_window": non_crowded,
        }
        scored.append(item)
    judge_metadata = dict(judge.metadata)
    judge_metadata["window_boundary"] = window_boundary
    judge_metadata["proactive_window_s"] = proactive_window_s
    strict_all_rows = [
        row
        for item in scored
        for row in item.get("per_window_results", [])
    ]
    strict_observable_rows = [row for row in strict_all_rows if row.get("observable")]
    eventual_rows = [
        row
        for item in scored
        for row in item.get("per_eventual_results", [])
    ]
    crowded_rows = [row for row in strict_all_rows if row.get("crowded_window") is True]
    non_crowded_rows = [row for row in strict_all_rows if row.get("crowded_window") is not True]
    strict_all = _view_summary(strict_all_rows, unit="window")
    strict_observable = _view_summary(
        strict_observable_rows,
        unit="window",
        total_count=len(strict_all_rows),
    )
    eventual = _view_summary(eventual_rows, unit="event")
    crowded = _view_summary(crowded_rows, unit="window")
    non_crowded = _view_summary(non_crowded_rows, unit="window")
    return {
        "task": "proactive",
        "record_count": len(scored),
        "trigger_metadata": _trigger_metadata_status(
            [record for record in records if isinstance(record, Mapping)]
        ),
        "proactive_window_s": proactive_window_s,
        "window_boundary": window_boundary,
        "strict_all_window": strict_all,
        "strict_observable_window": strict_observable,
        "post_trigger_eventual": eventual,
        "window_density_views": {
            "crowded_window": crowded,
            "non_crowded_window": non_crowded,
        },
        "crowded_window_count": len(crowded_rows),
        "non_crowded_window_count": len(non_crowded_rows),
        # Historical top-level aliases point to strict-all, the primary
        # end-to-end denominator.  New consumers should use the explicit
        # view objects above.
        "window_count": strict_all["window_count"],
        "correct_windows": strict_all["correct_windows"],
        "fully_correct_windows": strict_all["fully_correct_windows"],
        "window_score_sum": strict_all["window_score_sum"],
        "window_accuracy": strict_all["window_accuracy"],
        "outside_window_intrusion_count": outside,
        "outside_window_intrusion_rate": outside / strict_all["window_count"]
        if strict_all["window_count"]
        else 0.0,
        "redundant_response_intrusion_count": redundant,
        "redundant_response_rate": redundant / strict_all["window_count"]
        if strict_all["window_count"]
        else 0.0,
        "eventual_outside_response_count": eventual_outside,
        "eventual_redundant_response_count": eventual_redundant,
        "failure_count": failures,
        "window_source_distribution": dict(source_counts),
        "judge": {
            **judge_metadata,
            # Top-level compatibility counters describe the strict primary
            # view. Eventual coverage is reported separately and is not added
            # a second time.
            "method_counts": dict(judge_methods_by_view["strict"]),
            "error_counts": dict(judge_errors_by_view["strict"]),
            "method_counts_by_view": {
                view: dict(counts) for view, counts in judge_methods_by_view.items()
            },
            "error_counts_by_view": {
                view: dict(counts) for view, counts in judge_errors_by_view.items()
            },
            "requested_window_count": sum(
                1
                for item in scored
                for window in item.get("per_window_results", [])
                if window.get("judge", {}).get("requested") is True
            ),
            "requested_eventual_count": sum(
                1
                for item in scored
                for event in item.get("per_eventual_results", [])
                if event.get("judge", {}).get("requested") is True
            ),
        },
        "scored_records": scored,
    }


def score_records(
    task: str,
    records: list[dict[str, Any]],
    *,
    judge: JudgeRouter | None = None,
    events: list[dict[str, Any]] | None = None,
    proactive_window_s: float | None = None,
    window_boundary: str = "half_open",
) -> dict[str, Any]:
    return (
        score_qa(records, events=events)
        if task == "qa"
        else score_proactive(
            records,
            judge=judge,
            proactive_window_s=5.0 if proactive_window_s is None else float(proactive_window_s),
            window_boundary=window_boundary,
            events=events,
        )
    )
