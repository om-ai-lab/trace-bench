# Benchmark results and findings

English | [简体中文](benchmark-results.zh-CN.md)

Explore these results with the [interactive scorecard and plots](results-explorer.md).

This page summarizes Chapters 3–5 and Appendix B of the Open Stream Bench technical
report, as reviewed on 2026-09-10. Figures are the report's selected figures;
tables describe the tested configurations, not a combined leaderboard or a claim
that every adapter is included in this repository.

## Tasks and experiment scope

| Task | What the model must do | Report population |
| --- | --- | --- |
| Timestamped QA | Answer a question arriving at a specified time using the legal video history | 833 records / 340 videos |
| Proactive Response | Receive an instruction before an event, monitor subsequent evidence, and decide when to respond | 407 standard records / 178 videos / 1,270 windows |

Core supplies causal RGB observations at 1 FPS with wall-clock pacing.
Point triggers distinguish event onset, action completion and sufficient clues;
states use annotated intervals. Failures remain in score denominators.
Proactive results use W=5s scoring, with earlier next-trigger boundaries and
unchanged state intervals.

**Result provenance:** these report analyses use retained v1.0.0 inference bundles,
with the v1.1.0 standard population applied to Proactive results and record-scoped
telemetry. They are not newly executed v1.1.0 runs. The shipped release includes
another 8 sampling-stress records / 68 windows; `--subset full` includes them,
so its 415-record population differs from this report table.
See [release fields and subsets](../data/releases/README.md).

## What the benchmark reveals

- Similar QA scores can hide reliability differences: LiveCC and MOSS-Preview
  score 65.19% and 65.07%, but complete 93.88% and 100% of records.
- Similar Proactive scores can hide notification behavior: MOSS-VL and AURA
  score 8.05% and 7.92% SWA, but produce 185.6 and 28.4 redundant responses
  per 100 target windows, a roughly 6.5-fold difference.
- Higher window scores can come with more extra output and failures:
  LiveCC scores 12.98% SWA versus MOSS-VL's 8.05%, while producing 562.0
  versus 160.2 outside-window responses per 100 windows and completing
  87.71% versus 100% of records.
- Polling and autonomous response measure different interactions. MiniCPM-O's
  40.91% polling SWA measures externally prompted checks, not autonomous triggering.
- Trigger-specific strengths can reverse: MOSS-Preview scores 23.54% on
  sufficient-clue windows versus MOSS-VL's 8.75%, but 0% versus 7.21% on
  action-completion windows. These subsets differ in content and size.

These observations motivate reporting quality, timeliness, extra responses,
workload and completion separately rather than reducing them to one overall score.

## QA results

Accuracy below is the report's **Recoverable Accuracy**: accept one unambiguous
explicit option label, including an answer introduction or option text beginning
with the label; reject two distinct labels and unlabelled prose. Hidden thinking
is removed before parsing. This is **not the software 0.1.0 default strict
single-label `accuracy`**. Re-running `osb score` alone does not reproduce this
report analysis; this documentation update does not change the Core parser.

### Native model + adapter

| Model | Recoverable accuracy | Record completion | Query-stage p50 (ms) | Recorded output tokens | Invalid output |
| --- | ---: | ---: | ---: | ---: | ---: |
| LiveCC | 65.19% | 93.88% | 165.2 | 146,064 | 6.12% |
| MOSS-Preview | 65.07% | 100.00% | 138.1 | 42,206 | 1.92% |
| MOSS-VL | 75.03% | 99.88% | 374.6 | 39,768 | 0.84% |
| ThinkStream | 61.46% | 100.00% | 411.0 | 349,476 | 0.00% |
| VideoLLM-Online | 2.64% | 100.00% | 681.1 | 39,047 | 95.32% |

### End-to-end system

| System | Recoverable accuracy | Record completion | Query-stage p50 (ms) | Recorded output tokens | Invalid output |
| --- | ---: | ---: | ---: | ---: | ---: |
| JoyAI | 67.47% | 91.36% | 876.1 | 2,286 | 8.52% |

### Non-native prefix input

| Model | Recoverable accuracy | Record completion | Query-stage p50 (ms) | Recorded output tokens | Invalid output |
| --- | ---: | ---: | ---: | ---: | ---: |
| AURA | 73.83% | 99.88% | 819.7 | 2,469 | 0.60% |
| MiniCPM-O (polling) | 71.31% | 99.88% | 611.9 | N/A | 6.60% |

QA asks once per record; “polling” identifies MiniCPM-O's corresponding Proactive
configuration. Completion is execution status, while invalid output measures
failure to parse a legal choice.

![QA accuracy, recorded query duration and generation workload](assets/results/fig_qa_accuracy_workload.png)

Query-stage duration is measured from recorded query boundaries and may exclude
history processing; it is not end-to-end latency or TTFT. Output tokens include
recorded history generation, thinking, control text and answers. Missing values
are not estimated; different tokenizers and incomplete telemetry prevent treating
these totals as equal compute or monetary cost. The right panel divides totals
by 833 records and uses a logarithmic axis; shapes distinguish evaluation groups.

## Proactive results

Strict Window Accuracy (SWA) is mean window content score, including partial
credit. TCR@5s additionally requires a response onset within the 5-second latency
threshold; missing causal latency contributes zero. Both retain all 1,270 windows
in the denominator. Semantic judging is text-only using the shared
Qwen3.5-35B-A3B / `osb-vlm-judge-v1` configuration; timing is scored separately.

### Autonomous model + adapter

| Model | SWA | TCR@5s | Record completion |
| --- | ---: | ---: | ---: |
| LiveCC | 12.98% | 12.51% | 87.71% |
| MOSS-VL | 8.05% | 7.50% | 100.00% |
| AURA | 7.92% | 7.39% | 99.26% |
| MOSS-Preview | 4.45% | 4.31% | 100.00% |
| ThinkStream | 0.52% | 0.34% | 100.00% |
| VideoLLM-Online | 0.18% | 0.15% | 100.00% |

“Autonomous” describes output triggering, not proof of native visual state.
AURA's incremental-state boundary in Proactive remains unverified; its QA
configuration is non-native.

### End-to-end autonomous system

| System | SWA | TCR@5s | Record completion |
| --- | ---: | ---: | ---: |
| JoyAI | 17.08% | 15.18% | 95.58% |

JoyAI includes memory and scheduling components; its model-level incremental
state remains unverified.

### Non-native polling baseline

| Model | SWA | TCR@5s | Record completion |
| --- | ---: | ---: | ---: |
| MiniCPM-O (polling) | 40.91% | 26.97% | 95.33% |

![Proactive window score, completion and timely-correct curves](assets/results/fig_proactive_quality_w5.png)

Error bars are video-clustered 95% bootstrap intervals; overlapping intervals do
not establish a ranking. Background shading separates system and polling groups.
MOSS hatching preserves a recorded service label, not a different judge model.
MiniCPM-O in these figures is the polling configuration.

![Proactive quality versus outside-window and redundant responses](assets/results/fig_proactive_quality_behavior.png)

The two axes count different behaviors per 100 target windows: output outside
valid windows and redundant output inside windows. Counts can exceed 100 and are
not probabilities or general false-positive rates on no-trigger videos.

## Interpreting and reproducing results

The report evaluates specific model, adapter and system configurations. Some runs
used longer execution tolerances before common W=5 rescoring, so the same scoring
population does not imply identical executed input budgets. ThinkStream's tested
configuration has an end-block commit limitation; JoyAI reflects its tested
configuration rather than a new full-configuration inference run. MiniCPM-O native
duplex has incomplete semantic judging and is excluded from these point tables.

The sufficient-clue breakdown contains 48 windows from only 10 videos, compared
with 319 action-completion windows. Judge calibration is preliminary: 30/36 binary
agreements in a stratified sample, not a population-wide reliability guarantee.
The judge cannot verify visual grounding from text alone.

Use the [evaluation protocol](evaluation-protocol.md) and
[scoring documentation](scoring-and-results.md) for new runs. Match population,
parser, response window, triggering mode and measurement boundary before comparing
against this snapshot. Report-only Recoverable Accuracy, TCR curves and behavior
reconstruction are analysis outputs, not a promise of identical default CLI fields.
Raw experiment bundles and the full report analysis pipeline are not distributed
with this summary. Available public integrations are listed in
[examples and support status](../examples/README.md).
