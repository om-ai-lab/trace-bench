# Release files and field reference

English | [简体中文](README.zh-CN.md)

This reference describes the shipped [v1.1.0](v1.1.0/manifest.json) annotation snapshot.
Data and software versions are independent. For video downloads, see
[data setup](../../docs/data-setup.md); for licensing, see [data terms](../../DATA_TERMS.md).
The StreamingBench authors have permitted redistribution of the modified
annotation files included here. StreamingBench-derived TRACE additions are offered under
CC BY-NC-SA 4.0 within the rights held by TRACE contributors. This does not
license original videos or upstream source fields; OVO-Bench annotation terms
remain unresolved.

## File inventory

Paths below are relative to `v1.1.0/`. JSONL contains one JSON object per line;
ID files contain a JSON array of `record_id` strings.

| File | Contents |
| --- | --- |
| `manifest.json` | Release identity, canonical file names, counts and SHA-256 hashes |
| `qa.jsonl` | 833 canonical QA records |
| `proactive.jsonl` | 415 canonical Proactive records, 1,338 response windows |
| `tiny_qa_ids.json` | 9 QA IDs for setup checks |
| `tiny_proactive_ids.json` | 9 Proactive IDs for setup checks |
| `standard_proactive_ids.json` | 407 standard-subset IDs |
| `high_frequency_proactive_ids.json` | 8 sampling-stress-subset IDs |
| `proactive_standard.jsonl` | Complete canonical rows for the standard subset: 1,270 windows |
| `proactive_high_frequency.jsonl` | Complete canonical rows for the stress subset: 68 windows |
| `proactive_subsets.json` | Subset criterion, counts, hashes and partition checks |
| `changes.jsonl` | 380 review change/removal records |
| `exclusions.jsonl` | 52 excluded source records and reason codes |
| `review_summary.json` | Review coverage and disposition counts |
| `validation_report.json` | Validation results recorded when building the snapshot |

`--subset full` reads the canonical files, including sampling stress; it does not
automatically select the standard subset. `--subset tiny` selects the manifest's
tiny IDs. Keep all snapshot files: release validation checks the manifest hashes,
including audit and derived files.

## Shared conventions

Times and durations are in seconds. Timestamps use the original video's time
coordinates, not elapsed inference time. Intervals are half-open `[start_s, end_s)`.
`video_path` is relative to the video root supplied to TRACE. Videos and model weights
are not included.

The tables describe fields present in v1.1.0; “optional” means a field may be absent.
The loader also allows `memory_length` and legacy `deadline_s` to be null.
Ground-truth answers and review metadata are scoring/audit information, not model input.

| Shared QA / Proactive field | Type | Meaning |
| --- | --- | --- |
| `record_id` | string | Unique canonical record ID; used by subset files and result records |
| `source_id` | string | Source identity; equals `record_id` in this snapshot |
| `task` | string | `qa` or `proactive` |
| `task_type` | string | Task category inherited from the source benchmark |
| `video_path` | string | Relative source-video path |
| `memory_length` | number / null | Derived annotation duration, as defined below; not a runtime cutoff |
| `metadata` | object | Provenance, review and temporal annotations |

## QA records

| Field | Type | Meaning |
| --- | --- | --- |
| `question` | string | Question text |
| `options` | array of strings | Ordered answer options, including their labels |
| `answer` | string | Ground-truth option label |
| `question_time_s` | number | Video time at which the question is submitted |
| `evidence_anchor_s` | number | Evidence anchor used to construct the history prefix |
| `memory_length` | number / null | In v1.1.0, `question_time_s - evidence_anchor_s` |

With the default `qa_window_s=10`, Core samples from
`max(0, evidence_anchor_s - 10)` through `question_time_s`.
Thus `memory_length` is not the total sampled-prefix duration, and the anchor is
not necessarily the start of an evidence span. See the [evaluation protocol](../../docs/evaluation-protocol.md).

## Proactive records

| Field | Type | Meaning |
| --- | --- | --- |
| `instruction` | string | Monitoring instruction |
| `instruction_time_s` | number | Video time at which monitoring is instructed |
| `deadline_s` | number / null | Legacy annotation horizon retained for provenance; never the current inference cutoff |
| `windows` | array of objects | Stored response windows |
| `windows[].start_s`, `windows[].end_s` | number | Stored window boundaries |
| `windows[].expected_answer` | string | Ground-truth response for that window |
| `memory_length` | number / null | In v1.1.0, legacy `deadline_s - instruction_time_s` |

Stored point windows reflect the snapshot's 5-second policy. The evaluation
protocol/configuration determines the effective 5- or 10-second windows; point
windows stop at the next trigger if earlier. State intervals retain their annotated
boundaries. Evidence spans do not define response tolerance.
Legacy duration fields do not require processing the full video.
Evidence delivery and output draining follow the
[evaluation protocol](../../docs/evaluation-protocol.md), not `deadline_s`.

## Metadata

| Field inside `metadata` | Type / scope | Meaning |
| --- | --- | --- |
| `dataset` | string / both | `ovo_bench` or `streambench` (StreamingBench) |
| `stable_id` | string / both | Stable audit identity; distinct format from canonical `record_id` |
| `source_file` | string / both | Source annotation filename for provenance |
| `source_question_id` | string / both | Question ID in the source annotations |
| `required_ability` | string / both | Source ability description; may be empty |
| `validation_tier` | string / both | `human_reviewed` or `machine_screened` |
| `machine_risk_level` | string / both | Historical machine-screening result, not the final validity decision |
| `retention_gap_s` | number / both | Derived duration; equals this snapshot's `memory_length` |
| `source_memory_length_s` | number / both | Original source duration |
| `source_memory_length_discrepancy_s` | number / both | Source duration minus derived duration |
| `evidence_spans` | array / QA, optional | Review evidence; each object has `start_s`, `end_s` (numbers) and `description` (string) |
| `video_categories` | string / Proactive | Source video category; may be empty |
| `first_trigger_lead_s` | number / Proactive | Earliest trigger time minus instruction time |
| `monitoring_horizon_s` | number / Proactive | Legacy `deadline_s - instruction_time_s`; descriptive only |
| `point_response_tolerance_s` | number / Proactive | Snapshot point tolerance (5); does not override evaluation configuration |
| `trigger_annotations` | array / Proactive | Event/state annotations aligned by index with `windows` |
| `media_boundary_adjustments` | array / both, optional | Timestamp corrections to readable media boundaries |

Each `media_boundary_adjustments` object contains `field` (string),
`source_value_s` and `effective_value_s` (numbers), and `reason` (string).
A retained `machine_risk_level` such as `blocking` may precede a human correction;
do not use it alone to exclude a released record.

### Proactive trigger annotations

| Field inside `trigger_annotations[]` | Type | Meaning |
| --- | --- | --- |
| `event_id` | string | Event identity within the record |
| `answer` | string | Expected answer |
| `annotation_source` | string | Origin of the trigger annotation, e.g. human review or inferred task policy |
| `trigger_type` | string | `event_onset`, `event_completion`, `clue_sufficient`, or `state_interval` |
| `point_trigger_s` | number / null | Point trigger time; null for state intervals |
| `interval_start_s`, `interval_end_s` | number / null | State interval boundaries; null when not applicable |
| `response_policy` | string | Snapshot policy label, e.g. `up_to_5s_until_next_trigger` or `reviewed_state_interval` |
| `response_window_start_s`, `response_window_end_s` | number | Snapshot response-window boundaries |
| `source_window_start_s`, `source_window_end_s` | number, optional | Original window boundaries before correction |
| `accepted_facts` | array of strings, optional | Alternative acceptable factual descriptions |
| `evidence_description` | string, optional | Review explanation of visual evidence |
| `evidence_start_s`, `evidence_end_s` | number, optional | Evidence segment for review |

`event_onset` means the condition first holds; `event_completion` means the action
is complete; `clue_sufficient` means evidence first suffices to determine the answer;
`state_interval` describes when a state holds. These describe visual facts, not
model latency allowances.

## Manifest

| Field | Meaning |
| --- | --- |
| `release_id`, `schema_version` | Data release identifier and schema identifier (strings) |
| `status` | Release status; this combined snapshot is `private_provisional` because OVO-Bench annotation terms remain unresolved. StreamingBench modified annotations have author redistribution permission; see data terms |
| `qa_file`, `proactive_file` | Canonical JSONL filenames |
| `tiny_qa_ids_file`, `tiny_proactive_ids_file` | Tiny ID filenames |
| `counts` | Object mapping population names to integer counts |
| `source_files` | Array of source fingerprints: `path` (provenance identifier) and `sha256` |
| `files` | Object mapping 13 snapshot filenames to SHA-256 strings; excludes the manifest itself |
| `video_root_notes` | Video-root setup note (string) |
| `limitations` | Array of release limitation strings |

Source fingerprint paths are provenance identifiers, not files users must download
at those paths. Status is separate from the build validation result.

## Proactive subset descriptor

`proactive_subsets.json` uses these fields:

| Field | Meaning |
| --- | --- |
| `schema_version`, `source_file` | Descriptor schema and canonical source filename |
| `source.record_count`, `source.window_count` | Total source records and windows |
| `criterion.name`, `criterion.reason` | Criterion identifier and explanation |
| `criterion.scope` | `record`: retain all windows of each selected record |
| `criterion.window_duration` | Formula `end_s - start_s` |
| `criterion.threshold_s`, `criterion.inclusive` | Threshold 1.0 second, inclusive |
| `subsets.standard`, `subsets.high_frequency` | Each contains `ids_file`, `record_file`, `record_count`, `window_count`, `qualifying_window_count` |
| `hashes` | SHA-256 strings keyed by `source_file`, `standard_ids_file`, `standard_record_file`, `high_frequency_ids_file`, `high_frequency_record_file` |
| `checks` | Boolean checks: `full_records_preserved`, `record_ids_disjoint`, `record_ids_union_equals_source`, `record_order_sorted_by_record_id` |

A record enters sampling stress if any stored window lasts at most 1 second.
The 8 selected records have 68 windows, of which 25 meet that criterion.
This split uses snapshot windows; it is not recomputed from run FPS or tolerance.
A short window is not automatically unobservable: sampling phase also matters.

## Review and validation sidecars

These files summarize changes and coverage, not a complete annotation audit package
with prompts, sampling scripts or full reviewer conversations.

### Changes and exclusions

Both JSONL files include `record_id`, `stable_id`, `dataset`, `mode` (QA/Proactive)
and `task_type`, all strings.

| Additional field | Meaning |
| --- | --- |
| `changes.jsonl: disposition` | Review action |
| `changes.jsonl: issue_codes` | Array of recorded issue-code strings |
| `changes.jsonl: changes` | Array of `field` (source field path), `old_value`, `new_value` objects |
| `exclusions.jsonl: reason_codes` | Array of exclusion-reason strings |

Old/new values preserve their source JSON types, including null and nested objects;
field paths need not match canonical record paths. Historical trigger payloads can
also contain `observed_onset_s`, `observed_completion_s`, `monitoring_horizon_s`,
`response_tolerance_s`, `tolerance_before_s`, and `tolerance_after_s`, alongside
the event, answer and evidence fields above. These retain historical annotation
values, not current scoring settings. There are 328 edited and 52 removed records
in the 380 change records; exclusions are not additional removals.

### Review summary

| Field in `review_summary.json` | Meaning |
| --- | --- |
| `release_id` | Data release identifier |
| `source_record_count`, `included_record_count`, `excluded_record_count` | 1,300 input, 1,248 retained, 52 excluded |
| `saved_review_count`, `unresolved_saved_reviews` | 577 saved reviews; 0 unresolved saved reviews |
| `review_dispositions` | Counts by action: `edit` 328, `remove` 52, `valid` 197 |
| `validation_tiers` | Retained records: `human_reviewed` 525, `machine_screened` 723 |
| `pending_machine_screened_count` | Historical name for the 723 retained records without individual human review |
| `included_by_dataset_mode`, `included_by_task_type` | Objects mapping source/task categories to retained counts |
| `duplicate_policy` | Rule retaining the smaller stable ID |
| `duplicate_upper_id_removals` | 25 duplicate removals, already included in the 52 exclusions |

### Validation report

`validation_report.json` contains `release_id`, `status` (build result),
`counts` (integer counts for `qa`, `proactive`, `included`, `excluded`, `changes`)
and `checks` (named booleans):

| Check | Meaning |
| --- | --- |
| `all_saved_reviews_completed` | Saved reviews were resolved |
| `all_unreviewed_records_machine_completed_no_issue` | Records without individual review passed machine screening |
| `answers_match_options` | QA answers match available option labels |
| `canonical_content_unique`, `canonical_record_ids_unique` | Canonical content and IDs are unique |
| `duplicate_upper_ids_removed` | Duplicate policy was applied |
| `media_boundaries_within_last_readable_frame` | Checked timestamps fit readable media boundaries |
| `proactive_instruction_before_trigger` | Instructions precede triggers |
| `proactive_positive_windows`, `proactive_windows_non_overlapping` | Stored windows have positive duration and do not overlap |
| `qa_evidence_not_after_question` | Evidence anchors do not follow questions |
| `reviewed_memory_intervals_derived` | Reviewed duration fields were derived |
| `source_lineage_matches_audit_manifest` | Source fingerprints match the audit manifest |
| `streambench_proactive_128_matches_upstream` | Specific source-record consistency check |

These are saved build-time checks, not a fresh validation of your local media or a
license grant. Use `trace data validate --release data/releases/v1.1.0` from the
repository root to validate the installed snapshot's schema and hashes.
