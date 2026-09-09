# Open Stream Bench

[English](README.md) | 简体中文

用于时间戳视频 QA 和主动响应的本地评估基准。
用户下载源视频，通过 adapter 接入模型，保存原始输出、耗时、失败和分数。
真实模型评估通常需要 GPU；OSB 不提供托管在线评估。

| 内容 | 版本与范围 |
| --- | --- |
| 软件 | `0.1.0` |
| 标注快照 | `data/releases/v1.1.0` |
| 全量数据 | 833 条 QA、415 条 Proactive；1,338 个窗口 |
| Tiny 环境检查子集 | 9 条 QA + 9 条 Proactive |
| 代码 / 数据 | [MIT](LICENSE) / [数据条款](DATA_TERMS.zh-CN.md) |

仓库仅包含 v1.1.0 标注，视频和模型权重需另行下载。
数据范围和限制见[数据卡](docs/dataset-card.zh-CN.md)。

## 安装

已测试 Python 3.10–3.12。克隆或下载[本仓库](https://github.com/om-ai-lab/Open-Stream-Bench)，
进入仓库根目录后执行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
osb --help
osb data validate --release data/releases/v1.1.0
```

请保留源码目录；仅安装 wheel 不包含标注和视频。模型依赖应安装在模型自己的环境中。

## 验证软件流程

以下流程生成合成视频，运行 QA 和 Proactive、校验 bundle、重新算分并检查预期答案。
无需 GPU 或 judge 服务。测试替身故意读取 GT；这是软件测试，不是模型评分。

```bash
set -euo pipefail
python scripts/make_smoke_fixture.py --output output/smoke
osb data validate --release output/smoke/release
for task in qa proactive; do
  osb run --task "$task" --release output/smoke/release --subset tiny \
    --adapter open_stream_bench.adapters:TestDoubleAdapter \
    --video-root output/smoke --output "output/smoke/$task" \
    --synthetic --judge-mode exact --checkpoint-every 5
  osb bundle validate "output/smoke/$task"
  osb score "output/smoke/$task" --judge-mode exact
done
python scripts/check_smoke_results.py --output output/smoke
```

预期两个任务的答案检查通过，QA accuracy 和 Proactive window accuracy 均为 1.0，
无失败，并标记 `synthetic: true` / `official_eligible: false`。
12 秒 fixture 的回答窗口与默认 5 秒 polling 对齐。模型遥测缺失在此测试中属于预期情况。
bundle 有效不等于模型产生了正确回答。

结果保存在被 Git 忽略的 `output/`。生成器拒绝覆盖已有 fixture；
重复验证时将所有 `output/smoke` 一致改为新的路径。不要为了重跑教程删除已有实验结果。

## 评估模型

1. 从 StreamingBench 和 OVO-Bench [准备源视频](docs/data-setup.zh-CN.md)。
2. 按 [LiveCC 教程](docs/livecc-adapter.zh-CN.md)，或实验性
   [ThinkStream 指南](docs/thinkstream-adapter.zh-CN.md)配置模型。
3. 其他模型实现 [adapter 接口](docs/adapter-guide.zh-CN.md)，可放在自己的仓库中。
4. 先跑 tiny，检查预测、失败和遥测，再跑 full。
   语义 judge、重算和续跑见[评分与续跑](docs/scoring-and-results.zh-CN.md)。

Core 使用 OpenCV 以 1 FPS 提供时间戳 RGB uint8 数组。
QA 接收合法历史，跨模型 user 内容一致。
Proactive 使用 5s/10s 事件窗口或标注状态区间，视觉输入在最后严格窗口终点结束，
源视频更短时由其长度限制。
Native/non-native 视觉状态与 autonomous/polling 触发方式是独立比较维度。
详见[评估协议](docs/evaluation-protocol.zh-CN.md)。

## 文档

- [数据及限制](docs/dataset-card.zh-CN.md)
- [示例与支持状态](examples/README.zh-CN.md)
- [发布/版本规则](docs/releasing.zh-CN.md)及[验证](docs/release-validation.zh-CN.md)
- [第三方声明](THIRD_PARTY_NOTICES.zh-CN.md)、[贡献](CONTRIBUTING.zh-CN.md)、
  [安全](SECURITY.md)、[行为准则](CODE_OF_CONDUCT.md)
- [引用](CITATION.cff)及[更新记录](CHANGELOG.zh-CN.md)

## 开发检查

以下 check_docs.py 和 check_public_files.py 两个 Git 检查需要 Git checkout，
并在仓库根目录运行。ZIP 用户仍可安装、评估、运行测试和发行包检查；
需要运行这两个维护检查时请克隆仓库。CI 覆盖 Python 3.10–3.13。

```bash
mkdir -p output
python -m pytest -q --basetemp=output/pytest
ruff check .
python scripts/check_docs.py
python scripts/check_public_files.py
python -m build --outdir output/dist
python scripts/check_distribution.py --dist output/dist --output output/distribution-check
```

重复发行包检查时使用新的构建/检查目录。
CI 验证合成答案和源码包解包后的测试。GPU 推理和在线语义 judge 验证单独执行。
