"""User setup checks must catch absent assets before GPU inference."""

import subprocess
import sys
from pathlib import Path


def test_video_checker_present_and_missing(synthetic_release):
    release, root = synthetic_release
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts" / "check_videos.py"),
        "--release", str(release), "--video-root", str(root),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(command[:-1] + [str(root / "absent")], capture_output=True, text=True)
    assert result.returncode == 1
    assert "MISSING" in result.stdout
