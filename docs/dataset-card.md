# Open Stream Bench v1.1.0 dataset card

Visual-only timestamped multiple-choice QA and Proactive Response annotations,
derived from StreamingBench and OVO-Bench with reviewed temporal corrections.
The release contains 833 QA records and 415 Proactive records (1,338 windows).
Tiny contains 9 QA and 9 Proactive records and is a setup check, not a ranking.

The standard Proactive subset contains 407 records / 1,270 windows; the
high-frequency sampling-stress subset contains 8 records / 68 windows.
`--subset full` loads all 415 Proactive records. It does not automatically apply
the report's standard-subset filter. Data version v1.1.0 is independent of
Core package 0.0.0 and scorer osb-scoring-v6.

525 included records were human-reviewed; 723 passed model-assisted no-issue
screening without individual human review. Do not describe all records as
human-validated. Source-video dependencies and public GT limit claims about
unseen-data generalization. Results can depend on sampling and model preprocessing.

`qa.jsonl` and `proactive.jsonl` are canonical. Tiny/subset ID files define
populations; `proactive_standard.jsonl` and `proactive_high_frequency.jsonl`
are same-version derived subsets, not separate data versions. The sampling-stress
split is frozen in `proactive_subsets.json`; do not selectively remove windows
after inspecting a model's errors.

`manifest.json` records schema, source identities, hashes, counts and limitations.
`changes.jsonl`, `exclusions.jsonl`, `review_summary.json`, and
`validation_report.json` are annotation audit/provenance sidecars for this same
release. They are not runtime predictions or older releases. Retain them with
their existing hashes; changes to published annotations need a new release.

Record timestamps refer to the original video. QA uses question, options,
answer, question time, and evidence anchor. Proactive uses instruction time,
trigger/state annotations and expected answers. Legacy `deadline_s` is
provenance, not a video cutoff. Runtime window rules are defined by the
[evaluation protocol](evaluation-protocol.md).

No videos or model weights are included. See [setup](data-setup.md) and
[data terms](../DATA_TERMS.md). Upstream annotation permissions remain pending;
the local snapshot is prepared for publication, not proof of redistribution rights.
