# Dataset: v1.1.0

English | [简体中文](dataset-card.zh-CN.md)

Visual-only timestamped QA and Proactive Response annotations derived from
StreamingBench and OVO-Bench, with reviewed temporal corrections.

| Population | Size |
| --- | --- |
| QA | 833 records |
| Proactive | 415 records / 1,338 windows |
| Proactive standard | 407 records / 1,270 windows |
| Proactive sampling stress | 8 records / 68 windows |
| Tiny setup subset | 9 QA + 9 Proactive records |

`--subset full` includes sampling stress. Tiny checks setup, not model ranking.
Data and software versions are independent.

## Files and time coordinates

See the [release file and field reference](../data/releases/README.md) for every file and its fields.

`qa.jsonl` and `proactive.jsonl` contain canonical records. ID files define
subsets. `manifest.json` contains hashes and source fingerprints; source paths
are provenance identifiers, not required local files. Audit sidecars document
annotation changes and exclusions.

Timestamps refer to the original video. QA records contain question, options,
answer, question time and evidence anchor. Proactive records contain instruction
time, event/state annotations and answers. Legacy `deadline_s` is provenance,
not a cutoff. See the [protocol](evaluation-protocol.md).

## Limitations and access

525 records were human-reviewed; 723 passed model-assisted screening without
individual human review. Do not describe all records as human-validated.
Dense windows may be unobservable at 1 FPS; report coverage and sampling-stress
results separately. Public GT limits claims about unseen-data generalization.

No videos or weights are included. See [data setup](data-setup.md).
Licensing and pending upstream permissions are centralized in [data terms](../DATA_TERMS.md).
