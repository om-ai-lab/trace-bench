from open_stream_bench.cli import build_parser, main


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
        "open_stream_bench.adapters:TestDoubleAdapter",
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
        "--adapter", "open_stream_bench.adapters:TestDoubleAdapter",
        "--video-root", str(video_root),
        "--output", str(output),
        "--preflight-only",
        "--synthetic",
    ]) == 0
    assert '"preflight_schema": "osb-preflight-v4"' in capsys.readouterr().out
    assert not output.exists()
