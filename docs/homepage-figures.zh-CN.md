# 首页图表

[English](homepage-figures.md) | 简体中文

- 评估设计：[论文 SVG](assets/results/evaluation-design-report.en.svg)、
  [论文 PNG](assets/results/evaluation-design-report.en.png)。这是当前报告的
  原始机制示意，不是公开仓库重新绘制的版本。
- 执行模式：[论文 SVG](assets/results/execution-modes-report.en.svg)、
  [论文 PNG](assets/results/execution-modes-report.en.png)。这是当前报告的
  原始执行条件图。
- 论文 QA 质量、响应时延与生成工作量：[PNG](assets/results/fig_qa_accuracy_workload.png)、
  [SVG](assets/results/fig_qa_accuracy_workload.svg)。这是论文中包含两个 QA
  对照面板的原图。
- 论文 Proactive 质量与延迟：[PNG](assets/results/fig_proactive_quality_delay.png)、
  [SVG](assets/results/fig_proactive_quality_delay.svg)。该原图包含视频聚类
  置信区间。
- 论文 Proactive 误报/漏报图：[PNG](assets/results/fig_proactive_fa_miss.png)、
  [SVG](assets/results/fig_proactive_fa_miss.svg)。误报率按全局响应 episode
  计算，漏报率按目标窗口计算。

上面的五张图直接复制自当前 LaTeX 报告（`fig_qa_accuracy_workload`、
`fig_proactive_quality_delay` 和 `fig_proactive_fa_miss`），没有再次绘制。
由于论文没有单独的中文版本，中文页面与英文页面共用论文原始英文图。
下面的公开生成器不会重画或覆盖这些文件。数值比较和指标定义见结果表与 Explorer。

## 校验仓库中的论文原图

上面的五张图都直接复制自当前 LaTeX 报告，公开仓库不再保留重新绘制的近似图。
历史上的 `plot_homepage_figures.py` 文件名作为兼容入口保留，但脚本只校验十个已提交
PNG/SVG 文件的哈希，不会重画或覆盖任何图。

```bash
python scripts/plot_homepage_figures.py
```

论文更新时，应从 LaTeX checkout 导出新原图，一起替换公开文件，并同步更新校验脚本中的清单。
