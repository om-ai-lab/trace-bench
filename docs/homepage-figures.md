# Homepage figures

English | [简体中文](homepage-figures.zh-CN.md)

- Evaluation design: [English SVG](assets/results/evaluation-design.en.svg),
  [Chinese SVG](assets/results/evaluation-design.zh-CN.svg). This is a schematic,
  not a model trace. It shows the Core–adapter–model–scoring surfaces, the QA
  video-time and runtime-clock axes with recorded latency landmarks, and a
  Proactive response-window example with early, in-window, redundant and late
  segments. The runtime axis is not aligned to video time; timelines are
  illustrative.
- Execution modes: [English SVG](assets/results/execution-modes.en.svg),
  [Chinese SVG](assets/results/execution-modes.zh-CN.svg). Visual state (native
  persistent state vs. legal-prefix replay), response triggering (autonomous
  vs. polling) and the evaluation boundary (model + adapter vs. complete
  system) are independent declared dimensions, not capability levels.
- Similar scores, different behavior: [English SVG](assets/results/score-versus-behavior.en.svg),
  [Chinese SVG](assets/results/score-versus-behavior.zh-CN.svg). Values are rounded
  report Chapter 5 results, reviewed on 2026-09-10. See
  [result provenance and limits](benchmark-results.md).

All bars start at zero; percentages use a 0–100 reference. Blue is the first
named model in each pair, orange the second. Arrows indicate the preferred
direction of each quantity, not an overall ranking. Fewer tokens alone do not
establish better efficiency. No missing values are estimated. The repetition
ratio uses published rounded counts: 185.6 / 28.4 ≈ 6.5.

## Regenerate

Run from the repository root with Matplotlib and one of Noto Sans CJK SC,
WenQuanYi Zen Hei, or Droid Sans Fallback installed. Ubuntu's `fonts-noto-cjk`
package provides a supported font. SVG fonts are converted to paths for portable
viewing. Plotting is optional; Core does not require Matplotlib.

```bash
python -m pip install 'matplotlib>=3.7'
MPLCONFIGDIR=output/matplotlib-cache python scripts/plot_homepage_figures.py --output output/homepage-preview
```

This writes twelve files: three figures × two languages × PNG/SVG. Inspect previews,
then use the same command with `--output docs/assets/results` to update public
assets. The generator replaces only its own named files.
