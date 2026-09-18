"""Render bilingual homepage SVG/PNG figures from the report snapshot.

Requires matplotlib>=3.7 and a Chinese font (see docs/homepage-figures.md).
No inference, rescoring, or private analysis files are required.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Rectangle


INK = "#183047"
MUTED = "#52677b"
BLUE = "#1677b8"
ORANGE = "#d47728"
GREEN = "#27836b"
BACKGROUND = "#f3f6fa"

# Rounded published values: technical report Chapter 5, reviewed 2026-09-10.
# Counts are observed workload, not cross-model compute-cost estimates.
QA = [(65.19, 65.07), (93.88, 100.00), (146064, 42206)]
PROACTIVE = [(8.05, 7.92), (185.6, 28.4), (160.2, 188.1)]


def label(ax, x, y, value, size=13, color=INK, weight="normal", **kwargs):
    return ax.text(x, y, value, fontsize=size, color=color, weight=weight,
                   va="center", **kwargs)


def box(ax, x, y, w, h, color=BACKGROUND):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                              boxstyle="round,pad=0.012,rounding_size=0.018",
                              facecolor=color, edgecolor="none"))


def arrow(ax, x1, y1, x2, y2, color=MUTED):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops={"arrowstyle": "->", "color": color, "lw": 1.5})


def save(fig, output, name, lang):
    for extension in ("svg", "png"):
        fig.savefig(output / f"{name}.{lang}.{extension}", dpi=160,
                    facecolor="white", metadata={"Date": None}
                    if extension == "svg" else None)
    plt.close(fig)


def protocol(output, lang):
    zh = lang == "zh-CN"

    def tr(en, cn):
        return cn if zh else en

    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    label(ax, .04, .945, tr("What TRACE measures along a video stream",
                            "TRACE 如何沿视频流评估模型"), 25, weight="bold")
    label(ax, .04, .891, tr("Causal evidence + controlled query timing + traceable outcomes",
                            "因果视觉输入 + 明确的问题时机 + 可追溯的结果"), 15, MUTED)
    for y in (.54, .22):
        box(ax, .035, y, .69, .29)
    box(ax, .765, .22, .195, .61)
    label(ax, .055, .793, "QA", 20, BLUE, "bold")
    label(ax, .125, .793, tr("Question arrives after the history", "先接收历史，再接收问题"), 15)
    label(ax, .055, .705, tr("Video time", "视频时间"), 11, MUTED)
    arrow(ax, .16, .705, .685, .705)
    for x in (.20, .27, .34, .41, .48):
        ax.add_patch(Rectangle((x, .724), .04, .03, color="#a7cce3"))
    ax.plot([.55, .55], [.667, .765], color=BLUE, lw=2)
    label(ax, .55, .65, tr("Unified question", "统一问题"), 12, BLUE, ha="center")
    label(ax, .32, .674, tr("Legal history only", "仅提供合法历史帧"), 12, ha="center")
    label(ax, .065, .58, tr("Runtime logs", "运行耗时"), 11, MUTED)
    label(ax, .22, .60, tr("History processing", "历史处理花销"), 12, BLUE)
    label(ax, .22, .566, tr("calls / tokens / frames", "调用 / token / 帧"), 10, MUTED)
    arrow(ax, .43, .587, .49, .587, BLUE)
    label(ax, .51, .60, tr("Query → answer", "问题 → 回答"), 12, BLUE)
    label(ax, .51, .566, tr("TTFT / completion time", "TTFT / 回答完成时间"), 10, MUTED)

    label(ax, .055, .503, "Proactive", 20, GREEN, "bold")
    label(ax, .21, .503, tr("One instruction, then monitor", "先给一次指令，随后持续监测"), 15)
    ax.add_patch(Rectangle((.40, .32), .16, .115, color="#d6eee4"))
    label(ax, .48, .417, tr("Valid window", "合法响应窗口"), 11, GREEN, ha="center")
    arrow(ax, .16, .353, .69, .353)
    for x in (.21, .27, .33, .39, .45, .51, .57, .63):
        ax.add_patch(Rectangle((x, .376), .023, .014, color="#a7cce3"))
    ax.plot([.17, .17], [.332, .448], color=GREEN, lw=2)
    label(ax, .17, .464, tr("Instruction", "指令"), 11, GREEN, ha="center")
    ax.plot([.40, .40], [.32, .395], color=GREEN, lw=2)
    label(ax, .40, .301, tr("GT trigger", "GT 触发"), 11, GREEN, ha="center")
    for x, text, color in [(.29, tr("Early", "提前"), ORANGE),
                           (.44, tr("Correct", "正确"), GREEN),
                           (.52, tr("Repeat", "重复"), ORANGE),
                           (.64, tr("Late", "迟到"), ORANGE)]:
        ax.plot(x, .353, "o", color=color, ms=7)
        label(ax, x, .278, text, 11, color, ha="center")
    label(ax, .055, .238, tr("Illustrative events; late output is outside the strict window.",
                            "示意输出；迟到回答不计入严格窗口得分。"), 10, MUTED)

    arrow(ax, .724, .685, .758, .685)
    arrow(ax, .724, .366, .758, .366)
    label(ax, .785, .783, tr("Recorded outcomes", "结果与记账"), 16, weight="bold")
    for y, en, cn, note_en, note_cn in [
        (.704, "Quality", "内容质量", "QA / window score", "QA / 窗口得分"),
        (.606, "Timeliness", "响应及时性", "TTFT / response onset", "TTFT / 响应开始时间"),
        (.508, "Extra responses", "额外响应", "Outside / redundant", "窗口外 / 重复"),
        (.410, "Workload", "工作量", "History + answering", "历史处理 + 回答"),
        (.312, "Reliability", "运行可靠性", "Completion / failures", "完成率 / 失败")]:
        label(ax, .785, y, tr(en, cn), 14, weight="bold")
        label(ax, .785, y-.031, tr(note_en, note_cn), 10, MUTED)
    label(ax, .04, .168, tr("Declare two independent execution dimensions", "独立声明两个执行维度"), 15, weight="bold")
    label(ax, .04, .118, tr("Visual state: persistent reuse / history replay",
                            "视觉状态：持续复用 / 历史重放"), 13)
    label(ax, .51, .118, tr("Proactive trigger: autonomous / external polling",
                            "主动触发：模型自主 / 外部 polling"), 13)
    label(ax, .04, .053, tr("Video timestamps define evidence and windows. Monotonic runtime clocks measure cost and latency.",
                            "视频时间定义证据与窗口；单调运行时钟记录花销与延迟。"), 11, MUTED)
    save(fig, output, "evaluation-design", lang)


def findings(output, lang):
    zh = lang == "zh-CN"

    def tr(en, cn):
        return cn if zh else en

    fig = plt.figure(figsize=(16, 9))
    canvas = fig.add_axes((0, 0, 1, 1))
    canvas.set(xlim=(0, 1), ylim=(0, 1))
    canvas.axis("off")
    label(canvas, .04, .95, tr("Similar scores. Different operating behavior.",
                              "相近任务得分，隐藏不同运行表现"), 25, weight="bold")
    label(canvas, .04, .897, tr("Measured report configurations · quality, reliability and response behavior",
                              "报告受测配置 · 联合观察质量、可靠性与响应行为"), 15, MUTED)
    panels = [(.04, "QA", ("LiveCC", "MOSS-Preview"), QA,
               [(tr("Recoverable accuracy (%) ↑", "Recoverable 准确率（%）↑"), 100, 2),
                (tr("Record completion (%) ↑", "记录完成率（%）↑"), 100, 2),
                (tr("Recorded output tokens ↓", "记录输出 token ↓"), 160000, 0)]),
              (.54, "Proactive", ("MOSS-VL", "AURA"), PROACTIVE,
               [(tr("Strict window accuracy (%) ↑", "严格窗口得分（%）↑"), 100, 2),
                (tr("Redundant responses / 100 windows ↓", "重复响应 / 每百窗口 ↓"), 200, 1),
                (tr("Outside-window responses / 100 windows ↓", "窗口外响应 / 每百窗口 ↓"), 200, 1)])]
    for left, title, names, data, metrics in panels:
        label(canvas, left, .832, title, 19, weight="bold")
        for i, name in enumerate(names):
            label(canvas, left+.12+i*.17, .832, name, 13, [BLUE, ORANGE][i])
        for index, ((metric, maximum, precision), values) in enumerate(zip(metrics, data)):
            top = .76-index*.18
            label(canvas, left, top, metric, 13, weight="bold")
            axis = fig.add_axes((left+.015, top-.117, .39, .093))
            axis.barh([1, 0], values, height=.53, color=[BLUE, ORANGE])
            axis.set(xlim=(0, maximum*1.27), ylim=(-.5, 1.5), yticks=[])
            axis.set_xticks([0, maximum])
            axis.set_xticklabels(["0", f"{maximum:,}"], color=MUTED, fontsize=9)
            axis.tick_params(axis="x", length=0)
            for spine in axis.spines.values():
                spine.set_visible(False)
            axis.axvline(0, color="#cbd5df", lw=1)
            for y, value in zip([1, 0], values):
                axis.text(value+maximum*.018, y, f"{value:,.{precision}f}",
                          va="center", fontsize=12, color=INK)
        box(canvas, left, .185, .42, .061)
        label(canvas, left+.012, .216,
              tr("Near-equal accuracy; different completion and output volume.",
                 "准确率接近，完成率和生成量不同。") if title == "QA" else
              tr("6.5× repetition gap; outside-window counts favor MOSS-VL.",
                 "重复相差约 6.5 倍；MOSS-VL 窗口外输出更少。"), 11)
    label(canvas, .04, .128, tr("QA: 833 records, recoverable parser. Proactive: 1,270 standard windows, W=5s. All bars start at zero.",
                              "QA：833 条，宽松唯一标签解析。Proactive：1,270 个标准窗口，W=5s。所有条形从零开始。"), 11, MUTED)
    label(canvas, .04, .088, tr("Tokens are observed generation, not equal compute cost. Response counts are not probabilities. Descriptive comparisons.",
                              "token 为已记录生成量，不是等价计算成本；响应次数不是概率。图中为描述性比较。"), 11, MUTED)
    label(canvas, .04, .048, tr("AURA: autonomous output; native visual state unverified. Data lineage and measurement limits: docs/benchmark-results.md",
                              "AURA 自主输出，其原生视觉状态待核验。数据来源与测量边界见结果说明页。"), 10, MUTED)
    save(fig, output, "score-versus-behavior", lang)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/assets/results"))
    args = parser.parse_args()
    candidates = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "Droid Sans Fallback"]
    available = {font.name for font in font_manager.fontManager.ttflist}
    chinese = next((name for name in candidates if name in available), None)
    if chinese is None:
        parser.error("install Noto Sans CJK SC or WenQuanYi Zen Hei for Chinese figures")
    matplotlib.rcParams.update({"font.family": ["DejaVu Sans", chinese],
                                "svg.fonttype": "path", "svg.hashsalt": "osb-homepage-v1"})
    args.output.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "zh-CN"):
        protocol(args.output, lang)
        findings(args.output, lang)


if __name__ == "__main__":
    main()
