# Open Stream Bench

English | [简体中文](README.zh-CN.md)

A local benchmark for timestamped video QA and proactive responses.
Download the source videos, connect a model through an adapter, and retain
raw outputs, timing, failures and scores. Real model evaluation normally requires
a GPU; OSB does not host an online evaluator.

| Component | Version / scope |
| --- | --- |
| Software | `0.1.0` |
| Annotation snapshot | `data/releases/v1.1.0` |
| Full dataset | 833 QA, 415 Proactive records; 1,338 windows |
| Tiny setup subset | 9 QA + 9 Proactive records |
| Code / data | [MIT](LICENSE) / [data terms](DATA_TERMS.md) |

Only v1.1.0 annotations are included. Download videos and model weights separately.
See the [dataset card](docs/dataset-card.md) for populations and limitations.

## Install

Tested with Python 3.10–3.12. Clone or download
[this repository](https://github.com/om-ai-lab/Open-Stream-Bench), then enter
its root directory before running these commands:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
osb --help
osb data validate --release data/releases/v1.1.0
```

Keep the source checkout: the wheel alone does not include annotations or videos.
Model dependencies belong in the model's own environment.

## Verify the software pipeline

This generates a synthetic video, runs QA and Proactive, validates bundles,
rescores and checks the expected answers. No GPU or judge service is required.
The test double deliberately reads GT; these are software tests, not model scores.

```bash
set -euo pipefail
python scripts/make_smoke_fixture.py --output output/smoke
osb data validate --release output/smoke/release
for task in qa proactive; do
  osb run --task "$task" --release output/smoke/release --subset tiny \
    --adapter open_stream_bench.adapters:TestDoubleAdapter \
    --video-root output/smoke --output "output/smoke/$task" \
    --synthetic --judge-mode exact --checkpoint-every 5 --proactive-step-s 1
  osb bundle validate "output/smoke/$task"
  osb score "output/smoke/$task" --judge-mode exact
done
python scripts/check_smoke_results.py --output output/smoke
```

Expect both answer checks to pass, QA accuracy and Proactive window accuracy
to equal 1.0, zero failures, and `synthetic: true` / `official_eligible: false`.
The explicit 1-second polling interval is for this short fixture only.
Missing model telemetry is expected here. A valid bundle alone does not prove
that an answer was produced.

Results stay in ignored `output/`. The generator refuses an existing fixture
directory; for another smoke run change `output/smoke` consistently to a new path.
Do not delete prior experiment results to rerun a tutorial.

## Evaluate your model

1. [Prepare source videos](docs/data-setup.md) from StreamingBench and OVO-Bench.
2. Follow the [LiveCC walkthrough](docs/livecc-adapter.md), or the experimental
   [ThinkStream guide](docs/thinkstream-adapter.md).
3. For another model, implement the [adapter interface](docs/adapter-guide.md).
   The adapter can live in its own repository.
4. Run tiny, inspect predictions/failures and telemetry, then select full.
   See [scoring and resume](docs/scoring-and-results.md) for semantic judging.

Core delivers timestamped RGB uint8 arrays at 1 FPS through OpenCV.
QA receives the legal prefix and identical user content across models.
Proactive uses 5s/10s event windows or annotated state intervals, and evidence
ends at the final strict-window boundary, clamped to source duration.
Native/non-native visual state and autonomous/polling triggering are separate
comparison dimensions. See the [evaluation protocol](docs/evaluation-protocol.md).

## Documentation

- [Data and limitations](docs/dataset-card.md)
- [Examples and support status](examples/README.md)
- [Release/version policy](docs/releasing.md) and [validation](docs/release-validation.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md), [contributing](CONTRIBUTING.md),
  [security](SECURITY.md), [code of conduct](CODE_OF_CONDUCT.md)
- [Citation](CITATION.cff) and [changelog](CHANGELOG.md)

## Development checks

```bash
mkdir -p output
python -m pytest -q --basetemp=output/pytest
ruff check .
python scripts/check_docs.py
python scripts/check_public_files.py
python -m build --outdir output/dist
python scripts/check_distribution.py --dist output/dist --output output/distribution-check
```

Use fresh build/check directories when repeating distribution checks.
CI verifies synthetic answers and unpacked-source tests. GPU inference and
live semantic-judge validation are separate checks.
