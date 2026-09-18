"""Frozen, model-independent run configuration shown before evaluation."""

from __future__ import annotations

import inspect
import platform
import sys
from pathlib import Path
from typing import Any

import cv2

from . import __version__
from .adapters import Adapter
from .config import CORE_STREAM_FPS, stable_hash
from .data import Release, validate_release
from .models import AdapterCapabilities, RunConfig
from .sampling import RESIZE_POLICY, SAMPLER_IDENTITY, sha256_file

PREFLIGHT_SCHEMA = "osb-preflight-v4"
PROTOCOL_IDENTITY = "osb-incremental-decoded-rgb-v4"
CONTRACT_VERSION = "osb-contract-v4"


def _resolved_path(value: str | None) -> str | None:
    return str(Path(value).expanduser().resolve()) if value is not None else None


def _adapter_metadata(adapter: Adapter, reference: str) -> dict[str, Any]:
    declared = getattr(adapter, "metadata", {})
    if callable(declared):
        declared = declared()
    if not isinstance(declared, dict):
        raise TypeError("adapter metadata must be a JSON object")
    adapter_type = type(adapter)
    source_file = inspect.getsourcefile(adapter_type)
    return {
        "reference": reference,
        "implementation": f"{adapter_type.__module__}:{adapter_type.__qualname__}",
        "implementation_source": str(Path(source_file).resolve()) if source_file else None,
        "implementation_sha256": sha256_file(Path(source_file)) if source_file else None,
        "declared": declared,
    }


def _code_identities() -> dict[str, Any]:
    """Hash the Core/scorer/protocol sources that define a run's semantics."""

    package_root = Path(__file__).resolve().parent
    repository_root = package_root.parents[1]
    paths = {
        "core": package_root / "core.py",
        "models": package_root / "models.py",
        "preflight": package_root / "preflight.py",
        "prompts": package_root / "prompts.py",
        "scoring": package_root / "scoring.py",
        "sampling": package_root / "sampling.py",
        "data": package_root / "data.py",
        "config": package_root / "config.py",
        "adapters": package_root / "adapters.py",
        "bundle": package_root / "bundle.py",
        "evaluation_protocol": repository_root / "docs" / "evaluation-protocol.md",
    }
    return {
        name: {
            "source": str(path),
            "sha256": sha256_file(path) if path.is_file() else None,
        }
        for name, path in paths.items()
    }


def build_preflight_snapshot(
    config: RunConfig,
    release: Release,
    adapter: Adapter,
    capabilities: AdapterCapabilities,
    *,
    record_count: int,
) -> dict[str, Any]:
    """Build and hash the exact configuration that governs one run."""

    release_validation = validate_release(release.root)
    manifest_path = release.root / "manifest.json"
    video_root = Path(config.video_root).expanduser() if config.video_root else None
    if video_root is not None and (not video_root.exists() or not video_root.is_dir()):
        raise ValueError(f"video_root must be an existing directory: {video_root}")
    adapter_metadata = _adapter_metadata(adapter, config.adapter)

    snapshot: dict[str, Any] = {
        "preflight_schema": PREFLIGHT_SCHEMA,
        "software_version": __version__,
        "protocol": {
            "identity": PROTOCOL_IDENTITY,
            "contract": CONTRACT_VERSION,
            "config_version": config.config_version,
            "task": config.task.value,
            "subset": config.subset,
            "pacing": config.pacing,
            "execution_mode": "incremental_core_observations",
            "core_delivery_chunk_frames": 1,
            "qa_window_s": config.qa_window_s,
            "proactive_history_window_s": config.proactive_history_window_s,
            "proactive_history_policy": "fixed_independent_from_response_window",
            "proactive_window_s": config.proactive_window_s,
            "proactive_window_choices_s": [5.0, 10.0],
            "proactive_window_boundary": "half_open",
            "proactive_eventual_end": "next_trigger_or_final_strict_window_end",
            "proactive_evidence_end": (
                "last_strict_window_end_clamped_to_metadata_video_end_when_available"
            ),
            "video_duration_probe": "metadata_only_never_full_decode",
            "post_stream_response_policy": "remaining_strict_window",
            "legacy_deadline_used": False,
            "proactive_step_s": config.proactive_step_s,
            "qa_user_content_policy": "byte_identical_core_prompt",
            "qa_template_policy": "mechanical_role_control_serialization_only",
            "qa_ttft_start_policy": "core_semantic_query_arrival",
            "polling_same_timestamp_policy": "observe_then_query",
            "autonomous_response_time_policy": (
                "first_token_else_core_completion_fallback"
            ),
        },
        "data": {
            "release_dir": str(release.root.resolve()),
            "release_id": release.manifest.release_id,
            "release_status": release.manifest.status,
            "schema_version": release.manifest.schema_version,
            "release_manifest_sha256": sha256_file(manifest_path),
            "release_files": dict(sorted(release.manifest.files.items())),
            "validated_files": release_validation["checked_files"],
            "record_count": record_count,
            "video_root": _resolved_path(config.video_root),
        },
        "visual_input": {
            "evidence_delivery": "decoded_frames",
            "stream_fps": config.stream_fps,
            "core_stream_fps_fixed": CORE_STREAM_FPS,
            "sample_period_s": 1.0 / config.stream_fps,
            "sampler_identity": SAMPLER_IDENTITY,
            "timestamp_rule": "start + index / stream_fps; nearest source frame, half up",
            "decoder_backend": "opencv",
            "decoder_version": cv2.__version__,
            "decoder_identity": f"opencv-{cv2.__version__}",
            "color_space": "RGB",
            "dtype": "uint8",
            "resize_policy": RESIZE_POLICY,
            "max_width": config.max_width,
            "jpeg_encoding": "none",
        },
        "generation": {
            "core_temperature": config.temperature,
            "adapter_effective_settings": adapter_metadata["declared"].get("generation", {}),
        },
        "scoring": {
            "scorer_version": config.scorer_version,
            "judge_mode": config.judge_mode,
            "judge_base_url": config.judge_base_url,
            "judge_model": config.judge_model if config.judge_mode != "exact" else None,
            "judge_api_key_env": config.judge_api_key_env,
            "judge_prompt_version": "osb-vlm-judge-v1"
            if config.judge_mode != "exact"
            else None,
            "semantic_task_types": sorted(
                {str(value).strip().upper() for value in config.semantic_task_types if str(value).strip()}
            ),
            "window_boundary": "half_open",
            "score_views": [
                "strict_all_window",
                "strict_observable_window",
                "post_trigger_eventual",
            ],
            "density_views": ["crowded_window", "non_crowded_window"],
        },
        "adapter": {
            **adapter_metadata,
            "capabilities": capabilities.model_dump(mode="json"),
            "configuration": config.adapter_config,
        },
        "execution_track": {
            "pacing": config.pacing,
            "classification_source": "adapter_declared_capabilities",
            "visual_state": (
                "Native Streaming"
                if capabilities.state_lifetime == "persistent"
                else "Non-native Streaming"
            ),
            "response_triggering": capabilities.response_mode,
            "proactive_track": (
                "autonomous_primary"
                if capabilities.state_lifetime == "persistent"
                and capabilities.response_mode == "autonomous"
                and config.pacing == "wall_clock"
                else "polling_or_diagnostic_baseline"
            )
            if config.task.value == "proactive"
            else "not_applicable",
            "proactive_primary_eligible": (
                capabilities.state_lifetime == "persistent"
                and capabilities.response_mode == "autonomous"
                and config.pacing == "wall_clock"
            )
            if config.task.value == "proactive"
            else None,
            "proactive_response_track": (
                "autonomous_primary"
                if capabilities.state_lifetime == "persistent"
                and capabilities.response_mode == "autonomous"
                and config.pacing == "wall_clock"
                else "polling_baseline"
            )
            if config.task.value == "proactive"
            else None,
        },
        "run": {
            "output_dir": _resolved_path(config.output_dir),
            "resume": config.resume,
            "checkpoint_every_records": config.checkpoint_every_records,
            "synthetic": config.synthetic,
        },
        "telemetry_contract": {
            "schema": "osb-evaluation-telemetry-v2",
            "required_groups": [
                "frames_and_pixels",
                "queries_and_ttft",
                "text_tokens",
                "model_calls",
                "inference_time",
                "gpu_memory",
                "completion_and_failures",
                "qa_history_processing",
                "post_stream_response_grace",
            ],
        },
        "code_identities": _code_identities(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }
    snapshot["evaluation_profile_hash"] = stable_hash(
        {
            "protocol": snapshot["protocol"],
            "data": snapshot["data"],
            "visual_input": snapshot["visual_input"],
            "generation": {"core_temperature": config.temperature},
        }
    )
    snapshot["config_hash"] = stable_hash(snapshot)
    return snapshot
