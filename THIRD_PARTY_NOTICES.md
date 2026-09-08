# Third-party notices

OSB-owned software is MIT licensed. This does not relicense external software,
model weights, datasets or source media. Dependencies are installed separately.

| Component | Source | Terms / status |
| --- | --- | --- |
| StreamingBench | https://github.com/THUNLP-MT/StreamingBench | Code MIT, Copyright (c) 2021 THUNLP; annotation permission pending |
| OVO-Bench | https://github.com/joeleelyf/ovo-bench | Code MIT, Copyright (c) 2024 Junbo Niu; dataset README CC BY-NC-SA 4.0 |
| LiveCC | https://github.com/showlab/livecc | External runtime; livecc-utils and checkpoint cards identify Apache-2.0; root-code scope requires verification |
| ThinkStream | https://github.com/CASIA-IVA-Lab/ThinkStream | Code MIT; Qwen2.5-VL-3B base weights have separate Qwen Research License terms |
| NumPy | https://numpy.org/ | BSD-3-Clause; bundled components have their own notices |
| opencv-python-headless | https://github.com/opencv/opencv-python | Wrapper MIT, OpenCV Apache-2.0; binary distributions include additional notices |
| Pydantic | https://github.com/pydantic/pydantic | MIT |
| pytest | https://github.com/pytest-dev/pytest | MIT, development dependency |
| build | https://github.com/pypa/build | MIT, development dependency |
| Ruff | https://github.com/astral-sh/ruff | MIT, development dependency |

This is a direct-dependency inventory, not a license bill of materials for
every user's GPU environment. Retain the licenses shipped with each installed
distribution. If importing copied upstream code in future, preserve its full
copyright, license and applicable NOTICE alongside the code and record its
source revision; API compatibility does not authorize relicensing copied code.

See [DATA_TERMS.md](DATA_TERMS.md) for the OVO GitHub/Hugging Face discrepancy
and pending StreamingBench permission. OSB includes corrected/derived annotation
fields; such changes do not remove source attribution or ShareAlike obligations.
Model references describe compatibility, not author endorsement.

Please cite the source benchmark papers as well as OSB:

- Lin et al., *StreamingBench: Assessing the Gap for MLLMs to Achieve Streaming
  Video Understanding*, https://arxiv.org/abs/2411.03628.
- Li et al., *OVO-Bench: How Far is Your Video-LLMs from Real-World Online Video
  Understanding?*, https://arxiv.org/abs/2501.05510.
