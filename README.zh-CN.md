# Open Stream Bench

[English](README.md) | 简体中文

用于时间戳视频 QA 与 Proactive Response 的本地评估 Core。用户自行下载源视频，
通过 adapter 运行自己的模型，保存原始输出、耗时、失败与评分。没有托管在线评估服务。
真实模型评估通常需要 GPU。

| 内容 | 版本与范围 |
| --- | --- |
| 公开标注 | `data/releases/v1.1.0` |
| 全量数据 | 833 道 QA、415 道 Proactive，1,338 个 Proactive 窗口 |
| Tiny 子集 | 9 道 QA + 9 道 Proactive，用于检查环境 |
| Core 软件版本 | `0.0.0`，与数据版本独立 |
| 协议 / 算分器 | `osb-contract-v4` / `osb-scoring-v6` |
| 软件 / 数据许可 | [MIT](LICENSE) / [数据条款](DATA_TERMS.md) |

仓库只发布 v1.1.0 标注，本地被忽略的历史数据保留。视频和权重不随仓库分发。
上游标注授权确认仍在进行，发布边界见[数据条款](DATA_TERMS.md)。
[数据卡](docs/dataset-card.md)说明复核覆盖率与限制，不能把全部数据描述为逐条人工复核。

## 安装

使用 Python 3.10–3.12，下载或克隆本仓库后进入仓库根目录：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
osb --help
osb data validate --release data/releases/v1.1.0
```

首版支持从源码目录运行。仅安装 wheel 不会下载标注目录、源视频或模型依赖。

## 先完整跑通软件流程

以下命令生成短视频与合成标注，实际经过 OpenCV 解码、QA/Proactive 执行、落盘、
bundle 校验和重新算分。无需 GPU、源数据下载、模型权重或 judge 服务。
测试替身会故意读取 GT，分数必须标为 synthetic，不能作为模型结果。每次换一个新输出目录。

```bash
python scripts/make_smoke_fixture.py --output /tmp/osb-smoke
osb data validate --release /tmp/osb-smoke/release
for task in qa proactive; do
  osb run --task "$task" --release /tmp/osb-smoke/release --subset tiny \
    --adapter open_stream_bench.adapters:TestDoubleAdapter \
    --video-root /tmp/osb-smoke --output "/tmp/osb-smoke/$task" \
    --synthetic --judge-mode exact --checkpoint-every 5
  osb bundle validate "/tmp/osb-smoke/$task"
  osb score "/tmp/osb-smoke/$task" --judge-mode exact
done
```

每个输出目录应包含 `records.jsonl`、`events.jsonl`、`metrics.json`、`summary.json`、
`resolved_config.json`、`manifest.json`、`integrity.json`。重算后增加
`rescored_records.jsonl` 与 `rescored_metrics.json`。
检查 summary 中的 `synthetic: true` 和资格报告中的 `official_eligible: false`。
bundle 校验通过只代表文件完整，不代表模型效果或协议资格已获认证。

## 准备真实视频

按[数据准备教程](docs/data-setup.md)，从
[StreamingBench](https://streamingbench.github.io/) 与
[OVO-Bench](https://github.com/joeleelyf/ovo-bench) 获取源视频，继续使用本仓库的 OSB 标注。
视频根目录下需有 `videos/` 与 `src_videos/`，对应记录中的相对 `video_path`。
OVO 必须使用原始源视频，不能用时间戳归零的切片替换。
注意 StreamingBench 与名称相近的 StreamBench 是不同项目。

```bash
python scripts/check_videos.py --release data/releases/v1.1.0 \
  --video-root /path/to/osb-media --subset tiny
```

将 `/path/to/...` 换为实际路径。此工具检查文件是否存在；推理才会验证实际解码。
在加载模型前修复缺失路径。全量检查使用 `--subset full`。

## 跑真实模型

首先按 [LiveCC 教程](docs/livecc-adapter.md)准备上游依赖、权重和环境变量。
在模型环境内安装 OSB；前面的软件测试虚拟环境没有 PyTorch 和模型运行依赖。

配置完成后，在 OSB 根目录执行预检查，不加载权重：

```bash
osb run --task qa --release data/releases/v1.1.0 --subset tiny \
  --adapter open_stream_bench.livecc_adapter:LiveCCAdapter \
  --adapter-config examples/livecc/logical.json --pacing logical \
  --video-root /path/to/osb-media --output /path/to/results/livecc-qa \
  --judge-mode exact --checkpoint-every 5 --preflight-only
```

然后实际运行 QA 和 Proactive：

```bash
for task in qa proactive; do
  osb run --task "$task" --release data/releases/v1.1.0 --subset tiny \
    --adapter open_stream_bench.livecc_adapter:LiveCCAdapter \
    --adapter-config examples/livecc/logical.json --pacing logical \
    --video-root /path/to/osb-media --output "/path/to/results/livecc-$task" \
    --judge-mode exact --checkpoint-every 5 --proactive-window-s 5
  osb bundle validate "/path/to/results/livecc-$task"
  osb score "/path/to/results/livecc-$task" --judge-mode exact
done
```

检查完成数量、`failed_reason`、模型答案与原始事件。finalized 的 bundle 也可能包含失败题。
上述 logical pacing 和 exact 算分用于快速检查；测量流式时延时同时使用
`examples/livecc/wall_clock.json`、`--pacing wall_clock`，换新输出目录，并配置语义 judge。
Tiny 成功后才切换 `--subset full`。全量 Proactive 包含高频压力子集，
不会自动过滤为技术报告使用的 standard 人口。

自己的 adapter 通过 `--adapter module:Class --adapter-config file.json` 接入，
参见 [adapter 教程](docs/adapter-guide.md)及[示例状态](examples/README.md)。
Native/non-native 分类来自 adapter 声明，不代表 Core 自动证明了模型增量状态。
视觉状态和 autonomous/polling 触发方式是独立维度。

## 算分与断点续跑

QA 使用统一 user prompt 与归一化单标签评分；普通句子、选项字母加答案正文不作为
合法选项提取。原始输出不修改。Proactive 同时报告严格全窗口、严格可观测窗口、
触发后 eventual 分数，以及窗口外输出、冗余回答与覆盖率。

使用自己部署的 OpenAI-compatible judge：

```bash
export OSB_VLM_JUDGE_BASE_URL=http://127.0.0.1:30099/v1
export OSB_VLM_JUDGE_MODEL=your-served-judge-model
export OSB_VLM_JUDGE_API_KEY=your-key
osb score /path/to/results/livecc-proactive --judge-mode auto \
  --judge-base-url "$OSB_VLM_JUDGE_BASE_URL" --judge-model "$OSB_VLM_JUDGE_MODEL"
```

`auto` 对 SSR/CRR 使用语义 judge，其他任务类型归一化精确比较；`vlm` 对所有
Proactive 类型使用 judge。当前 judge 接收问题、参考答案、预测文本，不接收视频帧。
未配置服务或调用失败时，结果是诊断值或语义评分不完整，不能当作最终语义分数。
这些文本将发送到你指定的服务；密钥从环境变量读取，不保存到 bundle。

重新算分只写派生文件，不改原始 records/events。默认支持 resume：中断后重复完全相同
的运行命令，跳过已经提交的成功题和失败题，重新执行未提交题。默认每 10 题落盘，
可设 `--checkpoint-every 5`。已 finalized 的 bundle 不允许续写或覆盖；修改模型、
提示词、数据或执行参数后，使用新输出目录。

## 协议与报告

Core 使用 OpenCV 以 1 FPS 提供时间戳 RGB uint8 数组。QA 只接收合法历史，user 内容
跨模型一致；允许原生 system prompt 和必要的 role/control 序列化。历史处理成本单独保留。

Proactive 点触发窗口为半开区间，容差 5s 或 10s，下一触发点更早时截断；SSR 使用状态区间。
视觉输入到最后严格窗口终点为止，源视频更短时由元数据限制。视频先结束可以留下无新帧
的剩余评分时间；有限 shutdown drain 只允许已及时开始的回答完成。Core 不为探测长度
而解码整段视频。eventual 到下一触发点或最终严格窗口终点截止。
指令前历史固定 5s，不随响应容差变化。

报告包含质量、时延、图像处理量、token、模型调用、GPU 显存、失败和遥测覆盖率。
无法真实测到的值保持缺失。自动 `official_eligible` 检查不能替代 adapter 人工审查。
更多见[完整协议](docs/evaluation-protocol.md)、[算分与排错](docs/scoring-and-results.md)、
[数据卡](docs/dataset-card.md)、[发布规则](docs/releasing.md)、
[第三方声明](THIRD_PARTY_NOTICES.md)、[贡献说明](CONTRIBUTING.md)和[引用](CITATION.cff)。

## 开发检查

```bash
python -m pytest -q
ruff check .
python -m build
```

CI 只运行 CPU 软件测试，真实 GPU 模型测试作为单独发布检查。
`master` 跟随最新数据，版本分支保留发布快照。
本次实际验证范围与尚待完成项见[发布验证记录](docs/release-validation.md)。
