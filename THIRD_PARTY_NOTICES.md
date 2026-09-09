# Third-party notices

English | [简体中文](THIRD_PARTY_NOTICES.zh-CN.md)

MIT covers OSB-owned software. External code, model weights and source data
retain their own licenses. Install model runtimes separately and consult their
current license/model cards before use.

| Component | Source / terms |
| --- | --- |
| StreamingBench | [Source](https://github.com/THUNLP-MT/StreamingBench); code MIT |
| OVO-Bench | [Source](https://github.com/joeleelyf/ovo-bench); code MIT |
| LiveCC | [Source](https://github.com/showlab/livecc); check upstream code/runtime and checkpoint licenses |
| ThinkStream | [Source](https://github.com/CASIA-IVA-Lab/ThinkStream); code MIT, base weights have separate terms |
| NumPy | BSD-3-Clause |
| opencv-python-headless | Wrapper MIT; OpenCV Apache-2.0; binary components carry additional notices |
| Pydantic, pytest, build, Ruff | MIT |

Retain notices included with installed dependencies. This list does not replace
the licenses of every component in a user's GPU environment.
Data permissions and the OVO license discrepancy are described in
[data terms](DATA_TERMS.md).

Cite OSB and the source benchmark papers:

- Lin et al., [StreamingBench: Assessing the Gap for MLLMs to Achieve Streaming
  Video Understanding](https://arxiv.org/abs/2411.03628).
- Li et al., [OVO-Bench: How Far is Your Video-LLMs from Real-World Online Video
  Understanding?](https://arxiv.org/abs/2501.05510).

Model references indicate compatibility, not author endorsement.
