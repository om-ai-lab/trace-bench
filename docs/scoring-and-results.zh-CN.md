# 评分与续跑

[English](scoring-and-results.md) | 简体中文

先推理，再校验和评分。只生成标注不会生成结果。
Preflight 只检查配置，不执行推理。

## Judge 与重算

QA 使用单标签选项评分。Proactive 使用精确匹配或用户配置的
OpenAI-compatible 语义 judge。生成示例 bundle 后，替换服务地址、模型名和密钥执行：

```bash
osb bundle validate output/livecc-proactive
export OSB_VLM_JUDGE_BASE_URL=http://127.0.0.1:30099/v1
export OSB_VLM_JUDGE_MODEL=your-served-judge-model
export OSB_VLM_JUDGE_API_KEY=your-key
osb score output/livecc-proactive --judge-mode auto \
  --judge-base-url "$OSB_VLM_JUDGE_BASE_URL" --judge-model "$OSB_VLM_JUDGE_MODEL"
```

`auto` 对 SSR/CRR 使用配置的 judge，其他类型精确匹配；
`vlm` 对所有 Proactive 类型使用 judge；`exact` 不需要服务。
Judge 接收问题、参考答案和预测文本，不接收视频帧。
密钥从指定环境变量读取，不落盘。
Judge 配置缺失或调用失败时结果为诊断值/不完整评分。

显式 model/URL 参数覆盖原 bundle 冻结的设置。
比较时保持 judge 模型、prompt、路由和窗口一致。
重算写入 `rescored_records.jsonl` 和 `rescored_metrics.json`，
不改 `records.jsonl` 或 `events.jsonl`。
需要保留多个 judge 版本时，在下次重算前归档派生结果。

## 输出与续跑

`records.jsonl` 保存预测/状态；`events.jsonl` 保存原始事件和遥测。
Manifest/config/integrity 文件标识运行，`metrics.json` 和 `summary.json` 是原始汇总。

默认每 10 条记录 checkpoint，支持 `--checkpoint-every 5`。
中断后用相同命令和输出目录续跑。已提交成功和失败题跳过，未完成题重跑。
Finalized 结果不能续写或覆盖。设置变化要求新输出目录。

结构有效与正式资格分开。除分数外还应检查失败、judge 和遥测覆盖率。
缺失测量不是零。QA 历史成本与 query TTFT 分开。
统计范围和类别定义见[协议](evaluation-protocol.zh-CN.md)。

## 排错

- 缺视频：运行视频检查器，检查根目录和解压层级。
- 缺 bundle 文件：先 `osb run`，再 `bundle validate` 和 `score`。
- Adapter 导入失败：在模型环境安装 adapter 包。
- Pacing 不匹配：使 Core pacing 与 adapter 能力/配置一致。
- CUDA 初始化失败：先修环境再续跑，不能解释为模型错误率。
- 配置变化：保留旧 bundle，换新输出目录。
- 意外错误：使用 `osb --debug ...` 查看 traceback。
