# 更新记录

[English](CHANGELOG.md) | 简体中文

## 未发布

- 项目更名为 TRACE（仓库 `om-ai-lab/trace-bench`）。Python 包改为 `trace_bench`，
  命令行改为 `trace`；原 `osb` 命令保留为兼容别名。
- 评分配置优先读取 `TRACE_VLM_JUDGE_*` 环境变量，未设置时回退到原有
  `OSB_VLM_JUDGE_*` 名称。
- 协议、合约、算分器和 schema 标识（如 `osb-contract-v4`、`osb-scoring-v6`）
  保持不变，已有 Run Bundle 仍然有效。

## 0.1.0

- QA/Proactive 本地 Core、OpenCV RGB 抽帧和外部 adapter 接口。
- LiveCC 教程和实验性 ThinkStream 集成。
- 原始事件 bundle、断点续跑、完整性校验和离线重算。
- 精确/可配置语义评分及质量、时延、输入处理量报告。
- 中英文安装、适配和协议文档。
- 合成测试在原始评分和重算后均验证正确回答。
- 源码发行包包含测试辅助文件，解包后运行测试。
- 标注 v1.1.0 版本独立；provisional 状态反映 OVO-Bench 标注条款仍待解决。
  StreamingBench 作者已许可重新分发修改后的标注文件；在 TRACE 贡献者拥有相应权利的范围内，
  StreamingBench 来源的 TRACE 新增内容采用 CC BY-NC-SA 4.0。标注内容未改变。

执行合约 `osb-contract-v4` 和算分器 `osb-scoring-v6` 保留兼容性标识。
软件 0.1.0 不改变评分规则。
