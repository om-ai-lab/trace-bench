# 评估协议

[English](evaluation-protocol.md) | 简体中文

本协议对应软件 0.1.0 的执行与评分规则。Bundle 兼容性 ID 保留为
`osb-contract-v4` 和 `osb-scoring-v6`。软件打包变化不重新定义这些规则。

## 统一证据与提示词

Core 读取本地标注、控制时间线，通过 OpenCV 以 1 FPS 提供 RGB uint8 数组。
源帧编号为 `floor(t * source_fps + 0.5)`，BGR 转为 RGB。
比较模型使用相同合法时间戳和证据预算。Adapter 可记录原生缩放/chunk 行为，
但不能替换为关键帧、自行回放未来帧或独立读取源视频。

QA user 内容跨模型一致：原问题、原顺序选项，以及只回答选项字母的指令。
有原生 system prompt 就使用；否则省略，接口必须时才提供中性 system。
Role/control-token 序列化可以包裹 user 内容，但不能改写。记录 system 和序列化方式。

Proactive 接收原始指令，不加统一的问题或 WAIT 包装。保留原生 silence 协议。
只有没有原生回答/静默机制的模型使用以下最小 fallback system prompt：

```text
You are observing a live video stream frame by frame.
Follow the user's instruction.
If the available evidence is insufficient, output WAIT.
If the evidence is sufficient, output only a concise answer.
```

只描述视频的启动提示不等价于按指令主动响应；应换用兼容接口或声明集成不兼容。

## QA

提问前可以编码、缓存、提交历史帧，或进行模型原生生成。
保留其成本和事件，但提问前文本不是 QA 答案。Core 在语义提问边界只发送一次 query。
分块适配器可声明 `before_observation_deferred`，在处理提问时刻帧前排入 query，
但必须消费该帧后才能回答。TTFT 从统一 query 到达边界开始，
包括必要帧处理，并在 CUDA 同步前开始计时。

质量指标是包含所有题目和失败的选项准确率。
当前 parser 在已有格式包装和推理块归一化后接受一个合法选项标签
（例如 `B.` 或 `: C`）。选项加正文、答案短语和普通句子中的偶然字母无效。
Adapter 不能从不合规正文中提取合规字母。原始文本保留，本版不扩大 parser 接受范围。

## Proactive 执行与窗口

Autonomous adapter 只接收一次指令，随观测到达自主输出。
Polling adapter 按冻结时间表接收重复请求。
Query 与帧同一时间时先提供该帧；两帧之间的 query 不能看到下一帧。
持久状态 polling 是被提示的基线，不是自主输出。

GT 时间记录视觉事实：开始、完成、线索充分或状态区间。
证据片段用于复核，不决定响应容差。
点触发 `t_i` 在固定 W = 5s 或 10s 下的严格窗口为：

```text
[t_i, min(t_i + W, t_{i+1}))
[t_last, t_last + W)
```

状态区间保留标注 `[start, end)`。所有边界半开。
指令前历史独立固定为 5s，不随 W 改变。
密集窗口不合并、不为命中采样点移动，报告间隔、有效长度、观测数及拥挤/非拥挤汇总。
没有观测帧表示协议可观测性问题，不自动说明 GT 错误。

视觉输入在最后严格窗口终点结束；有视频时长元数据时按源时长限制。
Core 不为探测时长解码完整源视频。时长未知则记录未知并使用 GT 终点。
历史 `deadline_s` 只用于溯源。

源视频提前结束时，autonomous wall-clock 会话可使用最后严格窗口剩余时间，
不新增帧或 polling。首 token 单调时钟映射至流时间；无法观测时，
用完整回答接收时间作为保守边界，并保留首 token 覆盖缺失。
有限 shutdown 可完成已及时启动的 delta/snapshot 回答，
不能启动新的可评分回答或模型调用。Complete 事件各自独立；
片段必须有稳定 response ID 和结束标记。

## Proactive 分数与 judge

同时报告三个视图及其统计范围：

- `strict_all_window`：全部窗口，包括未回答和失败题。
- `strict_observable_window`：至少收到一帧 Core 观测的窗口。
- `post_trigger_eventual`：触发后至下一点触发；最后点触发截止最后严格窗口终点，
  状态截止状态终点。它没有历史全局 deadline，但也不是无限给分。

每个回答 episode 最多分配给一个事件，先按时间归属。
不能因文本匹配而把后一事件答案计给前一事件。
同时报告未输出、窗口外打扰和冗余回答。
时延 p50/p95 使用严格窗口内已回答窗口；无法因果排序的耗时保留在该范围内并标缺失。

精确匹配提供确定性结果，语义 judge 处理合法同义表达。
`auto` 对 SSR/CRR 使用已配置 judge，其他类型精确匹配；
`vlm` 对全部 Proactive 类型使用 judge。
当前 judge 接收问题、参考答案、预测文本，不接收视频帧。
比较时冻结模型、prompt、路由、温度和窗口，记录原始 judge 回复、错误与覆盖率。
Judge 失败/回退属于诊断结果，不是模型错误。参见[评分](scoring-and-results.zh-CN.md)。

## 指标、类别与持久化

报告质量；TTFT/响应时延；帧处理 p50/p95、lag、准时率、丢帧率、流完成率；
提交帧/像素；实际文本 token；模型调用和推理墙钟时间；
隔离进程 GPU 基线/峰值/增量；题目完成率、失败类型、超时、重试和测量覆盖率。
QA 历史成本与 query 成本分开，包含经过时间、推理区间、调用、token、帧/像素和 commit。
视频时钟与单调耗时时钟分开。不能从文本长度或配置 FPS 估算缺失 token、
TTFT、视觉 token 或资源使用。

视觉状态分为 Native Streaming（实际持久模型状态复用）和 Non-native Streaming
（历史/窗口回放）。Python 帧列表不是原生状态。
主要 Proactive 结果要求原生状态、自主输出和 wall-clock pacing；polling 基线单独报告。
QA 没有主动触发类别。能力声明仍需实现审查。

结构有效不代表正式资格。Synthetic/provisional、logical pacing、必需遥测缺失、
judge 失败或不兼容 Proactive 类别会阻止正式资格，但保留诊断分数。

Core 每 N 条终态记录连同事件落盘（默认 10，可设 5），结束时保存不足批次。
Resume 跳过有效已提交成功和失败记录，重跑未完成记录，拒绝变化的运行身份。
不自动逐题重试；主动重试用新 run。无法初始化或 CUDA 状态损坏时落盘后中止。
Finalized bundle 不可修改；`events.jsonl` 是权威事件源，内嵌副本必须一致。
重算只写附属结果，不修改原始证据。

模型、数据、证据、prompt、时间或推理设置变化要求新 run。
仅评分变化且原证据充分时可以重算。比较时保持数据范围、执行类别和评分设置一致。
