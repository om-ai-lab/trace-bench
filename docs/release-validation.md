# Release validation

English | [简体中文](release-validation.zh-CN.md)

Scope: software 0.1.0 and annotation v1.1.0. These are software checks, not
model leaderboard results.

Local checks on 2026-09-09: 135 tests passed with PyTorch available; the Core-only
sdist check skips the two model modules that require PyTorch. README smoke,
bilingual command/link checks, public-file scan and Ruff passed. QA and Proactive
original/rescored synthetic accuracies were both 1.0 with zero failures.
PyPI TLS failures required cached public dependency wheels for isolated packaging
and installation checks; no certificate checks were disabled.
Local execution used Python 3.12. Python 3.13 is included in CI; this revision
has not been locally rerun on 3.13.

## Reproduce

Run README's installation, synthetic flow and development checks from the
repository root. Generated files stay in ignored `output/`.
Use new output directories for repeated checks.

The smoke check requires one QA and one Proactive record, zero failures,
QA accuracy 1.0 and Proactive window accuracy 1.0 with an in-window answer,
in both original and rescored metrics. It also verifies synthetic/ineligible
labels. The 12-second fixture aligns its window with default 5-second polling.
A regression test uses a polling interval that misses the window and confirms
that the check rejects it. Git-based scans require a checkout; ZIP users receive
a concise nonzero error. All fenced block languages participate in bilingual
comparison; Bash, Python and JSON additionally receive syntax checks, without
executing Python snippets.

Distribution checks run tests from unpacked sdist sources, including
`tests/conftest.py`, then install the wheel in a separate environment and check
the imported package path and bundled preset, then runs both synthetic tasks
through the installed wheel. Normal setuptools egg-info in an
sdist is metadata, not a model/runtime artifact.

## Scope of model validation

LiveCC was previously checked on real tiny data with local weights: 9 QA and
9 Proactive records completed with no failures, using logical pacing and exact
diagnostic scoring. This is not a fresh GPU run of every release revision,
a wall-clock timing qualification or live semantic-judge validation.
ThinkStream has fake-runtime tests; fresh GPU validation remains pending.
See the model guides for requirements and inspect results before comparison.
