"""Canonical data and runtime models for TRACE."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskName(str, Enum):
    QA = "qa"
    PROACTIVE = "proactive"


class RecordStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FatalEvaluationError(RuntimeError):
    """An error that invalidates the current model process/session.

    Adapters must raise this for unrecoverable runtime failures such as a
    poisoned CUDA context.  The Core checkpoints completed records and stops
    the run instead of converting the error into an ordinary per-record
    failure and continuing with an unusable model process.
    """


class EventKind(str, Enum):
    ANSWER = "answer"
    WAIT = "wait"
    FAILURE = "failure"
    OBSERVATION = "observation"
    TELEMETRY = "telemetry"


class ResponseWindow(BaseModel):
    start_s: float
    end_s: float
    expected_answer: str = ""


class QARecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    source_id: str
    task: Literal["qa"] = "qa"
    task_type: str = ""
    video_path: str
    question: str
    options: list[str] = Field(default_factory=list)
    answer: str
    question_time_s: float
    evidence_anchor_s: float
    memory_length: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProactiveRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    source_id: str
    task: Literal["proactive"] = "proactive"
    task_type: str = ""
    video_path: str
    instruction: str
    instruction_time_s: float
    # Kept optional only to read older v0/v1 release snapshots.  The current
    # protocol never uses this legacy source deadline for sampling or scoring.
    deadline_s: Optional[float] = None
    windows: list[ResponseWindow] = Field(default_factory=list)
    memory_length: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReleaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_id: str
    status: Literal["private_provisional", "public"]
    schema_version: str
    qa_file: str
    proactive_file: str
    tiny_qa_ids_file: str
    tiny_proactive_ids_file: str
    counts: dict[str, int] = Field(default_factory=dict)
    source_files: list[dict[str, Any]] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    video_root_notes: str = ""
    limitations: list[str] = Field(default_factory=list)


class AdapterCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_delivery: Literal["decoded_frames", "encoded_video"] = "decoded_frames"
    state_lifetime: Literal["stateless", "persistent"] = "stateless"
    response_mode: Literal["query", "polling", "autonomous"] = "query"
    # QA adapters that batch observations may need the query queued immediately
    # before the question-time frame. Such adapters must defer any response
    # until the subsequent observation call; ordinary query adapters keep the
    # historical after-observation timing.
    qa_query_timing: Literal["after_observation", "before_observation_deferred"] = (
        "after_observation"
    )
    pacing: Literal["logical", "wall_clock"] = "logical"
    deployment: Literal["in_process", "user_service"] = "in_process"
    telemetry: bool = False


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_dir: str
    task: TaskName
    subset: Literal["tiny", "full", "all"] = "tiny"
    adapter: str
    adapter_config: dict[str, Any] = Field(default_factory=dict)
    video_root: Optional[str] = None
    stream_fps: Literal[1.0] = 1.0
    qa_window_s: float = Field(default=10.0, ge=0)
    proactive_history_window_s: float = Field(default=5.0, ge=0)
    # Official point-trigger evaluation uses one of the two frozen tolerances.
    # The literal type gives a clear error instead of silently producing a
    # non-comparable leaderboard run.
    proactive_window_s: Literal[5.0, 10.0] = 5.0
    proactive_step_s: float = Field(default=5.0, gt=0)
    max_width: Optional[int] = Field(default=960, gt=0)
    jpeg_quality: int = Field(default=90, ge=1, le=100)
    temperature: float = Field(default=0.2, ge=0)
    pacing: Literal["logical", "wall_clock"] = "logical"
    checkpoint_every_records: int = Field(default=10, ge=1)
    output_dir: str = "runs/latest"
    resume: bool = True
    synthetic: bool = False
    config_version: str = "v4"
    # Scoring is configured independently from model execution so a completed
    # bundle can be rescored without loading the adapter or model weights.
    judge_mode: Literal["auto", "exact", "vlm"] = "auto"
    judge_base_url: Optional[str] = None
    judge_model: str = "Qwen3.5-35B-A3B"
    judge_api_key_env: str = "TRACE_VLM_JUDGE_API_KEY"
    judge_timeout_s: float = Field(default=60.0, gt=0)
    judge_temperature: float = Field(default=0.0, ge=0)
    semantic_task_types: list[str] = Field(default_factory=lambda: ["SSR", "CRR"])
    scorer_version: str = "osb-scoring-v6"


class QueryRequest(BaseModel):
    kind: Literal["qa", "proactive"]
    logical_time_s: float
    text: str
    dispatch_perf_ns: Optional[int] = None


class ModelEvent(BaseModel):
    kind: EventKind
    logical_time_s: float
    text: str = ""
    status: str = "ok"
    failed_reason: Optional[str] = None
    raw_output: Any = None
    # Response assembly fields are intentionally provider-neutral.  Adapters
    # that emit complete answers may leave the defaults unchanged; streaming
    # adapters use response_id/sequence_id/text_mode/is_final to let Core group
    # fragments into one scored response episode.
    event_id: Optional[str] = None
    response_id: Optional[str] = None
    sequence_id: Optional[int | str] = None
    text_mode: Literal["complete", "delta", "snapshot"] = "complete"
    is_final: Optional[bool] = None
    response_decision: Optional[Literal["response", "silent"]] = None
    telemetry: dict[str, Any] = Field(default_factory=dict)


@dataclass
class Observation:
    timestamp_s: float
    frame_index: int
    rgb: Any
    observation_id: Optional[str] = None
    scheduled_arrival_perf_ns: Optional[int] = None
    arrival_perf_ns: Optional[int] = None
    visible_until_s: Optional[float] = None


@dataclass
class RecordContext:
    record: QARecord | ProactiveRecord
    task: TaskName
    video_path: str
    evidence_start_s: float
    evidence_end_s: float
    config: RunConfig


@dataclass
class RunRecord:
    record_id: str
    task: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
