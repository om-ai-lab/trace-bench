# Contributing

Install with `python -m pip install -e '.[dev]'`. Run `python -m pytest -q`,
`ruff check .`, `python -m build`, and the release validation command in README.
For a bug report, include the package/data/protocol/scorer identities, a minimal
command, and sanitized error output. Exclude credentials, videos, model weights,
and raw bundles containing private deployment information.

Keep model-specific behavior in adapters. Prompt, frame sampling, scoring and
failure-policy changes need explicit protocol/version review and regression
tests. Never edit finalized raw runs or widen QA parsing as incidental cleanup.
Explain how a change was tested and whether existing results require rescoring
or new inference. New code contributions use MIT; retain upstream licenses for
third-party material. See docs/releasing.md for the branch/data policy.
