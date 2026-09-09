# Evaluation protocol

English | [简体中文](evaluation-protocol.zh-CN.md)

This is the execution/scoring contract shipped with software 0.1.0.
Bundle compatibility IDs remain `osb-contract-v4` and `osb-scoring-v6`.
Software packaging changes do not redefine these rules.

## Shared evidence and prompts

Core loads local annotations, owns the timeline, and delivers RGB uint8 arrays
at 1 FPS using OpenCV. Source frame index is `floor(t * source_fps + 0.5)`;
BGR is converted to RGB. The same legal timestamps and evidence budget apply
across compared models. Adapters may record native resizing/chunking, but may
not substitute keyframes, replay future frames or read source videos independently.

QA user content is identical across models: canonical question, options in
their original order, and the instruction to answer only with the option letter.
Use the model's native system prompt if available; otherwise omit it unless the
interface requires a neutral one. Role/control-token serialization may surround
the user content but must not modify it. Record the system prompt and serializer.

Proactive receives the raw canonical instruction without a universal question
or WAIT wrapper. Preserve native silence protocols. Only a model without a
native answer/silence mechanism uses the minimal fallback system prompt:

```text
You are observing a live video stream frame by frame.
Follow the user's instruction.
If the available evidence is insufficient, output WAIT.
If the evidence is sufficient, output only a concise answer.
```

A narration-only bootstrap is not equivalent to instruction-following Proactive.
Replace it with a compatible interface or report the integration as incompatible.

## QA

Legal history may be encoded, buffered, committed or used for native generation
before question time. Retain its costs and events; pre-query text is not the QA
answer. Core sends one query at the semantic question boundary.
Chunked adapters may declare `before_observation_deferred` and queue the query
before processing the question-time frame, but must consume that frame before
answering. TTFT starts at the shared query-arrival boundary, including required
frame processing and before CUDA synchronization.

Quality is exact choice accuracy over all records, including failures.
The current parser accepts a single valid option label after existing wrapper
and reasoning-block normalization (e.g. `B.` or `: C`).
Option-plus-answer text, answer phrases and incidental letters in sentences are
invalid. Adapters must not extract a compliant label from noncompliant prose.
Raw provider text is preserved; this release does not widen the parser.

## Proactive execution and windows

Autonomous adapters receive the instruction once and emit as observations arrive.
Polling adapters receive repeated requests on a frozen schedule. A query at a
frame timestamp sees that frame first; a query between frames cannot see the
next one. Persistent-state polling is a prompted baseline, not autonomous output.

GT times describe visual facts: onset, completion, sufficient clue or a state
interval. Evidence clips support review, not response tolerance.
For point triggers `t_i` and fixed W = 5s or 10s, strict windows are:

```text
[t_i, min(t_i + W, t_{i+1}))
[t_last, t_last + W)
```

State intervals retain their annotated `[start, end)`. Boundaries are half-open.
Pre-instruction history is independently fixed at 5s, not W.
Dense windows are not merged or moved to hit sampled frames. Report gap,
effective duration, observation count and crowded/non-crowded summaries.
Zero observed frames indicate protocol observability, not automatically bad GT.

Evidence ends at the final strict-window endpoint, clamped to source duration
when metadata is available. Core never decodes the whole source to discover
its end. Unknown duration stays unknown; use the GT endpoint.
Legacy `deadline_s` is provenance only.

If the source ends earlier, an autonomous wall-clock session may use the remaining
final strict-window time without new frames or polls. First-token monotonic time
maps to the stream clock; when unavailable, completed-response receipt is the
conservative boundary and first-token coverage remains missing.
Bounded shutdown may finish an already timely-started delta/snapshot episode,
but cannot start a new scoreable answer or model call. Complete events are
independent answers; stable response IDs and final markers are required for fragments.

## Proactive scores and judge

Report all three views with their populations:

- `strict_all_window`: every window, including misses and failed records.
- `strict_observable_window`: windows with at least one Core-delivered frame.
- `post_trigger_eventual`: after a trigger until the next point trigger;
  the final point ends at the final strict-window end, states at their state end.
  This is a bounded view without a global legacy deadline, not unlimited credit.

Assign an episode to at most one event, time-first. Do not credit a later event's
answer to an earlier one because its text matches. Also report no-output,
outside-window intrusion and redundant answers.
Latency p50/p95 uses answered strict in-window windows; unavailable causal timing
remains missing in that population.

Exact matching is deterministic. Semantic judging supports valid paraphrases.
`auto` uses a configured judge for SSR/CRR and exact matching for other types;
`vlm` judges all Proactive types. The judge currently receives question,
reference and prediction text, not video frames. Freeze model, prompt, route,
temperature and window settings across comparisons. Record raw judge responses,
errors and coverage. Judge failures/fallbacks are diagnostic, not model errors.
See [scoring](scoring-and-results.md).

## Metrics, tracks and persistence

Report quality; TTFT/response latency; frame-processing p50/p95, lag, on-time,
dropped and completion rates; submitted frames/pixels; actual text tokens;
model calls and inference wall time; isolated GPU baseline/peak/increment;
record completion, failure types, timeouts, retries and measurement coverage.
QA history costs are reported separately from query costs, including elapsed
time, inference intervals, calls, tokens, frames/pixels and commits.
Keep video time separate from monotonic duration clocks. Do not estimate missing
tokens, TTFT, vision tokens or resource usage from text length or configured FPS.

Visual-state categories are Native Streaming (actual persistent model-state
reuse) and Non-native Streaming (prefix/window replay). A Python frame list is
not native state. Primary Proactive requires native state, autonomous output and
wall-clock pacing; polling baselines remain separate. QA has no proactive
triggering track. Capability declarations require implementation review.

Structural validity is not official eligibility. Synthetic/provisional runs,
logical pacing, incomplete required telemetry, judge failure or an incompatible
Proactive track prevent official qualification while retaining diagnostic scores.

Core checkpoints raw records and their events every N terminal records
(default 10; 5 supported), plus a final partial batch. Resume skips valid
committed successes and failures, reruns incomplete records and rejects changed
run identity. No automatic per-question retries; intentional retries need new
runs. Unusable initialization or poisoned CUDA aborts after checkpointing.
Finalized bundles are immutable; `events.jsonl` is authoritative and embedded
copies must match. Rescoring writes sidecars without editing raw evidence.

Changes to model, data, evidence, prompt, timing or inference settings require a
new run. Scoring-only changes can rescore preserved evidence when sufficient.
Compare only matching data populations, execution tracks and scoring settings.
