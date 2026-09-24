# Homepage figures

English | [简体中文](homepage-figures.zh-CN.md)

- Evaluation design: [paper SVG](assets/results/evaluation-design-report.en.svg)
  and [paper PNG](assets/results/evaluation-design-report.en.png). This is the
  exact current-report schematic, not a public redraw.
- Execution modes: [paper SVG](assets/results/execution-modes-report.en.svg)
  and [paper PNG](assets/results/execution-modes-report.en.png). This is the
  exact current-report schematic, not a public redraw.
- Paper QA quality, response latency and generation workload: [PNG](assets/results/fig_qa_accuracy_workload.png),
  [SVG](assets/results/fig_qa_accuracy_workload.svg). This is the exact checked-in
  paper figure, including both paired QA panels.
- Paper Proactive quality and delay: [PNG](assets/results/fig_proactive_quality_delay.png),
  [SVG](assets/results/fig_proactive_quality_delay.svg). This is the exact paper
  asset, including video-clustered confidence intervals.
- Paper Proactive False-alarm/Miss view: [PNG](assets/results/fig_proactive_fa_miss.png),
  [SVG](assets/results/fig_proactive_fa_miss.svg). False-alarm is the global
  episode-level ratio and Miss is the target-window-level ratio.

The five figures above are copied verbatim from the current LaTeX report
(`fig_qa_accuracy_workload`, `fig_proactive_quality_delay`, and
`fig_proactive_fa_miss`). The report does not provide separate Chinese versions,
so the Chinese page uses the same English paper assets. The public generator below
intentionally does not redraw or overwrite these files. Numerical comparisons and
metric definitions remain in the result tables and the Explorer.

## Verify the checked-in paper assets

All five figures above are copied verbatim from the current LaTeX report. The
public checkout intentionally contains no plotting approximation for them. The
historical `plot_homepage_figures.py` filename is retained as a compatibility
entry point, but the script only verifies the ten checked-in PNG/SVG hashes; it
does not redraw or overwrite any figure.

```bash
python scripts/plot_homepage_figures.py
```

When the manuscript changes, export the new report assets from the LaTeX
checkout, replace the public files together, and update the verifier manifest.
