# 首页图表

[English](homepage-figures.md) | 简体中文

- 评估设计：[英文 SVG](assets/results/evaluation-design.en.svg)、
  [中文 SVG](assets/results/evaluation-design.zh-CN.svg)。这是机制示意，
  不是模型轨迹。图示包含 Core–适配器–模型–打分各环节、QA 的视频时间与
  运行时钟双轴及记录的时延标记、以及含提前、窗口内、冗余、迟到片段的
  Proactive 响应窗口示例。运行轴不与视频时间对齐；时间轴为示意。
- 执行模式：[英文 SVG](assets/results/execution-modes.en.svg)、
  [中文 SVG](assets/results/execution-modes.zh-CN.svg)。视觉状态（原生持续
  状态 / 合法前缀重放）、响应触发（自主 / 轮询）与评测边界（模型 + 适配器 /
  完整系统）是相互独立的声明维度，不是能力等级。
- 相近得分、不同表现：[英文 SVG](assets/results/score-versus-behavior.en.svg)、
  [中文 SVG](assets/results/score-versus-behavior.zh-CN.svg)。数值为技术报告
  第五章的舍入结果，核对日期为 2026-09-10。
  详见[结果来源与限制](benchmark-results.zh-CN.md)。

所有条形从零开始；百分比使用 0–100 参考范围。蓝色为每组先列出的模型，
橙色为后列出的模型。箭头表示该指标的偏好方向，不是综合排名。
仅凭 token 更少不能确立效率优势。不估算缺失值。
重复响应倍数来自公布的舍入次数：185.6 / 28.4 ≈ 6.5。

## 重新生成

在仓库根目录执行，环境需要 Matplotlib，系统需安装 Noto Sans CJK SC、
WenQuanYi Zen Hei 或 Droid Sans Fallback 中任一字体。
Ubuntu 的 `fonts-noto-cjk` 包提供支持的字体。
SVG 将字体转为路径，方便跨环境查看。绘图是可选功能，Core 不依赖 Matplotlib。

```bash
python -m pip install 'matplotlib>=3.7'
MPLCONFIGDIR=output/matplotlib-cache python scripts/plot_homepage_figures.py --output output/homepage-preview
```

生成十二个文件：三张图 × 两种语言 × PNG/SVG。检查预览后，
使用相同命令并改为 `--output docs/assets/results` 更新公开资源。
生成器只替换自己命名的文件。
