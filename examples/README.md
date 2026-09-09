# Adapter examples

English | [简体中文](README.zh-CN.md)

| Integration | Scope | Guide |
| --- | --- | --- |
| LiveCC | Local weights; previously checked on real tiny data/GPU | [Setup](../docs/livecc-adapter.md) |
| ThinkStream | Experimental; fake-runtime contract tests, fresh GPU validation pending | [Setup](../docs/thinkstream-adapter.md) |
| TestDoubleAdapter | Synthetic only; deliberately reads GT | [Software smoke](../README.md#verify-the-software-pipeline) |

LiveCC `logical.json` is for fast diagnostics; `wall_clock.json` must be paired
with Core wall-clock pacing for timing experiments. Source code, weights and
model dependencies are obtained separately. Other adapters may live in external
repositories and load through `module:Class`.

Successful execution is separate from conformance, quality and timing eligibility.
Review actual state reuse, response behavior, failures, judge and telemetry coverage.
