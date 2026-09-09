from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from open_stream_bench.adapters import load_adapter, validate_adapter
from open_stream_bench.config import resolve_config
from open_stream_bench.data import load_release
from open_stream_bench.models import TaskName
from open_stream_bench.preflight import build_preflight_snapshot


def _snapshot(synthetic_release):
    release_dir, video_root = synthetic_release
    config = resolve_config(
        release_dir=release_dir,
        task=TaskName.QA,
        subset="tiny",
        adapter="open_stream_bench.adapters:TestDoubleAdapter",
        output_dir=video_root / "run",
        video_root=str(video_root),
        overrides={"stream_fps": 1.0, "max_width": 32},
        synthetic=True,
    )
    release = load_release(release_dir)
    adapter = load_adapter(config.adapter, config.adapter_config)
    capabilities = validate_adapter(adapter, config.task, config)
    return config, build_preflight_snapshot(
        config, release, adapter, capabilities, record_count=1
    )


def test_preflight_freezes_protocol_data_visual_and_adapter_identity(synthetic_release):
    _, snapshot = _snapshot(synthetic_release)
    assert snapshot["software_version"] == "0.1.0"
    assert snapshot["protocol"]["identity"] == "osb-incremental-decoded-rgb-v4"
    assert snapshot["protocol"]["contract"] == "osb-contract-v4"
    assert snapshot["protocol"]["core_delivery_chunk_frames"] == 1
    assert snapshot["data"]["release_id"] == "synthetic-v0.0.0"
    assert len(snapshot["data"]["release_manifest_sha256"]) == 64
    assert snapshot["visual_input"]["stream_fps"] == 1.0
    assert snapshot["visual_input"]["max_width"] == 32
    assert snapshot["visual_input"]["decoder_identity"].startswith("opencv-")
    assert snapshot["adapter"]["declared"]["model"]["identity"] == "synthetic-oracle"
    assert len(snapshot["adapter"]["implementation_sha256"]) == 64
    assert len(snapshot["evaluation_profile_hash"]) == 64
    assert len(snapshot["config_hash"]) == 64
    assert snapshot["protocol"]["qa_user_content_policy"] == "byte_identical_core_prompt"
    assert snapshot["telemetry_contract"]["schema"] == "osb-evaluation-telemetry-v2"
    assert snapshot["scoring"]["scorer_version"] == "osb-scoring-v6"
    assert len(snapshot["code_identities"]["core"]["sha256"]) == 64
    assert snapshot["execution_track"]["proactive_track"] == "not_applicable"


def test_preflight_hash_changes_when_core_input_changes(synthetic_release):
    config, first = _snapshot(synthetic_release)
    changed = config.model_copy(update={"stream_fps": 1.0, "max_width": 64})
    release = load_release(Path(changed.release_dir))
    adapter = load_adapter(changed.adapter, changed.adapter_config)
    capabilities = validate_adapter(adapter, changed.task, changed)
    second = build_preflight_snapshot(changed, release, adapter, capabilities, record_count=1)
    assert first["config_hash"] != second["config_hash"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("stream_fps", 0), ("stream_fps", 2), ("max_width", 0), ("jpeg_quality", 101), ("temperature", -0.1)],
)
def test_invalid_core_configuration_is_rejected(synthetic_release, field, value):
    release_dir, video_root = synthetic_release
    with pytest.raises(ValidationError):
        resolve_config(
            release_dir=release_dir,
            task=TaskName.QA,
            subset="tiny",
            adapter="open_stream_bench.adapters:TestDoubleAdapter",
            output_dir=video_root / "run",
            overrides={field: value},
        )


def test_preflight_rejects_missing_video_root(synthetic_release):
    config, _ = _snapshot(synthetic_release)
    changed = config.model_copy(update={"video_root": "/definitely/missing/osb-videos"})
    release = load_release(Path(changed.release_dir))
    adapter = load_adapter(changed.adapter, changed.adapter_config)
    capabilities = validate_adapter(adapter, changed.task, changed)
    with pytest.raises(ValueError, match="video_root must be an existing directory"):
        build_preflight_snapshot(changed, release, adapter, capabilities, record_count=1)
