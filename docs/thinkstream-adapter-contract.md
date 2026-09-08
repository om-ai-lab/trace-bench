# ThinkStream Adapter Contract

This document is the implementation checklist for the ThinkStream-side
adapter. The Open Stream Bench Core owns sampling, causal timing, response
assembly, scoring, and reporting. ThinkStream owns model-specific parsing and
must return provider output through the normalized event fields below.

## Required response fields

Every proactive response event must include:

```json
{
  "kind": "answer",
  "logical_time_s": 282.0,
  "text": "up",
  "response_id": "episode-17",
  "sequence_id": 3,
  "text_mode": "delta",
  "is_final": false,
  "response_decision": "response",
  "raw_output": {"provider_text": "<response>up<|im_end|>"}
}
```

Use the following rules:

- `response_id` stays constant for all fragments that belong to one logical
  answer and changes for the next answer episode.
- `sequence_id` is monotonically increasing within a record. Core uses it for
  deterministic ordering when callbacks finish out of order.
- `text_mode` is `delta` when `text` is a new fragment, `snapshot` when `text`
  is the complete answer-so-far, and `complete` when the event is already a
  complete answer.
- `is_final=true` is required on the last fragment of an episode. If the model
  only reveals that a response ended when the next silent step arrives, buffer
  one event or emit the final marker before returning the previous fragment.
- `response_decision=response` is required for substantive output. Silent
  output must be a canonical `kind=wait`, `text=WAIT`,
  `response_decision=silent` event. It closes any active delta episode.
- Preserve the complete provider payload and generated token IDs in
  `raw_output`; Core only normalizes the visible answer for scoring.

The fields may be emitted at the top level of the `ModelEvent` or in its
`telemetry` object for compatibility with older adapters, but new adapters
should use the top level.

## ThinkStream-specific mapping

For the current `StreamingWindowInferenceEngine` loop:

1. Parse `<response>...</response-or-im_end>` as visible output and map
   `<silent>` or standalone `WAIT` to a `wait` event.
2. Keep a `response_id` in the adapter session. Start it when the first
   response control token is emitted, keep it while subsequent response
   fragments continue, and close it when the model emits silent output, a new
   response episode, or the record ends.
3. Return each generated response fragment as `text_mode=delta`. Include the
   whitespace that belongs between word-level fragments in `text`; Core will
   preserve explicit whitespace and has a conservative word-fragment fallback.
4. Mark the final fragment with `is_final=true`. Do not create a new response
   ID for every model inference chunk.
5. Keep `chunk_idx` in telemetry for diagnostics, but do not use it as the
   response identity.

The current v8 bundle emits `He`, `stands`, `up`, ... as separate `answer`
events without response identity or text mode. Core therefore treats those
events as independent complete answers for backward compatibility. That is
deliberately conservative and cannot reconstruct the intended sentence. A
ThinkStream run intended for official scoring must be rerun with the contract
above, or an explicit external migration must add the same fields before
rescoring.

## Timing and telemetry

Keep the existing telemetry fields unchanged:

- `first_token_perf_ns` is the first valid generated token for the response;
- `response_completion_perf_ns` is generation completion;
- `model_calls`, actual input IDs, generated token IDs, frame telemetry, and
  raw provider output remain attached to the event;
- `response_latency_ms` is computed by Core from the trigger-frame arrival and
  the first valid response token. Do not report a configured FPS as a timing
  measurement.

The adapter must still declare persistent state and autonomous response mode
for the Native Streaming leaderboard category. Response assembly metadata does
not by itself establish native streaming.
