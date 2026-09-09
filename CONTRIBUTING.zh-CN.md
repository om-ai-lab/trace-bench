# 贡献指南

[English](CONTRIBUTING.md) | 简体中文

安装 `'.[dev]'`，运行 README 中开发检查和合成流程。
Issue 请提供软件/数据版本、命令、预期行为和脱敏日志。
不要附带视频、权重、凭据或含私有信息的原始 bundle。

模型特有行为放在 adapter 中。证据、prompt、评分和失败策略变化需要回归测试和兼容性审查。
不要顺便放宽 QA parser 或修改 finalized 原始结果。
说明用户是否需要重算或重新推理。

OSB 自有代码贡献采用 MIT；复制内容保留上游许可。
数据遵循[数据条款](DATA_TERMS.zh-CN.md)。
遵守[行为准则](CODE_OF_CONDUCT.md)和[发布规则](docs/releasing.zh-CN.md)。
欢迎中英文贡献，配对文档及命令块保持一致。
