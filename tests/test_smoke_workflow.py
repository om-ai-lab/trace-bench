"""Exercise the documented fixture and reject the original false-positive flow."""

from pathlib import Path
import runpy
import subprocess
import sys

import cv2

import pytest

from open_stream_bench.cli import main


@pytest.mark.parametrize("step", [None, 20])
def test_documented_smoke_checks_answer_path(tmp_path, step):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    create = runpy.run_path(str(scripts / "make_smoke_fixture.py"))["create_fixture"]
    check = runpy.run_path(str(scripts / "check_smoke_results.py"))["check"]
    root = tmp_path / "smoke"
    create(root)
    for task in ("qa", "proactive"):
        bundle = root / task
        assert main([
            "run", "--task", task, "--release", str(root / "release"),
            "--adapter", "open_stream_bench.adapters:TestDoubleAdapter",
            "--video-root", str(root), "--output", str(bundle), "--synthetic",
            "--judge-mode", "exact",
            "--checkpoint-every", "5",
        ] + ([] if step is None else ["--proactive-step-s", str(step)])) == 0
        assert main(["bundle", "validate", str(bundle)]) == 0
        assert main(["score", str(bundle), "--judge-mode", "exact"]) == 0
    if step is None:
        check(root)
    else:
        with pytest.raises(ValueError, match="window_accuracy"):
            check(root)


def test_fixture_duration_and_repeat_preserve_existing_files(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/make_smoke_fixture.py"
    root = tmp_path / "fixture"
    command = [sys.executable, str(script), "--output", str(root)]
    subprocess.run(command, check=True, capture_output=True)
    video = cv2.VideoCapture(str(root / "video.avi"))
    try:
        assert video.get(cv2.CAP_PROP_FRAME_COUNT) / video.get(cv2.CAP_PROP_FPS) >= 12
    finally:
        video.release()
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    repeated = subprocess.run(command, capture_output=True, text=True)
    assert repeated.returncode == 1
    assert "choose a new directory" in repeated.stderr
    assert "Traceback" not in repeated.stderr
    assert len(repeated.stderr.splitlines()) == 1
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
