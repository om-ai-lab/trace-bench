from __future__ import annotations

import json

import pytest

from open_stream_bench.bundle import RunBundle


def test_checkpoint_commits_terminal_records_and_events_atomically(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen"}
    bundle.prepare(resolved)
    checkpoint = bundle.checkpoint(
        resolved_config=resolved,
        records=[{"record_id": "qa:1", "status": "failed"}],
        events=[{"record_id": "qa:1", "kind": "failure"}],
    )

    assert (checkpoint / "commit.json").is_file()
    records, events = bundle.resume_state(expected_config_hash="frozen")
    assert [record["record_id"] for record in records] == ["qa:1"]
    assert [event["record_id"] for event in events] == ["qa:1"]
    manifest = json.loads((bundle.root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["finalized"] is False
    with pytest.raises(ValueError, match="not finalized"):
        bundle.validate()


def test_resume_ignores_uncommitted_newer_checkpoint(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen"}
    bundle.prepare(resolved)
    bundle.checkpoint(
        resolved_config=resolved,
        records=[{"record_id": "qa:1", "status": "completed"}],
        events=[],
    )
    incomplete = bundle.checkpoints_root / "00000002"
    incomplete.mkdir()
    (incomplete / "records.jsonl").write_text(
        '{"record_id":"qa:2","status":"completed"}\n', encoding="utf-8"
    )

    records, _ = bundle.resume_state(expected_config_hash="frozen")
    assert [record["record_id"] for record in records] == ["qa:1"]


def test_resume_rejects_corrupt_committed_checkpoint(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen"}
    bundle.prepare(resolved)
    checkpoint = bundle.checkpoint(
        resolved_config=resolved,
        records=[{"record_id": "qa:1", "status": "completed"}],
        events=[],
    )
    (checkpoint / "records.jsonl").write_text(
        '{"record_id":"qa:tampered","status":"completed"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="checkpoint integrity mismatch"):
        bundle.resume_state(expected_config_hash="frozen")


def test_checkpoint_rejects_orphan_events_and_config_drift(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen"}
    bundle.prepare(resolved)
    with pytest.raises(ValueError, match="does not belong"):
        bundle.checkpoint(
            resolved_config=resolved,
            records=[{"record_id": "qa:1", "status": "completed"}],
            events=[{"record_id": "qa:2", "kind": "answer"}],
        )
    bundle.checkpoint(
        resolved_config=resolved,
        records=[{"record_id": "qa:1", "status": "completed"}],
        events=[],
    )
    with pytest.raises(ValueError, match="config identity"):
        bundle.resume_state(expected_config_hash="changed")


def test_finalized_bundle_is_immutable(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen"}
    bundle.prepare(resolved)
    bundle.write(
        resolved_config=resolved,
        records=[{"record_id": "qa:1", "status": "completed"}],
        events=[],
        metrics={},
        synthetic=True,
    )
    with pytest.raises(ValueError, match="immutable"):
        bundle.checkpoint(resolved_config=resolved, records=[], events=[])


def test_rescoring_sidecars_do_not_mutate_finalized_bundle(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen", "task": "proactive"}
    bundle.prepare(resolved)
    bundle.write(
        resolved_config=resolved,
        records=[{"record_id": "p:1", "status": "completed"}],
        events=[],
        metrics={"window_accuracy": 0.0},
        synthetic=False,
    )
    integrity_before = (bundle.root / "integrity.json").read_text(encoding="utf-8")
    bundle.write_rescored(
        records=[{"record_id": "p:1", "per_window_results": [{"score": 0.75}]}],
        metrics={"window_accuracy": 0.75},
        scoring={"judge_model": "test"},
    )
    assert (bundle.root / "rescored_records.jsonl").is_file()
    assert (bundle.root / "rescored_metrics.json").is_file()
    assert (bundle.root / "integrity.json").read_text(encoding="utf-8") == integrity_before
    assert bundle.validate()["valid"] is True


def test_prepare_preserves_latest_committed_checkpoint_marker(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen"}
    bundle.prepare(resolved)
    bundle.checkpoint(
        resolved_config=resolved,
        records=[{"record_id": "qa:1", "status": "completed"}],
        events=[],
    )
    bundle.prepare(resolved)
    manifest = json.loads((bundle.root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["latest_checkpoint"] == 1


def test_bundle_validation_reports_eligibility_separately_from_integrity(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen"}
    bundle.prepare(resolved)
    bundle.write(
        resolved_config=resolved,
        records=[{"record_id": "qa:1", "status": "completed"}],
        events=[],
        metrics={},
        synthetic=False,
        provisional=False,
        official_eligibility={
            "official_eligible": False,
            "reasons": ["incomplete_telemetry:query_ttft"],
            "policy": "osb-official-eligibility-v1",
        },
    )
    result = bundle.validate()
    assert result["valid"] is True
    assert result["official_eligible"] is False


def test_bundle_validation_rejects_embedded_sidecar_event_drift(tmp_path):
    bundle = RunBundle(tmp_path / "run")
    resolved = {"config_hash": "frozen"}
    bundle.prepare(resolved)
    bundle.write(
        resolved_config=resolved,
        records=[
            {
                "record_id": "p:1",
                "status": "completed",
                "events": [{"kind": "answer", "logical_time_s": 1.0, "text": "A"}],
            }
        ],
        events=[
            {
                "record_id": "p:1",
                "kind": "answer",
                "logical_time_s": 1.0,
                "text": "B",
            }
        ],
        metrics={},
        synthetic=False,
    )
    with pytest.raises(ValueError, match="embedded events disagree"):
        bundle.validate()
