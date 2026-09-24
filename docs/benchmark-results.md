# Benchmark results and findings

English | [简体中文](benchmark-results.zh-CN.md)

Explore these results with the [interactive scorecard and plots](results-explorer.md).
The numerical source for the public tables and explorers is the versioned
[paper result snapshot](results/data/paper-results.json).

This page follows the active TRACE LaTeX report. It describes retained v1.0.0
inference bundles analyzed on the v1.1.0 standard population; it is not a fresh
inference rerun. The eight rows below are declared configurations, not a single
cross-boundary leaderboard.

## Tasks, populations and execution conditions

| Task | What the model must do | Report population |
| --- | --- | --- |
| Timestamped QA | Answer a question arriving at a specified time using the legal video history | 833 records / 340 videos |
| Proactive Response | Receive one monitoring instruction, observe subsequent evidence, and decide when to respond | 407 standard records / 178 videos / 1,270 windows |

Core supplies causal RGB observations at 1 FPS with wall-clock pacing.
Point triggers distinguish event onset, action completion and sufficient clues;
states use annotated intervals. Failures remain in score denominators.
Proactive results use W=5s scoring, with half-open boundaries, earlier next-trigger
limits and unchanged state intervals.

The released full population contains 1,248 records / 522 videos, including 415
Proactive records and 1,338 windows. Eight sampling-stress records contribute 68
windows, 25 of them at most one second. `--subset full` includes these records;
the paper standard population does not. Canonical release files and hashes are
unchanged. See [release fields and subsets](../data/releases/README.md).

**Table: Per-model configurations and result boundaries.** The columns and row
order follow the paper's `tab:configurations`; all standard Proactive tracks
receive one monitoring instruction and self-initiate their responses.

| Model/system | State and input organization | Proactive trigger | Deployment and evaluation boundary |
| --- | --- | --- | --- |
| AURA | QA: Non-native prefix processing at query time; Proactive: persistent history with incremental visual-state updates | Autonomous | Local service; model + Adapter |
| MOSS-VL | Native; real-time session and asynchronous frame queue | Autonomous | Local weights; model + Adapter |
| MOSS-Preview | Native; real-time session and asynchronous frame queue | Autonomous | Local weights; model + Adapter |
| LiveCC | Native; persistent session and streaming generation | Autonomous | Local weights; model + Adapter |
| ThinkStream | Native; two-frame blocks and persistent state | Autonomous | Local weights; model + Adapter |
| VideoLLM-Online | Native; per-frame visual representations and persistent key-value (KV) state | Autonomous | Local weights; model + Adapter |
| MiniCPM-O (native duplex) | Native; per-frame input and persistent duplex state | Autonomous | Local weights; model + Adapter diagnostic |
| JoyAI | Current segments and external summary memory; model-level incremental state unverified | Autonomous | Local multiple services; end-to-end system |

Polling remains a supported runtime mode and historical baseline, but it is not
part of the paper's primary cohort. The old MiniCPM-O polling scores are not
renamed as native duplex results.

## What the benchmark reveals

- Similar QA scores can hide different execution profiles: LiveCC and
  MOSS-Preview are near 65% accuracy, but their completion, response-latency and
  observed token profiles differ.
- Similar Proactive quality can hide different response-selection behavior:
  MOSS-VL and AURA score 8.05% and 7.92% In-window Accuracy, while MOSS-VL has
  lower False-alarm Rate (41.1% versus 59.1%) and a shorter observed median delay.
- JoyAI's 17.08% In-window Accuracy is measured at an end-to-end system boundary;
  its memory and scheduling components are part of the evaluated system.
- MiniCPM-O native duplex is a diagnostic interface condition: its QA accuracy is
  2.40% with 93.52% invalid output, and its Proactive accuracy is 0.51% with
  24.6% delay-onset coverage. It is not inherited from the historical polling run.

These observations support reporting quality, timeliness, response-selection
behavior, workload and execution reliability separately.

## QA results

QA **Recoverable Accuracy** accepts one unambiguous explicit option label,
including an answer introduction or label-prefixed option text. Hidden thinking
is removed before parsing. Two distinct labels, unlabeled prose and ordinary
articles are invalid. This report metric is separate from the software default
strict parser; the paper-compatible scoring profile exposes that distinction.

Response Latency is measured from question arrival at the Evaluation Core to
completion received. It includes required query-time history processing,
preparation, queueing and generation. It is not TTFT. Submitted images and
output tokens are observed workload totals under each configuration's boundary.

**Table: QA results by execution condition.** Latency is the median Response
Latency in milliseconds; output tokens are observed run totals over the scheduled
population and are not normalized by completion. The group labels follow the
paper's `tab:qa_results`.

| Configuration | Accuracy | Completion | Response latency, median (ms) | Submitted images | Recorded output tokens | Invalid output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **(a) Native models with Adapters** |  |  |  |  |  |  |
| LiveCC | 65.19% | 93.88% | 165.2 | 21,917 | 146,064 | 6.12% |
| MOSS-Preview | 65.07% | 100.00% | 138.1 | 30,835 | 42,206 | 1.92% |
| MOSS-VL | 75.03% | 99.88% | 374.6 | 30,835 | 39,768 | 0.84% |
| ThinkStream | 61.46% | 100.00% | 411.0 | 30,835 | 349,476 | 0.00% |
| VideoLLM-Online | 2.64% | 100.00% | 681.1 | 30,835 | 39,047 | 95.32% |
| MiniCPM-O (native duplex) | 2.40% | 100.00% | 489.5 | 30,835 | 24,591 | 93.52% |
| **(b) End-to-end system** |  |  |  |  |  |  |
| JoyAI | 67.47% | 91.36% | 876.1 | 17,235 | 2,286 | 8.52% |
| **(c) Non-native prefix-input** |  |  |  |  |  |  |
| AURA | 73.83% | 99.88% | 819.7 | 31,170 | 2,469 | 0.60% |

![QA accuracy, response latency and generation workload](assets/results/fig_qa_accuracy_workload.png)

Output-token totals include recorded history, reasoning, control text and
answers. Different vocabularies and incomplete telemetry prevent interpreting
them as a common compute or monetary cost. The supplementary native-duplex
Proactive completion field is unavailable and remains missing.

## Proactive results

**In-window Accuracy** averages content credit over all 1,270 target windows,
including misses and failures. **Median Response Delay** is conditional on
answered windows with an observed first-token onset. The snapshot reports the
observed-onset and answered counts for coverage. **False-alarm Rate** is a global
response-episode ratio: an episode beginning outside every currently valid
window enters the numerator only if a later valid window remains, and final-tail
episodes do not. **Miss Rate** is a target-window ratio: no assigned response is
a miss; an incorrect assigned response is not.

**Table: Proactive results by response track.** In-window Accuracy and Miss are
window-level; False-alarm Rate is a global response-episode ratio; Median
Response Delay is conditional on answered windows with an observed onset. The
group labels follow the paper's `tab:proactive_results`.

| Configuration | In-window Accuracy | Median delay (s) | False-alarm Rate | Miss Rate | Submitted images | Output tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **(a) Autonomous model + Adapter** |  |  |  |  |  |  |
| LiveCC | 12.98% | 1.08 | 65.0% | 0.31% | 23,243 | 78,478 |
| AURA | 7.92% | 1.15 | 59.1% | 47.64% | 439,400 | 50,957 |
| MOSS-VL | 8.05% | 0.33 | 41.1% | 47.24% | 34,520* | 74,672 |
| MOSS-Preview | 4.45% | 0.20 | 77.7% | 35.67% | 34,520* | 193,517 |
| ThinkStream | 0.52% | 2.14 | 73.6% | 68.43% | 32,783 | 373,897 |
| VideoLLM-Online | 0.18% | 0.20 | 82.4% | 60.39% | 32,783 | 42,162 |
| MiniCPM-O (native duplex) | 0.51% | 1.24 | 80.3% | 65.43% | 32,617 | 23,636 |
| **(b) End-to-end system** |  |  |  |  |  |  |
| JoyAI | 17.08% | 1.12 | 50.5% | 32.13% | 313,658 | 797,954 |

![Proactive quality versus response delay](assets/results/fig_proactive_quality_delay.png)

![Proactive False-alarm Rate versus Miss Rate](assets/results/fig_proactive_fa_miss.png)

`*` MOSS submitted-image values use 34,520 unique frames because repeated queue
occurrences were not retained. Unique-frame and coverage details are preserved
in the public snapshot. Repeated in-window responses are supplementary descriptive
behavior and are not subtracted from In-window Accuracy.

The paper also reports a trigger-type breakdown for seven standard response
tracks. The native duplex diagnostic has no matching retained trigger breakdown;
it remains missing rather than being inferred. Trigger subsets share videos and
have different sizes, so they are descriptive rather than controlled difficulty
groups.

## Interpreting and reproducing results

The report evaluates specific model, adapter and system configurations. Some runs
used longer execution tolerances before common W=5 rescoring, so the same scoring
population does not imply identical executed input budgets. ThinkStream's tested
configuration has an end-block commit limitation; JoyAI reflects its tested
configuration rather than a new full-configuration inference run. MiniCPM-O native
duplex is a diagnostic row with qualified timing coverage; unavailable supplementary
fields remain missing.

The sufficient-clue breakdown contains 48 windows from only 10 videos, compared
with 319 action-completion windows. Judge calibration is preliminary: 30/36 binary
agreements in a stratified sample, not a population-wide reliability guarantee.
The judge cannot verify visual grounding from text alone.

Use the [evaluation protocol](evaluation-protocol.md) and
[scoring documentation](scoring-and-results.md) for new runs. Match population,
parser, response window, triggering mode and measurement boundary before comparing
against this snapshot. Report-only Recoverable Accuracy, response-selection metrics
and behavior reconstruction are analysis outputs, not a promise of identical
legacy CLI fields.
Raw experiment bundles and the full report analysis pipeline are not distributed
with this summary. Available public integrations are listed in
[examples and support status](../examples/README.md).
