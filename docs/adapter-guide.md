# Implementing an adapter

Install your model's dependencies in its own environment, then install OSB with
`python -m pip install -e /path/to/open_stream_bench`. An adapter can live in
your own repository. Make that package importable and pass `--adapter module:Class`
plus a JSON `--adapter-config`. No Core registry edit is needed.

## Reference implementations

| Reference | What to study | Setup |
| --- | --- | --- |
| [LiveCC](../src/open_stream_bench/livecc_adapter.py) | Persistent KV state, RGB preprocessing, QA and autonomous Proactive, measured GPU workload | [Guide](livecc-adapter.md) |
| [ThinkStream](../src/open_stream_bench/thinkstream_adapter.py) | Two-frame chunks, deferred QA query, native silence and response fragments | [Guide](thinkstream-adapter-contract.md) |
| [TestDoubleAdapter](../src/open_stream_bench/adapters.py) | Smallest runnable interface and software tests | `python -m pytest -q tests/test_cli.py tests/test_core.py` |

Start with LiveCC for a real integration; use ThinkStream for chunked generation.
The test double reads GT deliberately and is strictly synthetic; never copy its
answer-selection logic into a real adapter. Neither model example's presence
certifies a run as official: bundle validation checks actual evidence coverage.

The separately maintained MiniCPM integration illustrates a useful contrast:
resetting the session and replaying the prefix is non-native/polling, whereas
its native integration keeps state. JoyAI illustrates a user-operated service,
and AURA adds a runtime abstraction. Those larger deployment-specific adapters
are not bundled as tutorial dependencies or copied from private paths.

## Implement the boundary

Use the types in [models.py](../src/open_stream_bench/models.py) and the
protocols in [adapters.py](../src/open_stream_bench/adapters.py).

1. Declare `AdapterCapabilities`: decoded frames, persistent or stateless state,
   query/polling/autonomous response mode, logical or wall-clock pacing, and
   in-process or user-service deployment. Core and adapter pacing must agree.
2. Load weights once in the adapter; create fresh per-record state in
   `open(context)`. The context is trusted evaluator metadata, not a model
   prompt: do not expose answers, GT windows, metadata evidence descriptions,
   or the source-video path to the model.
3. `observe(observation)` receives timestamped RGB uint8 NumPy frames. Use
   these frames only. Record actual resizing/chunking and commits; buffering a
   frame is not a model-state commit. Return available model events.
4. `query(request)` receives the exact benchmark user text in `request.text`.
   Preserve it byte-for-byte. Native system prompts and necessary role/control
   serialization are allowed and must be recorded. QA prefix computation is
   allowed and its costs count, but prefix text is not the QA answer.
5. QA answers follow the shared single-option instruction. Proactive receives
   its instruction once for autonomous execution; polling is a separate baseline.
   Map native silence to WAIT without forcing a model with a native silence
   mechanism to emit the literal word WAIT.
6. Return `ModelEvent` with raw output preserved. For streaming fragments keep
   stable `response_id`, ordered `sequence_id`, `text_mode`, and `is_final`.
   Do not turn every token into a separate answer episode.
7. Release session resources in `session.close()` and process resources in
   `adapter.close()`. Follow the existing examples for Core end-of-evidence
   hooks and shutdown drain; shutdown cannot extend scoring time.

Keep video timestamps and `time.perf_counter_ns()` separate. Measure first token
at generation, not at completed-response receipt; record unknown values as
missing. Do not estimate tokens from string length or work from configured FPS.
For required telemetry names and official eligibility, follow the
[evaluation protocol](evaluation-protocol.md). Preserve recoverable failures;
raise `FatalEvaluationError` for unusable model initialization or poisoned CUDA.

For chunked QA, declare `before_observation_deferred` only when the query must
be queued before the final frame; generation must still consume that frame.

## Try a real model

Copy a configuration from [examples](../examples/README.md), set local model
paths, then run preflight, tiny inference, and bundle validation. Change
`--subset tiny` to `--subset full` only after checking outputs and coverage.
Tiny uses real model inference and normally needs a GPU. Synthetic tests only
check software and cannot produce benchmark results.
