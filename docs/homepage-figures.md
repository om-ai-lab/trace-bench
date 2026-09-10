# Homepage figures

English | [简体中文](homepage-figures.zh-CN.md)

- Evaluation design: [English SVG](assets/results/evaluation-design.en.svg),
  [Chinese SVG](assets/results/evaluation-design.zh-CN.svg). This is a schematic,
  not a model trace. It shows an intermediate Proactive window; later frames do
  not imply processing beyond the final evaluation boundary. QA history may be
  processed before or at query time depending on execution mode; both history
  and answering costs are recorded. The runtime row is not aligned to video time.
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

This writes eight files: two figures × two languages × PNG/SVG. Inspect previews,
then use the same command with `--output docs/assets/results` to update public
assets. The generator replaces only its own named files.
