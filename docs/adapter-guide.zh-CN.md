# 实现 adapter

[English](adapter-guide.md) | 简体中文

Adapter 可以放在自己的仓库。在模型环境安装它和 TRACE，通过
`--adapter module:Class --adapter-config file.json` 接入，无需修改 Core 注册表。
参见 [LiveCC](livecc-adapter.zh-CN.md)及实验性
[ThinkStream](thinkstream-adapter.zh-CN.md)。
[TestDoubleAdapter](../src/trace_bench/adapters.py) 仅用于合成测试且故意读取 GT，
不能复制其答案选择逻辑。

## 接口边界

使用 [models.py](../src/trace_bench/models.py) 和
[adapters.py](../src/trace_bench/adapters.py) 中的协议。

1. 声明解码帧输入、持久/无状态、query/polling/autonomous 触发、pacing 和部署方式。
   Core 和 adapter pacing 必须匹配。
2. 权重只加载一次，在 `open(context)` 创建每题状态。
   Context 含评估元数据，不能把答案、GT 窗口、证据描述或源路径传给模型。
3. `observe(observation)` 接收时间戳 RGB 数组。
   记录实际缩放、chunk 和模型状态 commit；仅缓存不等于 commit。
4. `query(request)` 从 `request.text` 获取评估文本，逐字节保留。
   可用原生 system 和机械控制序列化，并记录。历史计算允许且计入成本。
5. QA 按统一指令回答选项。Autonomous Proactive 只收一次指令，polling 单独报告。
   保留原生 silence，映射为 WAIT，不强迫模型输出 fallback 字面词。
6. 返回保留原始输出的 `ModelEvent`。
   片段需要稳定 `response_id`、有序 `sequence_id`、`text_mode` 和 `is_final`，
   不能把每个 token 当成新答案。
7. 在 Core 证据边界 flush 未处理 chunk。
   `session.close()` / `adapter.close()` 释放会话/进程资源，shutdown 不能新增评分时间。

分块 QA 只有必须在最后帧前排入 query 时才声明 `before_observation_deferred`；
答案必须消费该帧。

## 测量与失败

直接测量生成首 token，区分视频时钟与单调运行时钟。
记录可观测的实际调用、token ID、提交帧/像素、commit、GPU 显存和失败；
未知保持缺失。不根据文本长度估算 token，不根据配置 FPS 估算工作量。
保留可恢复失败；初始化不可用或 CUDA 损坏时抛出 `FatalEvaluationError`。
遵循[评估协议](evaluation-protocol.zh-CN.md)。

## 验证

运行 preflight、真实 tiny 推理和 bundle 校验，检查答案、失败和遥测后再跑 full。
Tiny 通常需要 GPU，合成测试只检查软件。
Native 分类需要实际模型状态复用证据；能力声明和运行成功不等于符合性认证。
