# Changelog

English | [简体中文](CHANGELOG.zh-CN.md)

## Unreleased

- Renamed the project to TRACE (repository `om-ai-lab/trace-bench`). The Python
  package is now `trace_bench` and the console command is `trace`; the previous
  `osb` command is kept as a compatibility alias.
- Judge settings read `TRACE_VLM_JUDGE_*` environment variables first and fall
  back to the previous `OSB_VLM_JUDGE_*` names.
- Protocol, contract, scorer and schema identities such as `osb-contract-v4`
  and `osb-scoring-v6` are unchanged, so existing Run Bundles remain valid.

## 0.1.0

- Local QA/Proactive Core with OpenCV RGB sampling and an external adapter interface.
- LiveCC walkthrough and experimental ThinkStream integration.
- Raw event bundles, checkpoint/resume, integrity validation and offline rescoring.
- Exact/configurable semantic judging and quality, timing and workload reports.
- English and Chinese setup, adapter and protocol documentation.
- Synthetic smoke verifies correct answers before and after rescoring.
- Source distributions include test helpers and are tested after extraction.
- Annotation v1.1.0 remains independent; its provisional status reflects the
  unresolved OVO-Bench annotation terms. StreamingBench authors have permitted
  redistribution of the modified annotation files; StreamingBench-derived TRACE additions are
  offered under CC BY-NC-SA 4.0 within the rights held by TRACE contributors.
  Annotation content is unchanged.

Execution contract `osb-contract-v4` and scorer `osb-scoring-v6` retain their
compatibility identities. Software 0.1.0 does not change scoring rules.
