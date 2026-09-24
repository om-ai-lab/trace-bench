# 版本与发布

[English](releasing.md) | 简体中文

软件 0.1.0 与标注 v1.1.0 独立发布。`main` 跟随当前开发。
`v1.1.0` 等数据版本分支保留选定快照，不自动跟随 main。
软件 tag 使用 `v0.1.0` 等名称，不与数据分支重名。

README 展示软件与数据版本。Run Bundle 另记录执行合约 `osb-contract-v4`、
算分器 `osb-scoring-v6` 和 schema 标识用于复现。
它们是兼容性标识，不是独立软件包。文档或打包修复不改变评分标识，
评分规则变化则必须改变；不能重新标记历史 bundle。

由于该综合快照包含条款仍未解决的 OVO-Bench 标注，v1.1.0 manifest 继续标为 provisional。
StreamingBench 作者已许可在本仓库中重新分发修改后的标注文件；在 TRACE 贡献者拥有相应
权利的范围内，StreamingBench 来源的 TRACE 新增内容采用 CC BY-NC-SA 4.0。这不授予原始视频或上游源字段的许可。
详见[数据条款](../DATA_TERMS.zh-CN.md)。
来源路径改为描述性溯源 ID。元数据修正不改变标注、答案或其哈希，
但改变 manifest 身份和新运行资格。旧 bundle 保留原 manifest；
使用修订元数据时需新输出目录。

## 发布前

运行 README 的测试、合成答案检查、文档和公开文件扫描、发行包检查。
审阅 diff、数据授权、打包文件及所声明的 GPU/judge 验证，见[验证](release-validation.zh-CN.md)。
不要发布视频、权重、运行 bundle 或本地配置。
Git 只保留选定标注版本；旧本地数据通过忽略规则保留，不删除。
