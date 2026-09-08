# Running, resuming and scoring

Run preflight before inference, then remove `--preflight-only` and use the same
arguments. Use `--checkpoint-every 5` or `10`. To resume an interrupted run,
repeat the same command and output directory: committed terminal records are
skipped, including recorded failures. Incomplete records run again. Changing
inference settings requires a new directory. Finalized raw bundles are immutable.

```bash
osb bundle validate /path/to/results/my-run
osb score /path/to/results/my-run
```

`records.jsonl` preserves predictions and record status; `events.jsonl` preserves
raw model events and telemetry. `manifest.json`, `resolved_config.json`, and
`integrity.json` identify and validate the run. `metrics.json` and `summary.json`
are original aggregates. Rescoring writes `rescored_records.jsonl` and
`rescored_metrics.json` without modifying raw inference. Copy derived sidecars
to a separately named archive before another rescore if retaining both versions.

QA uses the frozen single-label parser. Proactive supports exact matching and a
user-operated semantic judge. Configure `OSB_VLM_JUDGE_BASE_URL`,
`OSB_VLM_JUDGE_MODEL`, and `OSB_VLM_JUDGE_API_KEY` in the environment and run
`osb score /path/to/results/my-run --judge-mode auto`. Auto routes SSR and CRR
to the judge when configured; exact fallback is diagnostic. `--judge-mode vlm`
requests semantic judging for all Proactive task types. Freeze the judge route,
model, prompt and window when comparing models; raw text alone does not measure
judge correctness. See the [protocol](evaluation-protocol.md) for score populations.

`official_eligible` is distinct from structural validity. Missing required
telemetry, judge failures, or mismatched tracks can leave a valid bundle
diagnostic. Missing measurements are not zero. QA prefix costs count separately
from query TTFT. Native/non-native visual state and autonomous/polling Proactive
triggering are independent comparison axes.

## Common problems

- Missing videos: run `scripts/check_videos.py`; check root and archive nesting.
- Adapter import fails: install the adapter package in the same Python environment.
- Pacing mismatch: match `--pacing` to the adapter's declared capability.
- CUDA initialization failure: fix the model environment before resuming; do not
  interpret initialization failure as a model accuracy result.
- Semantic fallback: configure the judge and rescore; inference need not repeat.
- Old configuration on resume: use the original configuration or a new output path.
