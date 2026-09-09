# Versions and releases

English | [简体中文](releasing.zh-CN.md)

Software 0.1.0 and annotation v1.1.0 are independent releases.
`main` follows current development. A data-version branch such as `v1.1.0`
preserves a selected snapshot and does not automatically follow main.
Use software tags such as `v0.1.0`; do not reuse a data branch name as a tag.

README exposes software and data versions. Run Bundles additionally record
execution contract `osb-contract-v4`, scorer `osb-scoring-v6` and schema
identities for reproducibility. These are compatibility identifiers, not
separate packages. A documentation or packaging fix does not change scoring
identity; a scoring-rule change must. Do not relabel historical bundles.

The v1.1.0 manifest status is provisional pending the permissions described in
[data terms](../DATA_TERMS.md). Source paths are descriptive provenance IDs.
This metadata correction does not alter annotations, answers or their hashes;
it does change the manifest identity and new-run eligibility. Old bundles
retain their original manifest. Use a new output directory with revised metadata.

## Before publishing

Run README's tests, smoke answer checks, documentation and public-file scans,
and distribution checks. Review the diff, data permissions, packaged files and
any claimed GPU/judge validation. See [validation](release-validation.md).
Do not publish videos, weights, output bundles or local configuration.
Keep only the selected annotation version in Git; retain older local files
through ignore rules rather than deleting them.
