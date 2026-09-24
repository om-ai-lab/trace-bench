"""Configuration resolution and stable hashing."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .models import RunConfig, TaskName

CORE_STREAM_FPS = 1.0


def judge_env(name: str) -> str | None:
    """Read a judge setting from TRACE_VLM_JUDGE_* or the legacy OSB_* name."""
    return os.getenv(f"TRACE_{name}") or os.getenv(f"OSB_{name}") or None


DEFAULT_PRESET = {
    "stream_fps": 1.0,
    "qa_window_s": 10.0,
    # The legal prefix before a Proactive instruction is independent from the
    # post-trigger response tolerance.
    "proactive_history_window_s": 5.0,
    # The benchmark freezes W=5s for the current comparable profile. A run may
    # explicitly choose 10s, but adapters must never choose independently.
    "proactive_window_s": 5.0,
    "proactive_step_s": 5.0,
    "max_width": 960,
    "jpeg_quality": 90,
    "temperature": 0.2,
    "pacing": "logical",
    "checkpoint_every_records": 10,
    "config_version": "v4",
    "judge_mode": "auto",
    "judge_base_url": None,
    "judge_model": "Qwen3.5-35B-A3B",
    "judge_api_key_env": "TRACE_VLM_JUDGE_API_KEY",
    "judge_timeout_s": 60.0,
    "judge_temperature": 0.0,
    "semantic_task_types": ["SSR", "CRR"],
    "scorer_version": "osb-scoring-v6",
    "scoring_profile": "legacy",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def resolve_config(
    *,
    release_dir: Path,
    task: TaskName,
    subset: str,
    adapter: str,
    output_dir: Path,
    overrides: dict[str, Any] | None = None,
    adapter_config: dict[str, Any] | None = None,
    video_root: str | None = None,
    synthetic: bool = False,
    resume: bool = True,
) -> RunConfig:
    values = dict(DEFAULT_PRESET)
    preset_path = Path(__file__).resolve().parent / "presets" / "current.json"
    if preset_path.is_file():
        values.update(load_json(preset_path))
    # The public preset deliberately has no private endpoint.  A user-operated
    # judge service can be selected through the environment without changing
    # the repository or embedding credentials in a Run Bundle.
    if not values.get("judge_base_url"):
        values["judge_base_url"] = judge_env("VLM_JUDGE_BASE_URL")
    if judge_env("VLM_JUDGE_MODEL"):
        values["judge_model"] = judge_env("VLM_JUDGE_MODEL")
    if judge_env("VLM_JUDGE_MODE"):
        values["judge_mode"] = judge_env("VLM_JUDGE_MODE")
    values.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return RunConfig(
        release_dir=str(release_dir),
        task=task,
        subset=subset,
        adapter=adapter,
        adapter_config=adapter_config or {},
        video_root=str(video_root) if video_root is not None else None,
        output_dir=str(output_dir),
        synthetic=synthetic,
        resume=resume,
        **values,
    )
