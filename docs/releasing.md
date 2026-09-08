# Repository and release policy

`master` contains the latest reviewed release. A version branch such as
`v1.1.0` preserves its corresponding code and annotation snapshot. Each branch
contains exactly one populated directory under `data/releases/`. Data subset
and audit files inside that directory belong to the same release.

The data version is independent of Core package 0.0.0, canonical schema
osb-canonical-v0, protocol/config v4, and scorer osb-scoring-v5. Record all of
these in results. Do not rename protocol identities merely to match branch names.
Use annotated tags with distinct names such as `release-v1.1.0` if tags are
needed; do not create a tag and branch with the same name.

Before publishing: review the staged file list, validate data hashes, run tests
and CI checks, execute the documented tiny flow in the selected GPU model
environment, verify third-party notices and data permission status, and fill
in the repository URL and author citation details when available.

Source-checkout installation is the supported first-release workflow. Data and
documentation stay in the checkout; package installation alone does not download
them. Config defaults are included in the Python package.

Keep videos, weights, local configurations and Run Bundles outside version
control. Future updates replace the one data directory on master and preserve
prior versions on their version branches. Never overwrite historical results
or change frozen annotations while retaining their release identity.
