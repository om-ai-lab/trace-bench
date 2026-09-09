# Release 文件与字段说明

[English](README.md) | 简体中文

本文说明当前发布的 [v1.1.0](v1.1.0/manifest.json) 标注快照。
数据版本与软件版本独立。视频下载见[数据准备](../../docs/data-setup.zh-CN.md)，
许可见[数据条款](../../DATA_TERMS.zh-CN.md)。

## 文件清单

以下路径均相对于 `v1.1.0/`。JSONL 每行是一个 JSON 对象；
ID 文件是由 `record_id` 字符串组成的 JSON 数组。

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 数据版本、标准文件名、数量及 SHA-256 哈希 |
| `qa.jsonl` | 833 条标准 QA 记录 |
| `proactive.jsonl` | 415 条标准 Proactive 记录，包含 1,338 个响应窗口 |
| `tiny_qa_ids.json` | 用于环境检查的 9 个 QA ID |
| `tiny_proactive_ids.json` | 用于环境检查的 9 个 Proactive ID |
| `standard_proactive_ids.json` | 标准子集的 407 个 ID |
| `high_frequency_proactive_ids.json` | 采样压力子集的 8 个 ID |
| `proactive_standard.jsonl` | 标准子集的完整标准记录，包含 1,270 个窗口 |
| `proactive_high_frequency.jsonl` | 采样压力子集的完整标准记录，包含 68 个窗口 |
| `proactive_subsets.json` | 子集划分条件、数量、哈希及划分校验 |
| `changes.jsonl` | 380 条复核修改或移除记录 |
| `exclusions.jsonl` | 52 条被排除的来源记录及原因代码 |
| `review_summary.json` | 复核覆盖率及处理结果统计 |
| `validation_report.json` | 构建快照时记录的校验结果 |

`--subset full` 读取标准文件，包含采样压力子集，不会自动筛选为标准子集。
`--subset tiny` 按 manifest 指定的 tiny ID 筛选。
请保留完整快照：release 校验会检查 manifest 中的哈希，包括审计文件和派生子集文件。

## 通用约定

时间戳与时长均以秒为单位。时间戳对应原始视频的时间坐标，不是推理经过的墙钟时间。
区间采用左闭右开形式 `[start_s, end_s)`。
`video_path` 相对于运行 OSB 时指定的视频根目录。仓库不包含视频或模型权重。

下表说明 v1.1.0 中出现的字段；“可选”表示部分记录可能没有该字段。
加载器也允许 `memory_length` 和历史 `deadline_s` 为 null。
GT 答案与复核元数据用于评分和审计，不是提供给模型的输入。

| QA / Proactive 共用字段 | 类型 | 含义 |
| --- | --- | --- |
| `record_id` | 字符串 | 唯一的标准记录 ID，供子集文件和结果记录引用 |
| `source_id` | 字符串 | 来源身份标识，本快照中与 `record_id` 相同 |
| `task` | 字符串 | `qa` 或 `proactive` |
| `task_type` | 字符串 | 继承自上游评估集的任务类别 |
| `video_path` | 字符串 | 来源视频相对路径 |
| `memory_length` | 数值 / null | 下文定义的派生标注时长，不是运行截止时间 |
| `metadata` | 对象 | 来源、复核和时间标注信息 |

## QA 记录

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `question` | 字符串 | 问题文本 |
| `options` | 字符串数组 | 按原顺序排列的选项，包含选项标签 |
| `answer` | 字符串 | GT 选项标签 |
| `question_time_s` | 数值 | 问题进入模型时对应的视频时间 |
| `evidence_anchor_s` | 数值 | 用于构造历史帧前缀的证据锚点 |
| `memory_length` | 数值 / null | v1.1.0 中为 `question_time_s - evidence_anchor_s` |

默认 `qa_window_s=10` 时，Core 从
`max(0, evidence_anchor_s - 10)` 采样到 `question_time_s`。
因此 `memory_length` 不等于完整历史帧前缀的时长，证据锚点也不一定是证据片段起点。
详见[评估协议](../../docs/evaluation-protocol.zh-CN.md)。

## Proactive 记录

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `instruction` | 字符串 | 持续监测指令 |
| `instruction_time_s` | 数值 | 发出监测指令时对应的视频时间 |
| `deadline_s` | 数值 / null | 仅用于溯源的历史标注终点，绝不是当前推理截止时间 |
| `windows` | 对象数组 | 快照中保存的响应窗口 |
| `windows[].start_s`、`windows[].end_s` | 数值 | 保存的窗口边界 |
| `windows[].expected_answer` | 字符串 | 该窗口的 GT 回答 |
| `memory_length` | 数值 / null | v1.1.0 中为历史 `deadline_s - instruction_time_s` |

保存的点触发窗口采用快照的 5 秒策略。评估协议与配置决定实际使用的 5 秒或 10 秒窗口；
若下一个触发点更早到来，点触发窗口在该处结束。状态区间保持标注边界。
证据片段不决定响应容差。历史时长字段不要求模型处理完整视频。
视觉证据投递与输出排空遵循[评估协议](../../docs/evaluation-protocol.zh-CN.md)，
不以 `deadline_s` 为准。

## 元数据

| `metadata` 内的字段 | 类型 / 适用任务 | 含义 |
| --- | --- | --- |
| `dataset` | 字符串 / 两者 | `ovo_bench` 或 `streambench`（StreamingBench） |
| `stable_id` | 字符串 / 两者 | 稳定审计标识，格式不同于标准 `record_id` |
| `source_file` | 字符串 / 两者 | 用于溯源的来源标注文件名 |
| `source_question_id` | 字符串 / 两者 | 来源标注中的问题 ID |
| `required_ability` | 字符串 / 两者 | 来源能力描述，可为空字符串 |
| `validation_tier` | 字符串 / 两者 | `human_reviewed`（人工复核）或 `machine_screened`（机器筛查） |
| `machine_risk_level` | 字符串 / 两者 | 历史机器筛查结果，不代表最终有效性判定 |
| `retention_gap_s` | 数值 / 两者 | 派生时长，等于本快照的 `memory_length` |
| `source_memory_length_s` | 数值 / 两者 | 上游原始时长 |
| `source_memory_length_discrepancy_s` | 数值 / 两者 | 上游原始时长减去派生时长 |
| `evidence_spans` | 数组 / QA，可选 | 复核证据；每项含数值 `start_s`、`end_s` 和字符串 `description` |
| `video_categories` | 字符串 / Proactive | 来源视频类别，可为空字符串 |
| `first_trigger_lead_s` | 数值 / Proactive | 最早触发时间减去指令时间 |
| `monitoring_horizon_s` | 数值 / Proactive | 历史 `deadline_s - instruction_time_s`，仅用于描述 |
| `point_response_tolerance_s` | 数值 / Proactive | 快照的点触发容差（5），不覆盖评估配置 |
| `trigger_annotations` | 数组 / Proactive | 与 `windows` 按索引对应的事件/状态标注 |
| `media_boundary_adjustments` | 数组 / 两者，可选 | 对齐可读媒体边界的时间修正 |

每个 `media_boundary_adjustments` 对象包含字符串 `field`、
数值 `source_value_s` 和 `effective_value_s`，以及字符串 `reason`。
保留的 `machine_risk_level`（例如 `blocking`）可能是在人工修正前产生的；
不能仅凭它排除已发布记录。

### Proactive 触发标注

| `trigger_annotations[]` 内的字段 | 类型 | 含义 |
| --- | --- | --- |
| `event_id` | 字符串 | 记录内的事件标识 |
| `answer` | 字符串 | 预期答案 |
| `annotation_source` | 字符串 | 触发标注来源，例如人工复核或按任务策略推导 |
| `trigger_type` | 字符串 | `event_onset`、`event_completion`、`clue_sufficient` 或 `state_interval` |
| `point_trigger_s` | 数值 / null | 点触发时间；状态区间时为 null |
| `interval_start_s`、`interval_end_s` | 数值 / null | 状态区间边界；不适用时为 null |
| `response_policy` | 字符串 | 快照策略标签，例如 `up_to_5s_until_next_trigger` 或 `reviewed_state_interval` |
| `response_window_start_s`、`response_window_end_s` | 数值 | 快照中的响应窗口边界 |
| `source_window_start_s`、`source_window_end_s` | 数值，可选 | 修正前的原始窗口边界 |
| `accepted_facts` | 字符串数组，可选 | 可接受的其他事实表述 |
| `evidence_description` | 字符串，可选 | 视觉证据的复核说明 |
| `evidence_start_s`、`evidence_end_s` | 数值，可选 | 用于复核的证据片段 |

`event_onset` 表示条件首次成立；`event_completion` 表示动作完整完成；
`clue_sufficient` 表示线索首次足以确定答案；
`state_interval` 表示状态成立的持续区间。这些字段记录视觉事实，不记录模型延迟容差。

## Manifest

| 字段 | 含义 |
| --- | --- |
| `release_id`、`schema_version` | 数据版本标识和 schema 标识（字符串） |
| `status` | 发布状态；本快照为 `private_provisional`，见数据条款 |
| `qa_file`、`proactive_file` | 标准 JSONL 文件名 |
| `tiny_qa_ids_file`、`tiny_proactive_ids_file` | Tiny ID 文件名 |
| `counts` | 数据范围名称到整数数量的映射对象 |
| `source_files` | 来源指纹数组，每项包含 `path`（溯源标识）与 `sha256` |
| `files` | 13 个快照文件名到 SHA-256 字符串的映射，不包含 manifest 自身 |
| `video_root_notes` | 视频根目录配置说明（字符串） |
| `limitations` | 数据限制说明的字符串数组 |

来源指纹中的路径是溯源标识，不要求用户将文件下载到这些路径。
发布状态与构建校验结果是不同概念。

## Proactive 子集描述

`proactive_subsets.json` 包含以下字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version`、`source_file` | 描述文件 schema 与标准来源文件名 |
| `source.record_count`、`source.window_count` | 来源记录总数和窗口总数 |
| `criterion.name`、`criterion.reason` | 划分规则标识和原因说明 |
| `criterion.scope` | `record`，即选中记录后保留其全部窗口 |
| `criterion.window_duration` | 时长公式 `end_s - start_s` |
| `criterion.threshold_s`、`criterion.inclusive` | 阈值为 1.0 秒，包含等于阈值的情况 |
| `subsets.standard`、`subsets.high_frequency` | 各含 `ids_file`、`record_file`、`record_count`、`window_count`、`qualifying_window_count` |
| `hashes` | SHA-256 字符串，键为 `source_file`、`standard_ids_file`、`standard_record_file`、`high_frequency_ids_file`、`high_frequency_record_file` |
| `checks` | 布尔检查：`full_records_preserved`、`record_ids_disjoint`、`record_ids_union_equals_source`、`record_order_sorted_by_record_id` |

任一保存窗口时长不超过 1 秒，该记录就进入采样压力子集。
选中的 8 条记录共有 68 个窗口，其中 25 个满足短窗口条件。
划分依据是快照窗口，不随运行 FPS 或容差重新计算。
短窗口不一定不可观测，还取决于采样时刻是否落入窗口。

## 复核与校验附属文件

这些文件记录修改摘要和覆盖情况，不是包含提示词、采样脚本或完整复核对话的完整标注审计材料。

### 修改与排除

两份 JSONL 都包含字符串字段 `record_id`、`stable_id`、`dataset`、
`mode`（QA/Proactive）和 `task_type`。

| 额外字段 | 含义 |
| --- | --- |
| `changes.jsonl: disposition` | 复核处理动作 |
| `changes.jsonl: issue_codes` | 记录的问题代码字符串数组 |
| `changes.jsonl: changes` | 每项含 `field`（来源字段路径）、`old_value`、`new_value` 的数组 |
| `exclusions.jsonl: reason_codes` | 排除原因代码字符串数组 |

新旧值保留来源 JSON 类型，包括 null 和嵌套对象；字段路径不一定对应标准记录路径。
历史触发标注除上述事件、答案和证据字段外，还可能包含
`observed_onset_s`、`observed_completion_s`、`monitoring_horizon_s`、
`response_tolerance_s`、`tolerance_before_s` 和 `tolerance_after_s`。
这些保留历史标注值，不是当前评分配置。
380 条变更记录中包含 328 条修改和 52 条移除；排除文件中的 52 条不能重复扣减。

### 复核摘要

| `review_summary.json` 中的字段 | 含义 |
| --- | --- |
| `release_id` | 数据版本标识 |
| `source_record_count`、`included_record_count`、`excluded_record_count` | 输入 1,300 条，保留 1,248 条，排除 52 条 |
| `saved_review_count`、`unresolved_saved_reviews` | 保存的复核共 577 条，其中未解决的为 0 条 |
| `review_dispositions` | 按动作统计：`edit` 328、`remove` 52、`valid` 197 |
| `validation_tiers` | 保留记录中：`human_reviewed` 525、`machine_screened` 723 |
| `pending_machine_screened_count` | 历史字段名，表示未逐条人工复核的 723 条保留记录 |
| `included_by_dataset_mode`、`included_by_task_type` | 来源/任务类别到保留数量的映射对象 |
| `duplicate_policy` | 重复记录保留较小 stable ID 的规则 |
| `duplicate_upper_id_removals` | 因重复移除 25 条，已计入 52 条排除记录 |

### 校验报告

`validation_report.json` 包含 `release_id`、`status`（构建校验结果）、
`counts`（`qa`、`proactive`、`included`、`excluded`、`changes` 的整数数量）
以及 `checks`（具名布尔检查）：

| 检查项 | 含义 |
| --- | --- |
| `all_saved_reviews_completed` | 已保存的复核均已处理完成 |
| `all_unreviewed_records_machine_completed_no_issue` | 未逐条人工复核的记录通过机器筛查 |
| `answers_match_options` | QA 答案与可用选项标签匹配 |
| `canonical_content_unique`、`canonical_record_ids_unique` | 标准记录内容与 ID 唯一 |
| `duplicate_upper_ids_removed` | 已执行重复记录处理规则 |
| `media_boundaries_within_last_readable_frame` | 检查的时间戳在可读媒体边界内 |
| `proactive_instruction_before_trigger` | 指令先于触发点 |
| `proactive_positive_windows`、`proactive_windows_non_overlapping` | 保存窗口时长为正且互不重叠 |
| `qa_evidence_not_after_question` | 证据锚点不晚于提问时间 |
| `reviewed_memory_intervals_derived` | 已推导复核记录的时长字段 |
| `source_lineage_matches_audit_manifest` | 来源指纹与审计 manifest 匹配 |
| `streambench_proactive_128_matches_upstream` | 特定来源记录的一致性检查 |

这些是保存的构建期检查，不等于重新检查用户本地视频，也不代表许可授权。
在仓库根目录运行 `osb data validate --release data/releases/v1.1.0`，
可检查当前快照的 schema 和哈希。

