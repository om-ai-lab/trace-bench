# 数据集：v1.1.0

[English](dataset-card.md) | 简体中文

来自 StreamingBench 和 OVO-Bench 的纯视觉时间戳 QA 与 Proactive Response 标注，
包含经过复核的时间修正。

| 数据范围 | 数量 |
| --- | --- |
| QA | 833 条 |
| Proactive | 415 条 / 1,338 个窗口 |
| Proactive 标准子集 | 407 条 / 1,270 个窗口 |
| Proactive 采样压力子集 | 8 条 / 68 个窗口 |
| Tiny 环境检查子集 | 9 条 QA + 9 条 Proactive |

`--subset full` 包含采样压力子集。Tiny 用于检查环境，不用于模型排名。
数据版本与软件版本独立。

## 文件与时间坐标

`qa.jsonl` 和 `proactive.jsonl` 保存标准记录。ID 文件定义子集。
`manifest.json` 保存哈希和来源指纹；来源路径是溯源标识，不是用户需要准备的本地文件。
审计附属文件记录标注变更与排除情况。

时间戳对应原始视频。QA 包含问题、选项、答案、提问时间和证据锚点；
Proactive 包含指令时间、事件/状态标注和答案。历史 `deadline_s` 只用于溯源，
不是截止时间。详见[协议](evaluation-protocol.zh-CN.md)。

## 限制与获取

525 条记录经过人工复核；723 条通过模型辅助筛查，但没有逐条人工复核。
不能将全部数据描述为人工验证。密集窗口在 1 FPS 下可能不可观测，应单独报告覆盖率
和采样压力子集结果。公开 GT 也限制了对未见数据泛化的结论。

仓库不包含视频或权重，参见[数据准备](data-setup.zh-CN.md)。
许可与上游待确认事项统一见[数据条款](../DATA_TERMS.zh-CN.md)。
