# Release-candidate validation

Validation date: 2026-09-08. Scope: local Core package 0.0.0, annotation v1.1.0,
protocol v4, quality scorer v6 and eligibility policy v2. This is software and
integration validation, not a leaderboard or a claim of full model conformance.

## Checks performed

- Fresh source snapshot and new Python 3.12 virtual environment: README
  `pip install -e '.[dev]'` succeeded without preinstalled Core dependencies.
- Core environment: 87 tests passed, two model test modules skipped because
  PyTorch is deliberately not a Core dependency.
- Separate model environment with PyTorch: 118 tests passed, including sampler,
  causal boundaries, QA prompt/query timing, Proactive windows and drain,
  failures, checkpoint/resume, rescoring, integrity and both bundled adapters.
- The documented synthetic video generator and both QA/Proactive CLI flows
  executed, including data validation, bundle validation and rescoring. Their
  outputs are synthetic and ineligible. CI now repeats these commands.
- Ruff passes with the explicitly frozen original E4/E7/E9/F baseline.
- Annotation validation passes for all 15 manifest/hashed files. Canonical
  records, GT, subsets and audit hashes were not modified.
- Source distribution and wheel build successfully from the actual publication
  file list. The source distribution includes the Chinese README and only the
  v1.1.0 release; deferred launch material, historical data, weights and runs
  are excluded. The wheel includes the default preset.
- Local Markdown links resolve; all Bash blocks in both READMEs are identical.
- The shipped files pass the private-path/credential-pattern scan.

## Real-model check

The README LiveCC walkthrough uses local LiveCC-7B-Instruct weights, existing
upstream source videos, 1 FPS, logical pacing, W=5, exact diagnostic scoring,
and checkpoints every five records. A separate virtual environment inherits the
existing model runtime and installs the release candidate without modifying
the shared runtime. GPU: NVIDIA A100 80GB.

QA and Proactive are checked on the complete v1.1.0 tiny selection (nine records
each). This verifies real weights and real video decoding, not just preflight
or a fake model. Predictions, raw events, failure status and bundle integrity
are inspected; a CLI exit code alone is not sufficient.

Final outcome: QA **9/9 completed, 0 failures**, 171 raw events; Proactive
**9/9 completed, 0 failures**, 912 raw events. Both bundles validate and rescore
successfully. Their Core/scorer/preflight source hashes match the publication
candidate. Both are explicitly diagnostic under eligibility policy v2.
Record `ovo_bench_proactive:1469` consumes 18 observations over 305–322 seconds,
with evaluation end 322 seconds at W=5; the legacy 347-second deadline is only
provenance and the long source-video tail is not fed to the model.

The run uses the dependency versions listed in [the LiveCC guide](livecc-adapter.md).
It does not reproduce model-environment installation from an empty machine or
redownload the full upstream corpora. Source H.264 decoder warnings may appear;
check whether they lead to failed records before interpreting results.

## Boundaries and publication gates

- The synthetic and logical model checks are diagnostic. Wall-clock timing
  qualification and a live semantic-judge run are not claimed by this check.
  Judge routing/raw-result handling are covered by deterministic transport tests.
- No new model leaderboard is shipped. Native labels are declared capabilities,
  not automatic proof of incremental model state. Model review is still needed
  before publishing an official result, even if automated coverage passes.
- LiveCC is the first walkthrough. ThinkStream launch material is deferred;
  its Python module remains compatible. Other external adapters are not part
  of the public example set.
- Confirm the outstanding upstream annotation redistribution permissions in
  [DATA_TERMS](../DATA_TERMS.md) before public data redistribution.
- Configure the user's remote repository URL and finalize citation metadata
  before pushing. No remote push is part of this local validation.

Keep video files, weights, private runtime paths, full validation bundles and
logs outside the repository. The English and Chinese README commands must stay
equivalent. `master` is latest; a version branch is updated only when the
corresponding snapshot is ready to freeze.
