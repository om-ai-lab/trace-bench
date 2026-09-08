# Changelog

## Unreleased — public repository preparation

- Add equivalent English/Chinese READMEs and an executable synthetic CLI flow
  for both tasks, bundle validation and rescoring; CI runs the same flow.
- Validate LiveCC as the first model walkthrough; defer ThinkStream launch
  material while preserving local files and existing Python adapter imports.
- Record declared classification provenance and pacing; eligibility policy v2
  marks explicitly logical runs diagnostic without changing quality scores.
- Preserve the original fatal run error when checkpoint or adapter cleanup
  also fails. Keep source data hashes unchanged.
- Correct video-root priority and document explicit judge model/URL overrides
  when rescoring existing bundles.

- Keep only annotation release v1.1.0; master follows latest, version branches
  preserve snapshots. Annotation and audit hashes remain unchanged.
- Add upstream video setup, adapter tutorial, model configs, dataset card,
  scoring/resume guidance, third-party notices, and contributor instructions.
- Package the current preset and retain stable adapter imports.
- Keep model results outside the checkout; CI scans annotation files too.
- Specify CC BY-NC-SA 4.0 for contributor-owned new annotations, subject to
  unresolved upstream rights. MIT applies to OSB-owned code.

## 0.0.0

- Initial private, runnable development Core.
- The public repository data target is now the single v1.1.0 release; earlier
  data snapshots are not shipped.
- OSB code is released under MIT. Data and upstream asset terms are documented
  separately in `DATA_TERMS.md`.
- The initial v0 data snapshot and protocol were provisional; see the current
  evaluation protocol and release manifest for subsequent identities.
- Added response-episode assembly for proactive delta/snapshot events.
- Added configurable exact/VLM judging for proactive scoring and offline
  rescoring sidecars; private judge endpoints and keys remain external.
- Proactive scoring now uses versioned 5s/10s half-open point windows,
  separates strict-all, strict-observable, and post-trigger eventual views,
  and stops evidence at the last strict-window end instead of a legacy
  `deadline_s` or the source-video tail.
- Upgraded the public execution contract to v4 and scorer to v5: Proactive
  history is independent from response tolerance, same-timestamp polling sees
  the legal frame first, and QA TTFT uses one Core semantic query-arrival clock.
- Added conservative Core-receipt timing for autonomous answers without an
  observable first token, while keeping official first-token eligibility
  incomplete.
- Added official-result eligibility reasons, authoritative `events.jsonl`
  validation, unique-label QA parsing, per-view judge coverage, and corrected
  dropped-frame and GPU-attribution aggregation.
- Proactive latency telemetry is now aggregated over answered strict
  `in_window` response windows, not every answer episode. Window-outside and
  redundant responses remain quality/intrusion metrics and do not enter the
  latency population; windows without a causal trigger-to-response interval
  remain missing and keep official latency eligibility incomplete.
