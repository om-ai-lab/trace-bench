# Open Stream Bench

Open Stream Bench is a local evaluation Core for timestamped video QA and
Proactive Response models.

The runnable Core is package version `v0.0.0`. The canonical public data
release is `v1.1.0` under `data/releases/v1.1.0`. Earlier development snapshots
are not part of the public repository.

## Current Scope

- visual timestamped QA;
- visual Proactive Response;
- local Python Core and CLI;
- user-provided model adapters;
- deterministic OpenCV frame sampling;
- JSON/JSONL data and Run Bundles.

The normative QA and Proactive Response prompt, adapter, scoring, telemetry,
and resume contract is documented in
[`docs/evaluation-protocol.md`](docs/evaluation-protocol.md).

Code is released under the [MIT License](LICENSE). Data use is governed by
[`DATA_TERMS.md`](DATA_TERMS.md) and the licenses of the upstream benchmarks and
source videos.

The Core is not an online service. Users provide local videos and run models in
their own environment. Source videos are not redistributed by this repository.
The current protocol fixes Core evidence delivery at 1 FPS and sends the same
Core-selected RGB NumPy frames to every adapter. An adapter may buffer or
combine those observations and choose its own model-call cadence. Logical
pacing is for correctness diagnostics; ranked streaming timing uses wall-clock
pacing. Proactive point-trigger scoring uses a frozen 5s or 10s half-open
window and reports dense windows explicitly. Core sends evidence only through
the last strict window (or the metadata-derived source-video end if it comes
first) and never decodes the full source merely to discover its duration. An
autonomous wall-clock session receives only the remaining final-window time when
the source ends first, without additional frames or polling. The eventual score
uses the next trigger or the final strict-window end and has no global deadline.
The Proactive pre-instruction history is independently frozen at 5 seconds, so
choosing a 10-second response tolerance does not give the model extra evidence.

## Install

Use Python 3.10–3.12. Clone this repository, enter its directory, then run:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

This first release supports a source checkout; videos and model dependencies
are installed separately. Real tiny/full inference normally needs a GPU.
Start with [data setup](docs/data-setup.md), then a
[runnable model example](examples/README.md). To test just the software:
`python -m pytest -q tests/test_cli.py tests/test_core.py`.

## Documentation

- [Data downloads and path mapping](docs/data-setup.md)
- [Dataset card and review limitations](docs/dataset-card.md)
- [Adapter tutorial and sample selection](docs/adapter-guide.md)
- [Model example configurations](examples/README.md)
- [Scoring, resume, result files and troubleshooting](docs/scoring-and-results.md)
- [Evaluation protocol](docs/evaluation-protocol.md)
- [Versions and release workflow](docs/releasing.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md) and [contributing](CONTRIBUTING.md)
- [Software citation](CITATION.cff); include the data release and protocol in reports

## Obtain Data And Videos

The repository ships the canonical OSB annotation release in
`data/releases/v1.1.0`. Original source datasets and source videos are not
redistributed here. Obtain them from the upstream links in
[`DATA_TERMS.md`](DATA_TERMS.md), then map their local paths with
`--video-root`.

```bash
osb data validate --release data/releases/v1.1.0
```

The release manifest records provenance, hashes, counts, and known limitations.

## Run With An Adapter

An adapter is a Python object referenced as `module:object`. The Core owns the
record, timing, evidence boundary, and scoring flow. The adapter owns model
preprocessing, transport, and provider response parsing.

```bash
osb run \
  --task qa \
  --release data/releases/v1.1.0 \
  --subset tiny \
  --adapter your_adapter:adapter \
  --video-root /path/to/video/roots \
  --output runs/my-qa
```

For Proactive Response, freeze the point-trigger tolerance explicitly:

```bash
osb run --task proactive --release data/releases/v1.1.0 --subset tiny \
  --adapter your_adapter:adapter --video-root /path/to/videos \
  --proactive-window-s 5 --output runs/my-proactive
```

The packaged default preset is `src/open_stream_bench/presets/current.json`.
CLI overrides are recorded in
the resolved Run Bundle. The current v1.1 tiny files contain 9 QA records and 9
Proactive Response records.

## Validate And Rescore

```bash
osb bundle validate runs/my-qa
osb score runs/my-qa
```

Proactive `SSR` and `CRR` windows use a semantic judge in `auto` mode when a
user-operated OpenAI-compatible endpoint is configured. Other task types use
normalized exact matching. The endpoint and key are never hard-coded or
persisted as a secret:

```bash
export OSB_VLM_JUDGE_BASE_URL=http://127.0.0.1:30099/v1
export OSB_VLM_JUDGE_MODEL=Qwen3.5-35B-A3B
export OSB_VLM_JUDGE_API_KEY=your-key
osb score runs/my-proactive --judge-mode auto
```

Use `--judge-mode exact` for a deterministic diagnostic, or `--judge-mode vlm`
to require the configured judge for every proactive task type. Each scored
window records the method, model, prompt version, raw judge response, and any
error. Existing raw events are not mutated, so changing judge configuration
only requires `osb score`; it does not rerun model inference. The derived
`rescored_records.jsonl` sidecar stores these per-window details. Response-fragment
requirements for ThinkStream are documented in
[`docs/thinkstream-adapter-contract.md`](docs/thinkstream-adapter-contract.md).

The local-weight LiveCC RGB adapter is documented in
[docs/livecc-adapter.md](docs/livecc-adapter.md).

## Frozen Configuration, Telemetry, And Resume

Before loading model weights, inspect the exact Core contract with
`--preflight-only`. The snapshot freezes the release hashes, video root,
OpenCV sampler/decoder, RGB and resize policy, stream FPS, pacing, query
windows, adapter capabilities, model generation settings, and checkpoint
interval, the fixed proactive window (`5s` or `10s`), bounded final-window
evidence policy, plus the exact scorer/judge route and semantic task types. The same snapshot is stored in `resolved_config.json` for a real
run, so model comparisons use the same visual evidence and protocol.

Every adapter event keeps directly observed frame arrival/commit times,
submitted frame occurrences and pixels, query timing, actual tokenizer IDs,
generated IDs, model-call intervals, failures, and resource observations when
the adapter can expose them. QA history processing is reported separately from
query TTFT, including pre-query calls, frames/pixels, tokens, and busy time.
Unsupported values remain `null` with coverage
metadata; the Core never estimates them from configured FPS or text length.
The final `metrics.json` contains quality, TTFT/response latency,
frame-processing and on-time rates, dropped/completed frames, submitted
workload, text tokens, model calls, inference wall time, GPU memory, failure
rate, and telemetry coverage.
Bundle validation separately reports structural validity and
`official_eligible`; missing required telemetry or judge coverage keeps a run as
a diagnostic artifact but prevents publication as an official result.

Raw records and their events are durably checkpointed every 10 terminal
records by default (`--checkpoint-every N`, or `--save-every N`). Checkpoints
are atomic and resumable; only committed records with matching configuration
identity are skipped. An interrupted run remains explicitly non-finalized and
can be resumed. A finalized bundle is immutable.

```bash
osb run --task qa --release data/releases/v1.1.0 --subset tiny \
  --adapter your_adapter:adapter --video-root /path/to/videos \
  --output runs/my-qa --preflight-only
```

Raw events and predictions are preserved. Scoring writes derived metrics and
does not mutate raw inference evidence.

## Development Checks

```bash
python -m pytest -q
python -m build
```

GitHub Actions will run software checks with a deterministic test double. It
does not run real model inference, download model weights, or require a GPU.

## Release Status

The local publication candidate contains the v1.1.0 research data release and MIT-licensed
OSB code. `master` follows the latest release; `v1.1.0` is its version branch.
Each branch ships one annotation version. Data remains subject to the non-commercial research terms and
upstream license confirmations described in `DATA_TERMS.md`; source videos are
not redistributed by OSB.
