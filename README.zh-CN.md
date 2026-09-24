<div align="center">

<h1>TRACE</h1>

<h3>Temporal Audit and Condition-aware Evaluation of Streaming Video Understanding</h3>

<p>
  面向时间戳视频问答与主动响应的可复现实验基准，支持本地运行和完整审计。
</p>

<p>
  <a href="https://arxiv.org/abs/2609.00000"><img src="https://img.shields.io/badge/Paper-Coming%20soon-6d28d9?style=flat-square" alt="论文即将发布"></a>
  <a href="https://huggingface.co/datasets/om-ai-lab/trace-bench"><img src="https://img.shields.io/badge/Hugging%20Face-Coming%20soon-f59e0b?style=flat-square" alt="Hugging Face 数据即将发布"></a>
</p>

<p>
  <a href="README.md">English</a> · <a href="docs/results/index.zh-CN.html">项目主页</a>
  · <a href="docs/results-explorer.zh-CN.md">结果看板</a>
  · <a href="docs/evaluation-protocol.zh-CN.md">评估协议</a>
  · <a href="docs/dataset-card.zh-CN.md">数据卡</a>
</p>

</div>

## TRACE 如何工作

TRACE 将因果视频历史、Adapter 执行、模型或系统响应、遥测和评分连接在同一套
可审计流程中。

<p align="center">
  <img src="docs/assets/results/evaluation-design-report.en.png" alt="TRACE 评估设计：因果输入、Core、Adapter、模型或系统与评分" width="100%">
</p>

<p align="center"><em>TRACE 评估设计：Core → Adapter → 模型/系统 → 评分，以及 QA 与 Proactive 的时间线。</em></p>

### TRACE 关注什么

| | TRACE 明确记录的内容 |
| --- | --- |
| **时间审计** | 时间戳 RGB 观测、合法历史、响应窗口和停止边界随输出一起保留。 |
| **受控执行** | Core 与 Adapter 将基准计时和模型接口分开，原生与非原生接入都能在清晰的边界上比较。 |
| **条件感知报告** | 按执行条件同时报告质量、延迟、误报、漏报和工作量。 |

## 执行条件

执行条件分别描述视觉状态、响应触发和评估边界。它们是比较维度，不代表能力等级。

<p align="center">
  <img src="docs/assets/results/execution-modes-report.en.png" alt="TRACE 执行模式：视觉状态、响应触发与评估边界" width="100%">
</p>

<p align="center"><em>执行模式：原生与前缀输入视觉状态、自主与 polling 响应触发，以及模型/Adapter 与完整系统边界。</em></p>

## 任务、数据与协议

TRACE 评估两种互补行为：

| 任务 | 模型输入与测量指标 |
| --- | --- |
| **QA** | 在指定时间收到问题，只能看到合法的视频历史；使用 Recoverable Accuracy、完成率、响应延迟和输出有效性评分。 |
| **Proactive** | 在事件前收到监测指令，需要决定说什么以及何时说；报告窗口内准确率、观测中位延迟、误报率和漏报率。 |

标准 benchmark 总体包含 **833 条 QA、407 条 Proactive（1,270 个窗口），共 517 个视频**。
仓库中的 release 还包含全量总体：1,248 条记录、522 个视频和 1,338 个 Proactive
窗口。标准总体不包含 8 条采样压力记录，因此 <code>--subset full</code> 覆盖的是不同总体。

源视频需要从上游数据集单独下载：
[StreamingBench](https://huggingface.co/datasets/mjuicem/StreamingBench) 和
[OVO-Bench](https://huggingface.co/datasets/JoeLeelyf/OVO-Bench)。TRACE 提供
v1.1.0 标注、release manifest 和校验元数据，不包含源视频或模型权重。使用前请阅读
[数据卡](docs/dataset-card.zh-CN.md)和[数据条款](DATA_TERMS.zh-CN.md)。
StreamingBench 作者许可重新分发修改后的标注文件；在 TRACE 贡献者拥有相应权利的范围内，
StreamingBench 来源的 TRACE 新增内容采用 CC BY-NC-SA 4.0。OVO-Bench 标注条款仍未解决。

## 基准结果

以下图像展示不同配置在质量、时延和响应行为上的差异。比较不同执行条件时，请结合
下面的成绩表和指标定义阅读结果。

### 相近 QA 质量可能对应不同执行画像

LiveCC 与 MOSS-Preview 的 QA 准确率都接近 65%，但完成率、响应延迟和记录的输出
token 总量不同。MiniCPM-O 作为诊断配置列出，因为它的文本接口无效输出率为 93.52%。

<p align="center">
  <img src="docs/assets/results/fig_qa_accuracy_workload.png" alt="QA 准确率、响应延迟与生成工作量" width="100%">
</p>

### 相近 Proactive 质量可能隐藏不同响应选择

MOSS-VL 与 AURA 的窗口内准确率分别为 8.05% 和 7.92%。MOSS-VL 的误报率更低
（41.1% 对 59.1%），观测到的中位延迟也更短。

<p align="center">
  <img src="docs/assets/results/fig_proactive_quality_delay.png" alt="Proactive 质量与响应延迟" width="100%">
</p>

<p align="center">
  <img src="docs/assets/results/fig_proactive_fa_miss.png" alt="Proactive 误报率与漏报率" width="100%">
</p>

完整结果可在离线[结果看板](docs/results-explorer.zh-CN.md)中筛选，也可阅读
[完整 benchmark 结果与测量限制](docs/benchmark-results.zh-CN.md)。机器可读的结果快照见
[docs/results/data/paper-results.json](docs/results/data/paper-results.json)；
缺失证据保留为 <code>null</code>。

<details>
<summary>查看完整基准成绩表</summary>

### QA · v1.1.0 benchmark 总体（833 条）

| 配置 | 准确率 ↑ | 完成率 ↑ | 中位响应时延（毫秒）↓ | 提交图像 | 记录输出 token | 无效输出 ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **(a) 原生模型 + Adapter** |  |  |  |  |  |  |
| LiveCC | 65.19% | 93.88% | 165.2 | 21,917 | 146,064 | 6.12% |
| MOSS-Preview | 65.07% | 100.00% | 138.1 | 30,835 | 42,206 | 1.92% |
| MOSS-VL | 75.03% | 99.88% | 374.6 | 30,835 | 39,768 | 0.84% |
| ThinkStream | 61.46% | 100.00% | 411.0 | 30,835 | 349,476 | 0.00% |
| VideoLLM-Online | 2.64% | 100.00% | 681.1 | 30,835 | 39,047 | 95.32% |
| MiniCPM-O（原生 duplex） | 2.40% | 100.00% | 489.5 | 30,835 | 24,591 | 93.52% |
| **(b) 端到端系统** |  |  |  |  |  |  |
| JoyAI | 67.47% | 91.36% | 876.1 | 17,235 | 2,286 | 8.52% |
| **(c) 非原生前缀输入** |  |  |  |  |  |  |
| AURA | 73.83% | 99.88% | 819.7 | 31,170 | 2,469 | 0.60% |

### Proactive · v1.1.0 benchmark 总体（407 条 / 1,270 个窗口）

| 配置 | 窗口内准确率 ↑ | 中位延迟（秒）↓ | 误报率 ↓ | 漏报率 ↓ | 提交图像 | 输出 token |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **(a) 自主模型 + Adapter** |  |  |  |  |  |  |
| LiveCC | 12.98% | 1.08 | 65.0% | 0.31% | 23,243 | 78,478 |
| AURA · 持久增量状态 | 7.92% | 1.15 | 59.1% | 47.64% | 439,400 | 50,957 |
| MOSS-VL | 8.05% | 0.33 | 41.1% | 47.24% | 34,520 | 74,672 |
| MOSS-Preview | 4.45% | 0.20 | 77.7% | 35.67% | 34,520 | 193,517 |
| ThinkStream | 0.52% | 2.14 | 73.6% | 68.43% | 32,783 | 373,897 |
| VideoLLM-Online | 0.18% | 0.20 | 82.4% | 60.39% | 32,783 | 42,162 |
| MiniCPM-O（原生 duplex） | 0.51% | 1.24 | 80.3% | 65.43% | 32,617 | 23,636 |
| **(b) 端到端系统** |  |  |  |  |  |  |
| JoyAI | 17.08% | 1.12 | 50.5% | 32.13% | 313,658 | 797,954 |


</details>

## 运行评估

### 安装

已测试 Python 3.10–3.12。克隆或下载[本仓库](https://github.com/om-ai-lab/trace-bench)，
进入仓库根目录：

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
trace --help
~~~

<code>osb</code> 命令仍作为 <code>trace</code> 的兼容别名保留安装；
<code>OSB_VLM_JUDGE_*</code> 环境变量在 <code>TRACE_VLM_JUDGE_*</code> 未设置时仍会作为后备。

~~~bash
trace data validate --release data/releases/v1.1.0
~~~

请保留源码目录；仅安装 wheel 不包含标注和视频。模型依赖应安装在模型自己的环境中。

### 验证软件流程

以下流程生成合成视频，运行 QA 和 Proactive、校验 bundle、重新算分并检查预期答案。
无需 GPU 或 judge 服务。测试替身故意读取 GT；这是软件检查，不是模型评分。

~~~bash
set -euo pipefail
python scripts/make_smoke_fixture.py --output output/smoke
trace data validate --release output/smoke/release
for task in qa proactive; do
  trace run --task "$task" --release output/smoke/release --subset tiny \
    --adapter trace_bench.adapters:TestDoubleAdapter \
    --video-root output/smoke --output "output/smoke/$task" \
    --synthetic --judge-mode exact --checkpoint-every 5
  trace bundle validate "output/smoke/$task"
  trace score "output/smoke/$task" --judge-mode exact
done
python scripts/check_smoke_results.py --output output/smoke
~~~

预期两个任务的答案检查通过，QA accuracy 和 Proactive window accuracy 均为 1.0，
无失败，并标记 <code>synthetic: true</code> /
<code>official_eligible: false</code>。12 秒 fixture 的回答窗口与默认 5 秒 polling 对齐。
模型遥测缺失在此测试中属于预期情况。bundle 有效不等于模型产生了正确回答。

结果保存在被 Git 忽略的 <code>output/</code>。生成器拒绝覆盖已有 fixture；
重复验证时将所有 <code>output/smoke</code> 一致改为新路径。不要为了重跑教程删除已有实验结果。

### 接入模型

1. 从 StreamingBench 和 OVO-Bench [准备源视频](docs/data-setup.zh-CN.md)。
2. 按 [LiveCC 教程](docs/livecc-adapter.zh-CN.md)，或实验性
   [ThinkStream 指南](docs/thinkstream-adapter.zh-CN.md)配置模型。
3. 其他模型实现 [Adapter 接口](docs/adapter-guide.zh-CN.md)，可放在自己的仓库中。
4. 先跑 <code>tiny</code>，检查预测、失败和遥测，再跑 <code>full</code>。
   语义 judge、重算和续跑见[评分与续跑](docs/scoring-and-results.zh-CN.md)。

Core 使用 OpenCV 以 1 FPS 提供时间戳 RGB uint8 数组。QA 接收合法历史，跨模型
user 内容一致。Proactive 使用 5s/10s 事件窗口或标注状态区间，视觉输入在最后严格
窗口终点结束，源视频更短时由其长度限制。Native/non-native 视觉状态与
autonomous/polling 触发方式是独立比较维度，详见[评估协议](docs/evaluation-protocol.zh-CN.md)。

## 文档与引用

- [数据及限制](docs/dataset-card.zh-CN.md)
- [Release 文件与字段](data/releases/README.zh-CN.md)
- [示例与支持状态](examples/README.zh-CN.md)
- [评估协议](docs/evaluation-protocol.zh-CN.md) · [评分与结果](docs/scoring-and-results.zh-CN.md)
- [发布/版本规则](docs/releasing.zh-CN.md) · [验证](docs/release-validation.zh-CN.md)
- [第三方声明](THIRD_PARTY_NOTICES.zh-CN.md) · [贡献](CONTRIBUTING.zh-CN.md) ·
  [安全](SECURITY.md) · [行为准则](CODE_OF_CONDUCT.md)
- [引用](CITATION.cff) · [更新记录](CHANGELOG.zh-CN.md)

TRACE 代码采用 [MIT](LICENSE) 许可。数据权利和上游署名要求见
[DATA_TERMS.zh-CN.md](DATA_TERMS.zh-CN.md)。仓库不提供在线评估器；真实模型结果需要
对应运行环境、模型权重和源视频。

## 开发检查

下面两个 Git 检查需要 Git checkout，并在仓库根目录运行。ZIP 用户仍可安装、评估、
运行测试和发行包检查；需要运行维护检查时请克隆仓库。CI 覆盖 Python 3.10–3.13。

~~~bash
mkdir -p output
python -m pytest -q --basetemp=output/pytest
ruff check .
python scripts/check_docs.py
python scripts/check_public_files.py
python -m build --outdir output/dist
python scripts/check_distribution.py --dist output/dist --output output/distribution-check
~~~

重复发行包检查时使用新的构建/检查目录。CI 验证合成答案和源码包解包后的测试。
GPU 推理和在线语义 judge 验证单独执行。
