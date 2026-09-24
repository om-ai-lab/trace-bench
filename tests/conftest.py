from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest

from trace_bench.models import ProactiveRecord, QARecord, ReleaseManifest, ResponseWindow


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_jsonl(path: Path, records: list[object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            value = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
            handle.write(json.dumps(value, sort_keys=True) + "\n")


@pytest.fixture
def synthetic_release(tmp_path: Path) -> tuple[Path, Path]:
    video_path = tmp_path / "video.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG writer unavailable")
    for index in range(40):
        frame = __import__("numpy").zeros((48, 64, 3), dtype="uint8")
        frame[:, :, 0] = index
        frame[:, :, 1] = 40
        frame[:, :, 2] = 180
        writer.write(frame)
    writer.release()

    release = tmp_path / "release"
    release.mkdir()
    qa = QARecord(
        record_id="qa:1",
        source_id="synthetic:qa:1",
        video_path=video_path.name,
        question="Which option?",
        options=["A", "B"],
        answer="A",
        question_time_s=2.0,
        evidence_anchor_s=1.0,
    )
    proactive = ProactiveRecord(
        record_id="proactive:1",
        source_id="synthetic:proactive:1",
        video_path=video_path.name,
        instruction="Watch the event.",
        instruction_time_s=0.0,
        deadline_s=3.0,
        windows=[ResponseWindow(start_s=1.0, end_s=2.5, expected_answer="event")],
    )
    _write_jsonl(release / "qa.jsonl", [qa])
    _write_jsonl(release / "proactive.jsonl", [proactive])
    (release / "tiny_qa_ids.json").write_text('["qa:1"]\n', encoding="utf-8")
    (release / "tiny_proactive_ids.json").write_text('["proactive:1"]\n', encoding="utf-8")
    manifest = ReleaseManifest(
        release_id="synthetic-v0.0.0",
        status="private_provisional",
        schema_version="osb-canonical-v0",
        qa_file="qa.jsonl",
        proactive_file="proactive.jsonl",
        tiny_qa_ids_file="tiny_qa_ids.json",
        tiny_proactive_ids_file="tiny_proactive_ids.json",
        counts={"qa": 1, "proactive": 1},
        files={name: _sha256(release / name) for name in ["qa.jsonl", "proactive.jsonl", "tiny_qa_ids.json", "tiny_proactive_ids.json"]},
    )
    (release / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return release, tmp_path
