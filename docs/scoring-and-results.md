# Scoring and resume

English | [简体中文](scoring-and-results.zh-CN.md)

Run inference before validating or scoring a bundle. Generating annotations
alone does not create results. Use preflight to inspect configuration; it does
not perform inference.

## Judge and rescoring

The default score preserves the legacy strict parser and contract. To produce
the current report-facing derived sidecar, pass `--scoring-profile paper-v1`:

```bash
trace score output/livecc-qa --scoring-profile paper-v1
```

This selects Recoverable QA parsing and emits explicit Proactive
`false_alarm_rate`, `miss_rate`, delay medians and delay coverage when the bundle
contains the required evidence. It never edits `records.jsonl`, `events.jsonl`
or the finalized bundle. The profile is part of the derived scoring metadata.

QA uses single-label choice scoring. Proactive uses exact matching or a
user-configured OpenAI-compatible semantic judge. After generating the example
bundle, replace endpoint/model/key values and run:

```bash
trace bundle validate output/livecc-proactive
export TRACE_VLM_JUDGE_BASE_URL=http://127.0.0.1:30099/v1
export TRACE_VLM_JUDGE_MODEL=your-served-judge-model
export TRACE_VLM_JUDGE_API_KEY=your-key
trace score output/livecc-proactive --judge-mode auto \
  --judge-base-url "$TRACE_VLM_JUDGE_BASE_URL" --judge-model "$TRACE_VLM_JUDGE_MODEL"
```

`auto` routes SSR/CRR to the configured judge and other types to exact matching.
`vlm` judges every Proactive type; `exact` needs no service.
The judge receives question, reference and prediction text, not video frames.
Keys are read from the named environment variable and are not persisted.
Missing judge configuration or judge failures produce diagnostic/incomplete scores.

Explicit model/URL flags override settings frozen in an existing bundle.
Keep judge model, prompt, routing and window settings consistent when comparing.
Rescoring writes `rescored_records.jsonl` and `rescored_metrics.json`, without
editing `records.jsonl` or `events.jsonl`. Archive derived sidecars before another
rescore if you need to retain several judge versions.

## Outputs and resume

`records.jsonl` stores predictions/status; `events.jsonl` stores raw events
and telemetry. Manifest/config/integrity files identify the run.
`metrics.json` and `summary.json` contain original aggregates.

Checkpointing defaults to 10 records; `--checkpoint-every 5` is supported.
Repeat the same command/output to resume interrupted inference.
Committed successes and failures are skipped; incomplete records rerun.
Finalized runs cannot resume or overwrite. Changed settings require a new output.

Structural validity is separate from official eligibility.
Inspect failures, judge coverage and telemetry as well as scores.
Missing measurements are not zero. QA history costs are separate from query TTFT.
See the [protocol](evaluation-protocol.md) for populations and track definitions.

## Troubleshooting

- Missing videos: run the video checker and inspect root/archive nesting.
- Missing bundle files: run `trace run` before `bundle validate` and `score`.
- Adapter import: install its package in the model environment.
- Pacing mismatch: match Core pacing to adapter capability/config.
- CUDA initialization: fix the runtime before resume; it is not model error rate.
- Changed configuration: retain the old bundle and choose a new output.
- Unexpected failure: use `trace --debug ...` to show the traceback.
