"""Exercise the documented fixture and reject the original false-positive flow."""

from pathlib import Path
import runpy

import pytest

from open_stream_bench.cli import main


@pytest.mark.parametrize("step", [1, 5])
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
            "--judge-mode", "exact", "--proactive-step-s", str(step),
            "--checkpoint-every", "5",
        ]) == 0
        assert main(["bundle", "validate", str(bundle)]) == 0
        assert main(["score", str(bundle), "--judge-mode", "exact"]) == 0
    if step == 1:
        check(root)
    else:
        with pytest.raises(ValueError, match="window_accuracy"):
            check(root)
