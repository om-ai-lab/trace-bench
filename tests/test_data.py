import json
from pathlib import Path

import pytest

from trace_bench.data import load_release, validate_release
from trace_bench.models import ProactiveRecord, QARecord, ReleaseManifest


def test_public_v1_1_release_is_valid():
    root = Path(__file__).parents[1] / "data/releases/v1.1.0"
    result = validate_release(root)
    assert result["release_id"] == "v1.1.0"
    assert result["qa_count"] == 833
    assert result["proactive_count"] == 415
    release = load_release(root)
    assert len(release.records("qa", "tiny")) == 9
    assert len(release.records("proactive", "tiny")) == 9


def test_release_rejects_duplicate_record_ids(tmp_path):
    qa = QARecord(
        record_id="duplicate",
        source_id="source",
        video_path="video.mp4",
        question="Q",
        answer="A",
        question_time_s=1.0,
        evidence_anchor_s=0.0,
    ).model_dump(mode="json")
    proactive = ProactiveRecord(
        record_id="proactive",
        source_id="source",
        video_path="video.mp4",
        instruction="Q",
        instruction_time_s=0.0,
        deadline_s=1.0,
    ).model_dump(mode="json")
    (tmp_path / "qa.jsonl").write_text(json.dumps(qa) + "\n" + json.dumps(qa) + "\n", encoding="utf-8")
    (tmp_path / "proactive.jsonl").write_text(json.dumps(proactive) + "\n", encoding="utf-8")
    (tmp_path / "tiny_qa_ids.json").write_text('["duplicate"]\n', encoding="utf-8")
    (tmp_path / "tiny_proactive_ids.json").write_text('["proactive"]\n', encoding="utf-8")
    manifest = ReleaseManifest(
        release_id="duplicate-test",
        status="private_provisional",
        schema_version="osb-canonical-v0",
        qa_file="qa.jsonl",
        proactive_file="proactive.jsonl",
        tiny_qa_ids_file="tiny_qa_ids.json",
        tiny_proactive_ids_file="tiny_proactive_ids.json",
        counts={"qa": 2, "proactive": 1},
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json")), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate qa record_id"):
        load_release(tmp_path)
