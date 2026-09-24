import pytest

from trace_bench.cli import build_parser, main


def test_cli_exposes_core_commands():
    parser = build_parser()
    assert parser.parse_args(["data", "validate", "--release", "data/releases/v1.1.0"]).command == "data"
    assert parser.parse_args(["bundle", "validate", "runs/example"]).command == "bundle"
    run_args = parser.parse_args([
        "run", "--task", "qa", "--release", "data/releases/v1.1.0",
        "--adapter", "example:adapter", "--output", "runs/example",
        "--checkpoint-every", "5", "--no-resume",
    ])
    assert run_args.checkpoint_every_records == 5
    assert run_args.no_resume is True
    paper_args = parser.parse_args([
        "run", "--task", "proactive", "--release", "data/releases/v1.1.0",
        "--subset", "standard", "--adapter", "example:adapter",
        "--output", "runs/paper", "--scoring-profile", "paper-v1",
    ])
    assert paper_args.subset == "standard"
    assert paper_args.scoring_profile == "paper-v1"


def test_cli_runs_synthetic_vertical_slice(synthetic_release, capsys):
    release, video_root = synthetic_release
    output = video_root / "cli-run"
    assert main([
        "run",
        "--task",
        "qa",
        "--release",
        str(release),
        "--subset",
        "tiny",
        "--adapter",
        "trace_bench.adapters:TestDoubleAdapter",
        "--video-root",
        str(video_root),
        "--output",
        str(output),
        "--synthetic",
    ]) == 0
    assert '"synthetic": true' in capsys.readouterr().out
    assert main(["bundle", "validate", str(output)]) == 0
    capsys.readouterr()
    assert main(["score", str(output)]) == 0
    assert (output / "rescored_metrics.json").is_file()


def test_cli_preflight_only_does_not_run_inference(synthetic_release, capsys):
    release, video_root = synthetic_release
    output = video_root / "preflight-only"
    assert main([
        "run",
        "--task", "qa",
        "--release", str(release),
        "--adapter", "trace_bench.adapters:TestDoubleAdapter",
        "--video-root", str(video_root),
        "--output", str(output),
        "--preflight-only",
        "--synthetic",
    ]) == 0
    assert '"preflight_schema": "osb-preflight-v4"' in capsys.readouterr().out
    assert not output.exists()


def test_cli_reports_missing_release_without_traceback(tmp_path, capsys):
    assert main(["data", "validate", "--release", str(tmp_path / "missing")]) == 1
    output = capsys.readouterr()
    assert "release manifest does not exist" in output.err
    assert "Traceback" not in output.err
    with pytest.raises(FileNotFoundError):
        main(["--debug", "data", "validate", "--release", str(tmp_path / "missing")])


def test_cli_missing_video_root_fails_before_output(synthetic_release, capsys):
    release, root = synthetic_release
    output = root / "must-not-exist"
    assert main([
        "run", "--task", "qa", "--release", str(release),
        "--adapter", "nonexistent:Adapter", "--video-root", str(root / "missing"),
        "--output", str(output),
    ]) == 1
    assert "video root is not a directory" in capsys.readouterr().err
    assert not output.exists()


def test_cli_does_not_hide_unexpected_errors(monkeypatch):
    def broken(*args):
        raise RuntimeError("unexpected bug")
    monkeypatch.setattr("trace_bench.cli.validate_release", broken)
    with pytest.raises(RuntimeError, match="unexpected bug"):
        main(["data", "validate", "--release", "unused"])
