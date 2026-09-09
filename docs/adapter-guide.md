# Implementing an adapter

English | [简体中文](adapter-guide.zh-CN.md)

An adapter can live in its own repository. Install it and OSB in the model
environment, then use `--adapter module:Class --adapter-config file.json`.
No Core registry edits are needed. See [LiveCC](livecc-adapter.md) and experimental
[ThinkStream](thinkstream-adapter.md); [TestDoubleAdapter](../src/open_stream_bench/adapters.py)
is synthetic and deliberately reads GT. Never copy its answer-selection logic.

## Boundary

Use [models.py](../src/open_stream_bench/models.py) and the protocols in
[adapters.py](../src/open_stream_bench/adapters.py).

1. Declare decoded-frame delivery, persistent/stateless state, query/polling/
   autonomous triggering, pacing and deployment. Core and adapter pacing must match.
2. Load weights once; create per-record state in `open(context)`.
   Context contains evaluator metadata: never feed answers, GT windows,
   evidence descriptions or source paths to the model.
3. `observe(observation)` receives timestamped RGB arrays. Record actual
   resizing, chunking and model-state commits; buffering alone is not a commit.
4. `query(request)` receives benchmark text in `request.text`. Preserve it
   byte-for-byte. Native system prompts and mechanical control serialization
   are allowed and recorded. History computation is allowed and measured.
5. QA answers only the shared option instruction. Autonomous Proactive gets one
   instruction; polling is separate. Preserve native silence, mapping it to WAIT
   without forcing the model to emit the literal fallback word.
6. Return raw-preserving `ModelEvent` objects. Fragments need stable
   `response_id`, ordered `sequence_id`, `text_mode` and `is_final`.
   Do not count each token as a new answer.
7. Flush pending chunks at the Core evidence boundary. Release session/process
   resources in `session.close()` / `adapter.close()`; shutdown cannot create
   new scoring time.

Chunked QA may declare `before_observation_deferred` only if it must queue the
query before the final frame; the answer must consume that frame.

## Measurements and failures

Measure generation first token directly. Keep video time and monotonic runtime
separate. Report actual calls, token IDs, submitted frames/pixels, commits,
GPU memory and failures where observable; unknown values stay missing.
Never estimate token counts from text length or work from configured FPS.
Preserve recoverable failures; raise `FatalEvaluationError` for unusable
initialization or poisoned CUDA. Follow the [protocol](evaluation-protocol.md).

## Validation

Run preflight, real tiny inference and bundle validation; inspect answers,
failures and telemetry before full evaluation. Tiny normally needs a GPU.
Synthetic tests check software only. Native status requires actual model-state
reuse evidence; declarations and a successful run are not conformance proof.
