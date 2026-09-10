# 交互结果看板

[English](results-explorer.md) | 简体中文

下载仓库后，用浏览器打开[英文看板](results/index.html)或
[中文看板](results/index.zh-CN.html)。两份页面均可独立运行，
浏览结果不需要构建、后端、模型服务或网络连接。
GitHub 仓库文件页只展示 HTML 源码，不运行页面；请下载后本地打开，或启用 Pages。

README 保留静态跨任务成绩表和代表性图表。
看板增加模型/比较组筛选、可见列排序、表头点击排序、按任务的能力与运行指标散点图，
以及配置详情。隐藏当前排序列后自动切换到其他可见指标；
隐藏所有指标列则保留不排序的模型列表。
QA 纵轴为准确率，Proactive 纵轴为 SWA 或 TCR；
横轴可选完成率、记录 token、查询阶段时间（QA）和额外响应（Proactive）。
缺失观测不绘入散点图，在表格中保留为 N/A。

## 如何理解结果

看板与[结果说明页](benchmark-results.zh-CN.md)使用同一报告总体，
不是新推理或新算分结果。模型与系统边界分别保留。
跨任务成绩表按 Proactive 边界分组，AURA 的 QA 输入为 Non-native。
粗体表示组内最优观测值（含并列），不代表统计显著性。
报告的 QA 解析不同于 Core 严格默认值；输出 token 为观测总量，不是等价计算成本。

中英文 HTML 内嵌相同数值和交互逻辑。更新结果时，请同步两份页面、
README 成绩表和结果文档，并保留总体、缺失值与来源说明。

## 可选：发布到 GitHub Pages

自行提交并推送文件后，在仓库 **Settings → Pages** 中选择
**Deploy from a branch**，选择包含本次修改的分支及 **/docs** 目录。
看板入口路径为 `/Open-Stream-Bench/results/`；
中文页面相对于项目站点根目录为 `results/index.zh-CN.html`。
本次只添加本地文件，不启用 Pages，不更改分支，也不推送。
