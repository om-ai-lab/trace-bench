# Adapter 示例

[English](README.md) | 简体中文

| 集成 | 范围 | 教程 |
| --- | --- | --- |
| LiveCC | 本地权重；此前在真实 tiny 数据/GPU 上检查 | [配置](../docs/livecc-adapter.zh-CN.md) |
| ThinkStream | 实验性；模拟运行接口测试，真实 GPU 待重新验证 | [配置](../docs/thinkstream-adapter.zh-CN.md) |
| TestDoubleAdapter | 仅合成测试，故意读取 GT | [软件测试](../README.zh-CN.md#验证软件流程) |

LiveCC 的 `logical.json` 用于快速诊断；测量时延时，
`wall_clock.json` 必须与 Core wall-clock pacing 配合。
源码、权重和模型依赖另行获取。其他 adapter 可以放在外部仓库，通过 `module:Class` 加载。

执行成功与符合性、质量及时延资格是不同问题。
需要检查实际状态复用、回答行为、失败、judge 和遥测覆盖率。
