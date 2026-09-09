"""Create a tiny synthetic video/release for the documented CLI smoke flow."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from open_stream_bench.models import ProactiveRecord, QARecord, ReleaseManifest, ResponseWindow


def create_fixture(root: Path) -> None:
    # Never overwrite a user's existing release or results.
    root.mkdir(parents=True, exist_ok=False)
    release = root / "release"
    release.mkdir()
    writer = cv2.VideoWriter(
        str(root / "video.avi"), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48)
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV MJPG encoder unavailable")
    try:
        for index in range(120):
            frame = np.zeros((48, 64, 3), dtype=np.uint8)
            frame[:] = (index, 40, 180)
            writer.write(frame)
    finally:
        writer.release()
    qa = QARecord(
        record_id="smoke:qa", source_id="synthetic", video_path="video.avi",
        question="Which option?", options=["A. event", "B. none"], answer="A",
        question_time_s=2, evidence_anchor_s=1,
    )
    proactive = ProactiveRecord(
        record_id="smoke:proactive", source_id="synthetic", video_path="video.avi",
        instruction="Report the event.", instruction_time_s=0,
        windows=[ResponseWindow(start_s=5, end_s=7.5, expected_answer="event")],
    )
    for name, value in {
        "qa.jsonl": qa.model_dump(mode="json"),
        "proactive.jsonl": proactive.model_dump(mode="json"),
        "tiny_qa_ids.json": [qa.record_id],
        "tiny_proactive_ids.json": [proactive.record_id],
    }.items():
        (release / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
    manifest = ReleaseManifest(
        release_id="synthetic-smoke", status="private_provisional",
        schema_version="osb-canonical-v0", qa_file="qa.jsonl",
        proactive_file="proactive.jsonl", tiny_qa_ids_file="tiny_qa_ids.json",
        tiny_proactive_ids_file="tiny_proactive_ids.json", counts={"qa": 1, "proactive": 1},
        files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in release.iterdir()},
    )
    (release / "manifest.json").write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(f"Synthetic fixture ready: {root}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        create_fixture(args.output)
    except FileExistsError:
        print(f"error: output directory already exists: {args.output}; choose a new directory",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
