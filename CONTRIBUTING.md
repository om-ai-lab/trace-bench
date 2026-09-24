# Contributing

English | [简体中文](CONTRIBUTING.zh-CN.md)

Install `'.[dev]'` and run the development checks and synthetic flow in README.
For issues, include software/data versions, command, expected behavior and
sanitized logs. Exclude videos, weights, credentials and private raw bundles.

Keep model-specific behavior in adapters. Evidence, prompt, scoring and failure
policy changes need regression tests and a compatibility review.
Do not widen QA parsing as incidental cleanup or edit finalized raw runs.
Explain whether users need rescoring or new inference.

TRACE-owned code contributions use MIT; preserve upstream licenses for copied
material. Data follows [data terms](DATA_TERMS.md).
Follow the [code of conduct](CODE_OF_CONDUCT.md) and
[release policy](docs/releasing.md). Contributions in English or Chinese are welcome;
keep paired documentation and command blocks aligned.
