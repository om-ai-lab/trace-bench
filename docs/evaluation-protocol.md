# Open Stream Bench Evaluation Protocol

Status: prompt and execution contract v4

This document is the normative evaluation contract for the Open Stream Bench
QA and Proactive Response tasks. It separates benchmark semantics, which must
be comparable across models, from model-native prompt and control-token
mechanics, which belong in an adapter.

## 1. Core Principles

The Core owns the benchmark release, record selection, legal timeline, video
sampling, evidence boundary, run persistence, and scoring population. The Core
is local Python code; it is not an online evaluation service. Proactive visual
evidence continues only through the last strict response window. For a point
trigger this is at most `trigger + W` (with dense windows ending at the next
trigger); reviewed state intervals keep their annotated end. If the source
video ends earlier, an autonomous wall-clock session may remain open only for
the remaining final strict-window time, without new frames or polling. A legacy
release `deadline_s` is provenance only and is never an evaluation cutoff.

Every primary comparison uses the same:

- data release and eligible record IDs;
- source-video identity and Core-selected evidence timestamps;
- question or instruction text and ground truth;
- causal frame boundary and versioned response-window policy;
- scoring and failure-denominator policy.

The v0/v1 Core uses one Core-owned OpenCV sampling path. Adapters receive
timestamped RGB observations and must not replace the primary temporal sampler
with model-author keyframes or a private video replay path. Such recipes are
diagnostic runs and need a separate run identity.

The benchmark-owned QA user content is byte-identical across model families. A
native system message is allowed. A tokenizer/chat interface may mechanically
add required role, BOS/EOS, or control tokens around the unchanged content, but
an adapter may not rewrite, summarize, reorder, or augment the question,
options, or answer instruction. The system prompt and serialization method are
recorded for audit.

## 2. System Prompt Policy

### QA

1. Use the model's native system prompt when it has one.
2. If it has no system prompt, omit the system message by default.
3. Add a neutral generic system message only when the model interface requires
   one.
4. A system prompt may describe the model's native chat or control-token
   protocol, but may not add benchmark-specific evidence, hints, answers, or a
   different question.

### Proactive Response

1. Use the model's native streaming system prompt when it has one.
2. Preserve native silence/response markers such as `<silent>`,
   `<|silent|>`, or `</silence>` when they are part of the model protocol.
3. If the model has no native response-decision protocol, use the following
   minimal fallback system prompt, or an equivalent adapter-declared version:

   ```text
   You are observing a live video stream frame by frame.
   Follow the user's instruction.
   If the available evidence is insufficient, output WAIT.
   If the evidence is sufficient, output only a concise answer.
   ```

4. A native system prompt that only asks the model to narrate a video, without
   a compatible answer/silence decision protocol, is not a standard Proactive
   Response integration. The adapter must replace that bootstrap behavior or
   mark the run as incompatible with the primary track.

## 3. QA Contract

### Benchmark prompt

The Core sends the same exact user content to every QA adapter:

```text
Question: {question}
Options:
{options, one per line}

Respond only with the letter corresponding to your chosen option
(e.g., A, B, C). Do not include any additional text or explanation.
```

The question, option text, order, question time, legal evidence prefix, and
answer key come from the canonical release. The adapter receives this exact
user content. Model-native role/control serialization may surround it but may
not alter any character in the content itself.

### Execution

1. The Core samples only the legal evidence interval.
2. The adapter receives observations in timestamp order. An offline adapter may
   buffer them; an incremental adapter may update persistent state.
   Before the query it may encode, commit, generate, and run other model-native
   work from those legal frames. Preserve that work as telemetry; pre-query
   text is not a QA prediction and is excluded from QA TTFT.
3. The Core records one benchmark-owned semantic query-arrival timestamp at the
   question time and sends exactly one QA query. A batched adapter may queue the
   request before committing the question-time frame, but QA TTFT starts at the
   same semantic arrival boundary for every adapter and therefore includes any
   required question-time frame processing.
4. The adapter returns the raw provider output and a normalized answer event.

### Output and scoring

The preferred output is one label from the record's actual option set. Native
punctuation or wrappers such as `B.` or `: C` may be normalized by the adapter
or scorer. The raw text remains in the Run Bundle. An output that cannot be
reliably and uniquely mapped to one option is invalid and scores zero under the
versioned QA policy. Ambiguous text such as `A or B` is never resolved by taking
the first label.

QA primary quality is exact choice accuracy. Formatting compliance and failure
rate are reported separately when available.

## 4. Proactive Response Contract

### Benchmark instruction

The Core provides the canonical instruction as raw benchmark text, for example:

```text
The woman in the black coat walks towards the direction of the man in yellow,
what action does she do with the man?
```

The Core does not prepend `Question:`, `Your response:`, or a universal `WAIT`
wrapper. This prevents a benchmark-owned control syntax from overriding a
model's native response format.

The adapter may deliver the raw instruction as a native user message, a native
bootstrap request, or a scheduled polling request according to its declared
capabilities. The adapter must not add task-specific hints or future evidence.

### Response triggering

- A native autonomous adapter receives the instruction once at its legal
  instruction boundary, continues to receive observations, and may emit
  events from observation calls without repeated Core queries.
- A polling/query adapter receives the same raw instruction at the frozen Core
  schedule. At a query exactly at frame timestamp `t`, Core delivers and commits
  the legal frame at `t` before dispatching the query. A query strictly between
  frame timestamps cannot see the next frame. The schedule and response-
  triggering mode are recorded in the Run Bundle.
- A hybrid adapter must declare both persistent ingestion and evaluator
  polling. It is not relabeled as autonomous merely because it keeps state.

Proactive response triggering is a separate evaluation axis from visual-state
streaming. The primary Proactive track requires persistent incremental state,
one instruction, autonomous output, and wall-clock pacing. Persistent-state
polling is a prompted baseline; stateless polling is a Non-native baseline.
Neither polling result is mixed with the autonomous-primary ranking.

### Output normalization

The adapter preserves the provider output and maps it to the canonical events:

- substantive model content -> `ANSWER`;
- native silence or the fallback marker -> `WAIT`;
- timeout, protocol violation, malformed output, or model error -> `FAILURE`.

The adapter may assemble response fragments into response episodes, but it must
preserve response IDs, sequence ordering, visible text, trigger/arrival times,
and raw fragments. Silence closes an active response episode.

### Proactive timing and scoring

The official point-trigger tolerance is selected before a run and must be
exactly `5s` or `10s` (`--proactive-window-s`). For ordered point triggers
`t_i`, the strict window is the non-overlapping half-open interval

```text
[t_i, min(t_i + W, t_{i+1}))       W in {5s, 10s}
```

The final point uses `[t_last, t_last + W)`. A `state_interval` keeps its
reviewed `[start, end)` interval and is not artificially truncated to `W`.
Window boundaries are half-open, so an answer exactly at the next trigger
belongs to the next event.

The pre-instruction visual history is a separate frozen parameter,
`--proactive-history-window-s` (5 seconds in the current profile). Changing W
from 5 to 10 seconds changes only response tolerance; it never supplies more
history to the model.

The Core reports two separate timing families. `strict_all_window` keeps every
window in the denominator; `strict_observable_window` keeps only windows with
at least one Core-delivered observation in the half-open interval and reports
coverage. `post_trigger_eventual` accepts a response after the trigger until
the next trigger for non-final point events. For the final point it ends at the
final strict-window end; state intervals end at their reviewed state end. It has
no global deadline and never grants unbounded credit.
A response episode is assigned to at most one event; extra answers are reported
as redundancy.

For each point window the scorer reports `inter_trigger_gap_s`,
`effective_window_duration_s`, actual `observed_frame_count`, and
`crowded_window = inter_trigger_gap_s < W`, plus separate crowded and
non-crowded strict summaries. Assignment remains time-first: a delayed answer
is never moved back to an earlier event merely because its text resembles that
event's answer.

The evidence endpoint is the last strict-window end, clamped to the measured
source-video endpoint when a container frame-count value is available. Core
never decodes the entire source merely to discover its duration. If duration
metadata is unavailable, the source endpoint is recorded as unknown and Core
uses the GT-derived endpoint without a source clamp. If the source video ends
first, an autonomous wall-clock run remains open without new frames or polling
for
`max(0, last_strict_window_end_s - video_end_s)`. First-token monotonic time is
mapped onto the stream clock for window membership. If first-token time is not
observable, Core uses its receipt time for the completed response as a
conservative scoring boundary and marks first-token coverage missing; such a
run is not eligible for the official latency result. A later shutdown drain may
persist an already-started response but cannot start a newly scoreable one.

Each annotated response window is scored for whether a response was emitted in
the legal window, whether it is correct, and whether it arrived outside the
window. The primary report includes response correctness, no-output cases,
premature/late intrusion, redundant responses, response latency,
strict-all/strict-observable coverage, eventual correctness, and failure
coverage.
The pooled proactive response-latency distribution uses answered strict
`in_window` response windows as its population. `before_window`, `no_output`,
and redundant/outside episodes remain in their respective quality diagnostics
but do not enter that latency population. An in-window answer whose trigger
and first-response clocks cannot be causally ordered remains in the denominator
with missing latency, so telemetry coverage cannot be improved by dropping the
window.

Exact text matching may be used as a deterministic diagnostic. Semantic VLM
judging is the primary method when the task permits multiple valid phrasings.
The current reference judge is `Qwen3.5-35B-A3B`; its OpenAI-compatible
endpoint and API key are supplied by the user at scoring time and are never
hard-coded in the repository.
The judge model, endpoint configuration, prompt version, raw response, and
errors are recorded as derived scoring metadata. Judge transport or parsing
failure makes the derived official score incomplete; it is not silently treated
as model error. Changing the judge does not rerun model inference.

## 5. Core and Adapter Boundary

| Responsibility | Core | Adapter |
| --- | --- | --- |
| Data release and record eligibility | Owns | Consumes |
| Legal timestamps and response-window policy | Owns | Must obey |
| Primary frame sampler | Owns | Receives observations |
| QA benchmark text | Owns | Wraps in native message structure |
| Proactive raw instruction | Owns | Delivers through native interface |
| Native system and mechanical role/control serialization | Does not prescribe | Owns without changing QA user content |
| Provider response parsing | Does not implement | Owns |
| Canonical events and raw evidence | Persists | Produces |
| Final scoring population | Owns | Supplies predictions/events |

An adapter must reject unsupported capability combinations rather than silently
changing evidence, timing, prompting, or failure behavior.

## 6. Required Run Evidence and Report

Every Run Bundle records the data, protocol, sampler, prompt contract, system
prompt metadata, adapter, model, hardware, generation settings, deployment,
execution pacing, and code identities/hashes.

Raw records and events preserve, when observable:

- Core-delivered and adapter-submitted frame counts;
- unique/duplicate/dropped frames and submitted pixels;
- frame arrival and model-state commit times;
- query/instruction dispatch, first-token, and completion times;
- actual text-token IDs and generated-token IDs;
- model-call intervals and inference wall time;
- GPU baseline/peak/increment memory;
- failures, timeouts, protocol violations, and retries;
- provider output and adapter preprocessing metadata.

`events.jsonl` is the scoring source of truth. Any legacy embedded event copy in
a record must match its sidecar events exactly or bundle validation fails.

The final report includes:

- QA accuracy and completion/failure rate;
- proactive window correctness, no-output, intrusion, and redundancy;
- QA TTFT and proactive response latency p50/p95;
- frame-processing p50/p95, on-time rate, lag, dropped-frame rate, and stream
  completion rate;
- processed/submitted frames and pixels, model calls, and inference wall time;
- input/output text tokens when directly observable;
- QA history-processing elapsed time, model busy time, calls, frames/pixels,
  actual text tokens, and frame-commit cost separately from query TTFT;
- peak GPU memory when directly observable;
- telemetry coverage and failure counts/types.

An inapplicable or unobservable field is reported as `N/A` with a reason. The
Core never estimates a missing value from configured FPS, text length, or a
model's claimed capacity.

Structural bundle validity and publication eligibility are separate. Bundle
validation reports `official_eligible` plus explicit reasons. Missing required
telemetry, incomplete GPU attribution, judge failure, synthetic/provisional
data, or a non-primary Proactive execution track prevents official publication
without erasing the diagnostic result.

Use `video_time_s` for causal/ground-truth semantics and a monotonic runtime
clock for measured intervals. Do not subtract values from these clock domains.

## 7. Persistence, Resume, and Failure Fairness

The Core persists raw events and predictions, not only final scores. A run
checkpoint is written after every 5 or 10 newly terminal records (default 10),
including each record's associated events. A final partial checkpoint is also
written on normal completion or handled interruption.

Resume skips only valid committed terminal records with matching run/config
identity. Incomplete records are rerun without duplicating committed events.
Finalized bundles are immutable; rescoring writes derived sidecars without
mutating raw inference evidence.

The default fairness policy does not automatically retry an individual model
failure. The first attempt remains visible in the run and in the denominator.
A deliberate retry must create a new run identity and retain the original run
for comparison.

## 8. Leaderboard and Versioning

Visual-state reporting has two categories:

- `Native Streaming`: persistent per-record state and incremental Core
  observations;
- `Non-native Streaming`: prefix/window replay or other reconstruction at each
  query.

For Proactive Response, autonomous versus polling is independently decisive.
The first official Proactive experiment matrix contains only Native Streaming,
autonomous, wall-clock runs. Native polling and Non-native polling are separate
prompted baselines. QA uses one scheduled query and remains organized only by
its visual-state category.

Any change to data, evidence, timing, prompt contract, system/fallback prompt,
adapter behavior, scorer, or inference settings creates a new run/protocol
identity. Historical proactive runs made with the old Core `WAIT` wrapper are
diagnostic and must be rerun under this contract before entering the primary
leaderboard. QA runs are eligible only when their canonical question/options
prompt and evidence contract are recorded and unchanged.
