# Open Stream Bench

English | [简体中文](README.zh-CN.md)

A local evaluation Core for timestamped video QA and Proactive Response.
Users download source videos, run their own models through adapters, and keep
raw outputs, timing, failures and scores in JSON/JSONL Run Bundles.
There is no hosted evaluator. Real model evaluation normally requires a GPU.

| Component | Version / scope |
| --- | --- |
| Public annotation snapshot | `data/releases/v1.1.0` |
| Data population | 833 QA, 415 Proactive records; 1,338 Proactive windows |
| Tiny setup subset | 9 QA + 9 Proactive records |
| Core package | `0.0.0` (independent of data version) |
| Protocol / scorer | `osb-contract-v4` / `osb-scoring-v6` |
| Software / data terms | [MIT](LICENSE) / [DATA_TERMS](DATA_TERMS.md) |

Only v1.1.0 annotations are shipped. Ignored historical local data is preserved.
Source videos and weights are not redistributed. Upstream annotation permission
confirmations remain pending; see [data terms](DATA_TERMS.md) and the
[dataset card](docs/dataset-card.md) for the publication boundary and review limitations.

## Install

Use Python 3.10–3.12. Download or clone this repository and enter its root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
osb --help
osb data validate --release data/releases/v1.1.0
```

This release supports source-checkout installation. An installed wheel alone
does not supply the annotation directory, videos, or model dependencies.

## Run the software end to end

This smoke flow creates a small video and synthetic annotations, decodes frames
with OpenCV, runs both tasks, validates bundles and rescores. It requires no GPU,
source download, model weights or judge endpoint. The test double deliberately
reads GT: its scores are synthetic and never model results. Use a new output
directory each time.

```bash
python scripts/make_smoke_fixture.py --output /tmp/osb-smoke
osb data validate --release /tmp/osb-smoke/release
for task in qa proactive; do
  osb run --task "$task" --release /tmp/osb-smoke/release --subset tiny \
    --adapter open_stream_bench.adapters:TestDoubleAdapter \
    --video-root /tmp/osb-smoke --output "/tmp/osb-smoke/$task" \
    --synthetic --judge-mode exact --checkpoint-every 5
  osb bundle validate "/tmp/osb-smoke/$task"
  osb score "/tmp/osb-smoke/$task" --judge-mode exact
done
```

Each output contains `records.jsonl`, `events.jsonl`, `metrics.json`, `summary.json`,
`resolved_config.json`, `manifest.json` and `integrity.json`; scoring adds
`rescored_records.jsonl` and `rescored_metrics.json`. Check the summary's
`synthetic: true` and eligibility report's `official_eligible: false`.
Bundle validation proves integrity, not model quality.

## Prepare real videos

Follow [data setup](docs/data-setup.md) using
[StreamingBench](https://streamingbench.github.io/) and
[OVO-Bench](https://github.com/joeleelyf/ovo-bench). Keep the shipped OSB annotations.
The video root must expose `videos/` and `src_videos/` matching each record's
relative `video_path`. OVO requires original source videos, not timestamp-reset
chunks. StreamingBench and the similarly named StreamBench are different projects.

```bash
python scripts/check_videos.py --release data/releases/v1.1.0 \
  --video-root /path/to/osb-media --subset tiny
```

Replace `/path/to/...` with your paths. This command checks presence; inference
checks actual decoding. Fix missing media before loading weights.
Use `--subset full` to check the complete release.

## Run a real model

Start with [LiveCC](docs/livecc-adapter.md) for upstream dependencies, weights
and environment variables. Run OSB in that model's environment; the software-only
virtual environment above does not include PyTorch or the model runtime.

After setup, from the OSB checkout, inspect QA without loading weights:

```bash
osb run --task qa --release data/releases/v1.1.0 --subset tiny \
  --adapter open_stream_bench.livecc_adapter:LiveCCAdapter \
  --adapter-config examples/livecc/logical.json --pacing logical \
  --video-root /path/to/osb-media --output /path/to/results/livecc-qa \
  --judge-mode exact --checkpoint-every 5 --preflight-only
```

Then run real QA and Proactive inference:

```bash
for task in qa proactive; do
  osb run --task "$task" --release data/releases/v1.1.0 --subset tiny \
    --adapter open_stream_bench.livecc_adapter:LiveCCAdapter \
    --adapter-config examples/livecc/logical.json --pacing logical \
    --video-root /path/to/osb-media --output "/path/to/results/livecc-$task" \
    --judge-mode exact --checkpoint-every 5 --proactive-window-s 5
  osb bundle validate "/path/to/results/livecc-$task"
  osb score "/path/to/results/livecc-$task" --judge-mode exact
done
```

Inspect failures, predictions and raw events as well as completion counts:
a finalized bundle may contain failures. Logical pacing and exact judging are
setup diagnostics. For streaming timing use `examples/livecc/wall_clock.json`
**and** `--pacing wall_clock`, a new output directory and a semantic judge.
Change to `--subset full` only after tiny succeeds. Full Proactive includes the
sampling-stress records; it does not automatically select the standard report cohort.

External adapters use `--adapter module:Class --adapter-config file.json`.
See the [adapter guide](docs/adapter-guide.md) and [example status](examples/README.md).
Capability labels are adapter declarations, not proof of model-state reuse.
Native/non-native and autonomous/polling describe independent execution properties.

## Scoring and resume

QA uses the shared user prompt and normalized single-label scoring. Ordinary
sentences and option-plus-answer prose are not parsed as choices. Raw text stays
unchanged. Proactive reports strict all-window, strict observable-window and
post-trigger eventual scores, intrusion/redundancy and coverage.

Configure your own OpenAI-compatible semantic judge:

```bash
export OSB_VLM_JUDGE_BASE_URL=http://127.0.0.1:30099/v1
export OSB_VLM_JUDGE_MODEL=your-served-judge-model
export OSB_VLM_JUDGE_API_KEY=your-key
osb score /path/to/results/livecc-proactive --judge-mode auto \
  --judge-base-url "$OSB_VLM_JUDGE_BASE_URL" --judge-model "$OSB_VLM_JUDGE_MODEL"
```

`auto` routes SSR/CRR to the semantic judge and other types to normalized exact
matching; `vlm` routes every Proactive type to the judge. The current judge
receives textual question/reference/prediction, not video frames. Missing judge
configuration or failed calls produce diagnostic/incomplete semantic results.
Judge calls send those fields to your configured endpoint; keys are not saved.

Rescoring writes derived sidecars without changing raw records/events. Resume is
enabled by default: repeat the **same run command** after interruption. Completed
and failed committed records are skipped; unfinished records run again. The
default checkpoint interval is 10 (`--checkpoint-every 5` is supported).
Finalized bundles cannot resume or overwrite; use a new output directory after
changing model, prompt, data or execution settings.

## Protocol and reports

Core delivers timestamped RGB uint8 arrays at 1 FPS using OpenCV. QA sees only
the legal prefix. Exact QA user content is shared; native system prompts and
mechanical role/control serialization are allowed. History processing costs
are retained separately from query response metrics.

Proactive point windows are half-open, use 5s or 10s tolerance and stop at the
next trigger when earlier; SSR uses state intervals. Evidence stops at the last
strict-window end, clamped to metadata video duration. Source end may leave
remaining scoring time without new frames; bounded shutdown drain only completes
already eligible responses. Core never scans an entire video to find its end.
The eventual view ends at the next trigger or final strict-window end.
Pre-instruction history stays 5s regardless of response tolerance.

Reports include quality, latency, frame workload, tokens, calls, GPU memory,
failures and telemetry coverage. Unobservable values remain missing. Automated
`official_eligible` checks do not replace adapter conformance review.
See [protocol](docs/evaluation-protocol.md),
[scoring and troubleshooting](docs/scoring-and-results.md),
[dataset card](docs/dataset-card.md), [release policy](docs/releasing.md),
[third-party notices](THIRD_PARTY_NOTICES.md), [contributing](CONTRIBUTING.md)
and [citation](CITATION.cff).

## Development

```bash
python -m pytest -q
ruff check .
python -m build
```

CI runs CPU software checks; GPU model runs are separate release checks.
`master` follows the latest annotation snapshot; version branches preserve
released snapshots. See [release validation](docs/release-validation.md) for
the checked scope and remaining publication gates.
