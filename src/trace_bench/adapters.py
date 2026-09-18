"""Model-independent adapter protocol and deterministic CI adapter."""

from __future__ import annotations

import importlib
import inspect
import time
from typing import Any, Protocol

from .models import (
    AdapterCapabilities,
    EventKind,
    ModelEvent,
    Observation,
    QueryRequest,
    RecordContext,
    RunConfig,
    TaskName,
)


class AdapterSession(Protocol):
    def observe(self, observation: Observation) -> list[ModelEvent]: ...

    def query(self, request: QueryRequest) -> list[ModelEvent]: ...

    def close(self) -> list[ModelEvent]: ...


class Adapter(Protocol):
    capabilities: AdapterCapabilities

    def open(self, context: RecordContext) -> AdapterSession: ...

    def close(self) -> None: ...


def _event_answer(text: str, logical_time_s: float, *, raw_output: Any = None) -> ModelEvent:
    return ModelEvent(
        kind=EventKind.ANSWER, logical_time_s=logical_time_s, text=text, raw_output=raw_output
    )


def _event_wait(logical_time_s: float) -> ModelEvent:
    return ModelEvent(kind=EventKind.WAIT, logical_time_s=logical_time_s, text="WAIT")


class _TestDoubleSession:
    def __init__(self, context: RecordContext, autonomous: bool = False, fail: bool = False):
        self.context = context
        self.autonomous = autonomous
        self.fail = fail
        self.observations: list[Observation] = []
        self.emitted_windows: set[int] = set()

    def observe(self, observation: Observation) -> list[ModelEvent]:
        self.observations.append(observation)
        commit = {
            "frame_commit": True,
            "commit_perf_ns": time.perf_counter_ns(),
            "adapter_submitted_frame_count": 1,
            "adapter_unique_submitted_frame_count": 1,
            "adapter_submitted_pixel_count": int(
                observation.rgb.shape[0] * observation.rgb.shape[1]
            ),
        }
        if self.fail:
            return [
                ModelEvent(
                    kind=EventKind.FAILURE,
                    logical_time_s=observation.timestamp_s,
                    status="failed",
                    failed_reason="synthetic test failure",
                    telemetry=commit,
                )
            ]
        if not self.autonomous or self.context.task is not TaskName.PROACTIVE:
            return [
                ModelEvent(
                    kind=EventKind.TELEMETRY,
                    logical_time_s=observation.timestamp_s,
                    telemetry=commit,
                )
            ]
        record = self.context.record
        events: list[ModelEvent] = []
        for index, window in enumerate(record.windows):  # type: ignore[union-attr]
            if (
                index not in self.emitted_windows
                and window.start_s <= observation.timestamp_s < window.end_s
            ):
                self.emitted_windows.add(index)
                events.append(
                    _event_answer(
                        window.expected_answer,
                        observation.timestamp_s,
                        raw_output={"synthetic": True},
                    )
                )
        if events:
            events[0].telemetry.update(commit)
        else:
            events.append(
                ModelEvent(
                    kind=EventKind.TELEMETRY,
                    logical_time_s=observation.timestamp_s,
                    telemetry=commit,
                )
            )
        return events

    def query(self, request: QueryRequest) -> list[ModelEvent]:
        if self.fail:
            return [
                ModelEvent(
                    kind=EventKind.FAILURE,
                    logical_time_s=request.logical_time_s,
                    status="failed",
                    failed_reason="synthetic test failure",
                )
            ]
        record = self.context.record
        if request.kind == "qa":
            return [
                _event_answer(record.answer, request.logical_time_s, raw_output={"synthetic": True})
            ]  # type: ignore[union-attr]
        for window in record.windows:  # type: ignore[union-attr]
            if window.start_s <= request.logical_time_s < window.end_s:
                return [
                    _event_answer(
                        window.expected_answer,
                        request.logical_time_s,
                        raw_output={"synthetic": True},
                    )
                ]
        return [_event_wait(request.logical_time_s)]

    def close(self) -> list[ModelEvent]:
        return []


class TestDoubleAdapter:
    """Deterministic adapter used for CI and local Core smoke tests only."""

    metadata = {
        "adapter_name": "deterministic-test-double",
        "adapter_version": "v0",
        "model": {"identity": "synthetic-oracle"},
        "generation": {},
    }

    def __init__(
        self,
        *,
        autonomous: bool = False,
        fail: bool = False,
        pacing: str = "logical",
        **_: Any,
    ):
        self.autonomous = autonomous
        self.fail = fail
        self.capabilities = AdapterCapabilities(
            state_lifetime="persistent" if autonomous else "stateless",
            response_mode="autonomous" if autonomous else "polling",
            pacing=pacing,
            deployment="in_process",
            telemetry=True,
        )

    def open(self, context: RecordContext) -> AdapterSession:
        return _TestDoubleSession(context, autonomous=self.autonomous, fail=self.fail)

    def close(self) -> None:
        return None


def load_adapter(reference: str, config: dict[str, Any] | None = None) -> Adapter:
    if ":" not in reference:
        raise ValueError("adapter must use module:object syntax")
    module_name, object_name = reference.split(":", 1)
    module = importlib.import_module(module_name)
    target: Any = module
    for part in object_name.split("."):
        target = getattr(target, part)
    kwargs = config or {}
    if inspect.isclass(target):
        adapter = target(**kwargs)
    elif callable(target) and not hasattr(target, "open"):
        adapter = target(**kwargs)
    else:
        adapter = target
    if not hasattr(adapter, "open") or not hasattr(adapter, "capabilities"):
        raise TypeError(f"adapter {reference!r} must expose capabilities and open(context)")
    try:
        capabilities = AdapterCapabilities.model_validate(adapter.capabilities)
    except Exception as exc:
        raise TypeError(f"adapter {reference!r} has invalid capabilities: {exc}") from exc
    try:
        adapter.capabilities = capabilities  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        # A read-only property is still usable; callers validate the value again.
        pass
    return adapter


def validate_adapter(adapter: Adapter, task: TaskName, config: RunConfig) -> AdapterCapabilities:
    """Validate the capabilities that the V0 Core can actually execute."""

    try:
        capabilities = AdapterCapabilities.model_validate(adapter.capabilities)
    except Exception as exc:
        raise TypeError(f"adapter capabilities are invalid: {exc}") from exc
    if capabilities.evidence_delivery != "decoded_frames":
        raise ValueError("TRACE only supports adapters receiving Core-decoded frames")
    if capabilities.pacing != config.pacing:
        raise ValueError(
            f"adapter pacing {capabilities.pacing!r} does not match run pacing {config.pacing!r}"
        )
    # Native adapters may use the same incremental generation path for QA and
    # Proactive. Their response_mode describes the proactive trigger behavior;
    # QA still injects a query through session.query().
    if (
        task is TaskName.PROACTIVE
        and capabilities.response_mode == "autonomous"
        and capabilities.state_lifetime != "persistent"
    ):
        raise ValueError("autonomous proactive adapters must declare persistent state")
    return capabilities
