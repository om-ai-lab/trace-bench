"""The single ``trace`` command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .adapters import load_adapter, validate_adapter
from .bundle import RunBundle
from .config import resolve_config
from .core import run
from .data import load_release, validate_release
from .models import TaskName
from .preflight import build_preflight_snapshot
from .scoring import (
    assess_official_eligibility,
    judge_from_settings,
    score_records,
    summarize_telemetry,
)


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task", choices=[task.value for task in TaskName], required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--subset", choices=["tiny", "full", "all"], default="tiny")
    parser.add_argument("--adapter", required=True, help="Adapter reference: module:object")
    parser.add_argument("--adapter-config", type=Path)
    parser.add_argument("--video-root", type=str)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--stream-fps",
        type=float,
        default=1.0,
        help="Core evidence rate; fixed at 1 FPS in the current protocol",
    )
    parser.add_argument("--qa-window-s", type=float)
    parser.add_argument(
        "--proactive-history-window-s",
        type=float,
        help="fixed legal history before the Proactive instruction (default: 5)",
    )
    parser.add_argument(
        "--proactive-window-s",
        type=float,
        choices=(5.0, 10.0),
        help="fixed point-trigger response window in seconds (5 or 10)",
    )
    parser.add_argument("--proactive-step-s", type=float)
    parser.add_argument("--max-width", type=int)
    parser.add_argument("--jpeg-quality", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--pacing", choices=["logical", "wall_clock"])
    parser.add_argument(
        "--checkpoint-every",
        "--save-every",
        dest="checkpoint_every_records",
        type=int,
        help="Durably checkpoint every N newly terminal records (default: 10)",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--synthetic", action="store_true")
    _add_judge_arguments(parser)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate and print the frozen run configuration without inference",
    )


def _add_judge_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--judge-mode",
        choices=["auto", "exact", "vlm"],
        help="proactive scoring route (default: resolved auto)",
    )
    parser.add_argument(
        "--judge-base-url",
        help="OpenAI-compatible judge base URL; prefer TRACE_VLM_JUDGE_BASE_URL",
    )
    parser.add_argument("--judge-model", help="judge model id")
    parser.add_argument(
        "--judge-api-key-env",
        help="environment variable containing the judge API key (the key is never persisted)",
    )
    parser.add_argument("--judge-timeout-s", type=float)
    parser.add_argument("--judge-temperature", type=float)
    parser.add_argument(
        "--semantic-task-type",
        dest="semantic_task_types",
        action="append",
        help="task type routed to VLM in auto mode; repeat for multiple types",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trace", description="TRACE local evaluation Core"
    )
    parser.add_argument("--debug", action="store_true", help="show full error tracebacks")
    parser.add_argument("--version", action="version", version=f"trace {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    data_parser = subparsers.add_parser("data", help="data release commands")
    data_subparsers = data_parser.add_subparsers(dest="data_command", required=True)
    data_validate = data_subparsers.add_parser("validate")
    data_validate.add_argument("--release", type=Path, required=True)

    run_parser = subparsers.add_parser("run", help="run a local evaluation")
    _add_run_arguments(run_parser)

    score_parser = subparsers.add_parser("score", help="rescore an existing bundle")
    score_parser.add_argument("bundle", type=Path)
    _add_judge_arguments(score_parser)

    bundle_parser = subparsers.add_parser("bundle", help="bundle commands")
    bundle_subparsers = bundle_parser.add_subparsers(dest="bundle_command", required=True)
    bundle_validate = bundle_subparsers.add_parser("validate")
    bundle_validate.add_argument("bundle", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _execute(args)
    except (OSError, ValueError) as exc:
        if args.debug:
            raise
        message = " ".join(str(exc).splitlines())
        print(f"trace: error: {message}", file=sys.stderr)
        return 1


def _execute(args: argparse.Namespace) -> int:
    if args.command == "data":
        _json(validate_release(args.release))
        return 0
    if args.command == "bundle":
        _json(RunBundle(args.bundle).validate())
        return 0
    if args.command == "score":
        bundle = RunBundle(args.bundle)
        bundle.validate()
        with (args.bundle / "resolved_config.json").open("r", encoding="utf-8") as handle:
            resolved = json.load(handle)
        judge_overrides = {
            "judge_mode": args.judge_mode,
            "judge_base_url": args.judge_base_url,
            "judge_model": args.judge_model,
            "judge_api_key_env": args.judge_api_key_env,
            "judge_timeout_s": args.judge_timeout_s,
            "judge_temperature": args.judge_temperature,
            "semantic_task_types": args.semantic_task_types,
        }
        resolved_for_scoring = dict(resolved)
        resolved_for_scoring.update(
            {key: value for key, value in judge_overrides.items() if value is not None}
        )
        resolved_scoring = resolved.get("scoring", {})
        historical_boundary = (
            resolved_scoring.get("window_boundary")
            if isinstance(resolved_scoring, dict)
            else None
        )
        judge = judge_from_settings(resolved_for_scoring)
        metrics = score_records(
            resolved["task"],
            bundle.records(),
            judge=judge,
            events=bundle.events(),
            proactive_window_s=resolved.get("proactive_window_s"),
            window_boundary=resolved.get("window_boundary") or historical_boundary or "half_open",
        )
        scored_records = metrics.pop("scored_records", [])
        metrics["execution_track"] = resolved.get("execution_track") or resolved.get(
            "preflight", {}
        ).get("execution_track", {})
        metrics["telemetry"] = summarize_telemetry(bundle.events(), scored_records)
        with (args.bundle / "summary.json").open("r", encoding="utf-8") as handle:
            source_summary = json.load(handle)
        metrics["official_eligibility"] = assess_official_eligibility(
            str(resolved["task"]),
            metrics,
            synthetic=bool(source_summary.get("synthetic")),
            provisional=bool(source_summary.get("provisional")),
        )
        bundle.write_rescored(
            records=scored_records,
            metrics=metrics,
            scoring=judge.metadata,
            source_bundle=str(args.bundle),
        )
        output = {
            "metrics": metrics,
            "scored_record_count": len(scored_records),
            "source_bundle": str(args.bundle),
            "scoring": judge.metadata,
            "rescored_records": str(args.bundle / "rescored_records.jsonl"),
            "rescored_metrics": str(args.bundle / "rescored_metrics.json"),
        }
        _json(output)
        return 0

    adapter_config = {}
    if args.video_root is not None and not Path(args.video_root).is_dir():
        raise ValueError(f"video root is not a directory: {args.video_root}")
    if args.adapter_config:
        with args.adapter_config.open("r", encoding="utf-8") as handle:
            adapter_config = json.load(handle)
    overrides = {
        "stream_fps": args.stream_fps,
        "qa_window_s": args.qa_window_s,
        "proactive_history_window_s": args.proactive_history_window_s,
        "proactive_window_s": args.proactive_window_s,
        "proactive_step_s": args.proactive_step_s,
        "max_width": args.max_width,
        "jpeg_quality": args.jpeg_quality,
        "temperature": args.temperature,
        "pacing": args.pacing,
        "checkpoint_every_records": args.checkpoint_every_records,
        "judge_mode": args.judge_mode,
        "judge_base_url": args.judge_base_url,
        "judge_model": args.judge_model,
        "judge_api_key_env": args.judge_api_key_env,
        "judge_timeout_s": args.judge_timeout_s,
        "judge_temperature": args.judge_temperature,
        "semantic_task_types": args.semantic_task_types,
    }
    config = resolve_config(
        release_dir=args.release,
        task=TaskName(args.task),
        subset=args.subset,
        adapter=args.adapter,
        output_dir=args.output,
        overrides=overrides,
        adapter_config=adapter_config,
        video_root=args.video_root,
        synthetic=args.synthetic,
        resume=not args.no_resume,
    )
    if args.preflight_only:
        release = load_release(args.release)
        adapter = load_adapter(config.adapter, config.adapter_config)
        capabilities = validate_adapter(adapter, config.task, config)
        _json(
            build_preflight_snapshot(
                config,
                release,
                adapter,
                capabilities,
                record_count=len(release.records(config.task.value, config.subset)),
            )
        )
        return 0
    output = run(config)
    provisional = load_release(args.release).manifest.status != "public"
    _json({"output": str(output), "synthetic": config.synthetic, "provisional": provisional})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
