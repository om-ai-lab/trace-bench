"""Render bilingual homepage SVG/PNG figures from the report snapshot.

Requires matplotlib>=3.7 and a Chinese font (see docs/homepage-figures.md).
No inference, rescoring, or private analysis files are required.
The evaluation-design and execution-modes schematics are the report review
diagrams, kept bilingual and regenerable from this script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


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


def assert_unclipped(fig, ax):
    """Fail instead of silently shipping text outside the figure."""

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for item in ax.texts:
        bounds = item.get_window_extent(renderer)
        if not fig.bbox.contains(bounds.x0, bounds.y0) or not fig.bbox.contains(
            bounds.x1, bounds.y1
        ):
            raise ValueError(f"Clipped text: {item.get_text()}")


def evaluation_design(output, lang):
    zh = lang == "zh-CN"

    def tr(en, cn):
        return cn if zh else en

    ink, muted = "#17324d", "#52677e"
    blue, green, orange = "#247ac2", "#168673", "#d97420"
    purple, red = "#7853b4", "#c35059"
    fig, ax = plt.subplots(figsize=(18, 12))
    fig.subplots_adjust(left=0.015, right=0.985, top=0.985, bottom=0.015)
    ax.set(xlim=(0, 100), ylim=(24, 100))
    ax.axis("off")

    def text(x, y, value, size=11, color=ink, weight="normal", ha="left"):
        return ax.text(x, y, value, fontsize=size, color=color, weight=weight,
                       ha=ha, va="center", linespacing=1.4)

    def rbox(x, y, w, h, fill):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8",
            facecolor=fill, edgecolor="none"))

    def farrow(x1, y1, x2, y2, color=muted, style="->", lw=1.5):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                     mutation_scale=12, color=color, linewidth=lw))

    def line(x1, y1, x2, y2, color=muted, dashed=False):
        ax.plot([x1, x2], [y1, y2], color=color, lw=1.3,
                linestyle="--" if dashed else "-")

    def span(x1, x2, y, caption, color, label_y=None):
        farrow(x1, y, x2, y, color, "<->")
        text((x1 + x2) / 2, y + 1 if label_y is None else label_y,
             caption, 10.5, color, ha="center")

    text(2, 98, tr("TRACE: from causal video input to multidimensional evaluation",
                   "TRACE：从因果视频输入到多维度评估"), 23, weight="bold")
    text(2, 95.5, tr("Shared task timelines  •  explicit interaction tracks  •  "
                     "linked quality, timing, behavior and workload",
                     "共享任务时间轴  •  明确的交互轨道  •  关联的质量、时延、行为与工作量"),
         12, muted)

    # Architecture: control and measurement surfaces, not a model architecture.
    stages = [
        (2, 21, "Evaluation Core", "评测 Core",
         tr("Timestamped frames + tasks\nCausal access • fixed delivery rules",
            "带时间戳的帧与任务\n因果访问 • 固定投递规则"), "#e8f2fc", blue),
        (27, 21, "Model Adapter", "模型适配器",
         tr("State reuse / legal-history replay\nCalls • images • tokens • failures",
            "状态复用 / 合法历史重放\n调用 • 图像 • token • 失败"), "#f0eafb", purple),
        (52, 21, "Model / system", "模型 / 系统",
         tr("Answers + response segments\nFirst-token and completion events",
            "回答与响应片段\n首 token 与完成事件"), "#e5f5ef", green),
        (77, 21, "Scoring + reporting", "打分与报告",
         tr("Reference content + time windows\nCompare within declared conditions",
            "参考内容 + 时间窗口\n在声明的条件内比较"), "#fff2df", orange),
    ]
    for x, w, title, title_cn, subtitle, fill, color in stages:
        rbox(x, 87.5, w, 6.3, fill)
        text(x + 1.2, 92, tr(title, title_cn), 12, color, "bold")
        text(x + 1.2, 89.4, subtitle, 9.5)
    for x in (23, 48, 73):
        farrow(x + 0.3, 90.6, x + 3.5, 90.6)

    # QA has separate video-time and runtime axes.
    rbox(2, 57, 96, 28.7, "#f1f6fc")
    text(4, 83.8, tr("QA: what is known when the question arrives?",
                     "QA：问题到达时模型已知道什么？"), 16, blue, "bold")
    text(4, 81.4, tr("Video time", "视频时间"), 10, muted)
    farrow(19, 80, 93, 80)
    for x in (22, 28, 34, 40, 46, 52, 58):
        ax.add_patch(Rectangle((x, 80.8), 3.5, 1.1, color="#a6cee8", ec="none"))
    line(64, 78.9, 64, 82.5, blue)
    text(65, 81.7, tr("Question + options at video time q",
                      "视频时间 q 处的问题与选项"), 11, blue, "bold")
    text(39, 78.6, tr("Only frames available by q are legal evidence",
                      "仅 q 之前可用的帧是合法证据"), 10, ha="center")
    text(80, 78.6, tr("Future video excluded", "排除未来视频"), 10, muted, ha="center")

    text(4, 75, tr("Runtime clock", "运行时钟"), 10, muted)
    text(4, 73.3, tr("(elapsed seconds)", "（流逝秒数）"), 9, muted)
    farrow(19, 72, 93, 72)
    for x, w, fill, caption in [
        (20, 13, "#dce8f8", tr("History processing", "历史处理")),
        (34, 23, "#e5dcf3", tr("Input preparation / queueing", "输入准备 / 排队")),
        (58, 13, "#d6eaf9", tr("Prefill / decoding", "预填充 / 解码")),
        (72, 18, "#cdece2", tr("Answer generation", "答案生成")),
    ]:
        rbox(x, 72.6, w, 2.7, fill)
        text(x + w / 2, 73.95, caption, 9, ha="center")
    for x, caption, color in [
        (34, tr("$r_q$\nCore question arrival", "$r_q$\nCore 发出问题"), blue),
        (58, tr("$r_{rec}$\nRecorded query start", "$r_{rec}$\n记录的查询开始"), purple),
        (72, tr("$r_1$\nFirst output token", "$r_1$\n首个输出 token"), green),
        (90, tr("$r_{end}$\nCompletion received", "$r_{end}$\n收到完整回答"), green),
    ]:
        line(x, 71.7, x, 75.6, color, True)
        text(x, 70.5, caption, 9, color, ha="center")
    span(58, 72, 66.5, tr("TTFT: query start → first token",
                          "TTFT：查询开始 → 首 token"), purple)
    span(34, 90, 61.5, tr("End-to-end query completion latency",
                          "端到端查询完成时延"), green)
    # Proactive point-window example with a gap before the next trigger.
    rbox(2, 26, 96, 29.5, "#eff8f4")
    text(4, 53.5, tr("Proactive Response: what to say, and when to say it",
                     "主动响应：说什么，何时说"), 16, green, "bold")
    text(4, 51.2, tr("Video time → instruction-dependent response-window assignment",
                     "视频时间 → 依指令分配的响应窗口"), 10, muted)
    for x, w, fill in [(19, 27, "#fbe7e5"), (46, 32, "#c5eadb"), (78, 15, "#fbe7e5")]:
        ax.add_patch(Rectangle((x, 42), w, 7.4, color=fill, ec="none"))
    text(32, 48, tr("OUTSIDE WINDOW", "窗口外"), 10, red, "bold", ha="center")
    text(62, 48, tr("VALID RESPONSE WINDOW", "合法响应窗口"), 11, green, "bold", ha="center")
    text(86, 48, tr("OUTSIDE", "窗口外"), 10, red, "bold", ha="center")
    farrow(17, 44.5, 95, 44.5)
    for x, caption, color in [
        (19, tr("Monitoring\ninstruction", "监测\n指令"), purple),
        (46, tr("Event\ntrigger", "事件\n触发"), green),
        (78, tr("Response\ndeadline", "响应\n截止"), green),
    ]:
        line(x, 41.5, x, 46.6, color)
        text(x, 40.4, caption, 9.5, color, ha="center")
    for x, caption, color in [
        (33, tr("Early", "提前"), red),
        (54, tr("In-window\nanswer", "窗口内\n回答"), green),
        (67, tr("Redundant\nanswer", "冗余\n回答"), orange),
        (86, tr("Late", "迟到"), red),
    ]:
        ax.scatter([x], [44.5], s=75, color=color, zorder=5, edgecolors="white")
        text(x, 46.4, caption, 9, color, ha="center")
    span(46, 54, 37.7, tr("Response-onset delay", "响应开始延迟"), green, 36.5)
    text(4, 33.9, tr("Window rule", "窗口规则"), 10, green, "bold")
    text(19, 33.9, tr("Point events: tolerance limit or next trigger, whichever "
                      "comes first; the endpoint is excluded.",
                      "点事件：取容忍上限或下一触发中较早者；端点不计入。"), 11)
    text(4, 31.5, tr("Assignment", "判定方式"), 10, green, "bold")
    text(19, 31.5, tr("Each dot = segment onset (first token); content is judged "
                      "separately. In-window does not imply correct.",
                      "每个点 = 片段开始（首 token）；内容单独评判。窗口内不等于正确。"), 10)
    text(4, 29.1, tr("State tasks", "状态任务"), 10, green, "bold")
    text(19, 29.1, tr("Use the annotated interval during which the target state "
                      "remains valid.",
                      "使用标注的、目标状态持续有效的区间。"), 10)
    text(4, 27.2, tr("Video timestamps define evidence and windows; aligned runtime "
                     "clocks measure latency. Timelines are schematic.",
                     "视频时间戳定义证据与窗口；对齐的运行时钟度量时延。时间轴为示意图。"),
         9, muted)
    assert_unclipped(fig, ax)
    save(fig, output, "evaluation-design", lang)


def execution_modes(output, lang):
    zh = lang == "zh-CN"

    def tr(en, cn):
        return cn if zh else en

    ink, gray = "#183447", "#617482"
    blue, green, orange, purple = "#247ac2", "#168673", "#cf771f", "#8056ac"
    fig, ax = plt.subplots(figsize=(16, 12))
    fig.subplots_adjust(left=0.025, right=0.975, top=0.975, bottom=0.025)
    ax.set(xlim=(0, 100), ylim=(0, 100))
    ax.axis("off")

    def text(x, y, value, size=11, color=ink, bold=False, ha="left"):
        return ax.text(x, y, value, fontsize=size, color=color,
                       weight="bold" if bold else "normal", ha=ha, va="center",
                       linespacing=1.35)

    def rect(x, y, w, h, fill):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor="none"))

    def farrow(x, y, xx, yy, color=gray):
        ax.add_patch(FancyArrowPatch((x, y), (xx, yy), arrowstyle="->",
                                     mutation_scale=13, lw=1.5, color=color))

    def node(x, y, w, value, color=blue, fill="#dfedf9"):
        rect(x, y - 2.2, w, 4.4, fill)
        text(x + w / 2, y, value, 11, color, True, "center")

    text(1, 97, tr("TRACE execution modes: independent comparison dimensions",
                   "TRACE 执行模式：相互独立的比较维度"), 22, bold=True)
    text(1, 93.8, tr("How video is processed, who initiates an answer, and what "
                     "is included in the evaluated system",
                     "视频如何被处理、谁来发起回答、被评测系统包含哪些部分"), 12, gray)
    text(1, 89.5, tr("VISUAL STATE  |  What happens when new frames arrive?",
                     "视觉状态  |  新帧到来时发生什么？"), 15, blue, True)
    rect(1, 65.5, 47, 21, "#eef5fc")
    rect(51, 65.5, 47, 21, "#f3eef9")
    text(3, 83.5, tr("Native Streaming", "原生流式"), 14, blue, True)
    text(53, 83.5, tr("Non-native Streaming", "非原生流式"), 14, purple, True)
    for x, frame, state in [(5, tr("Frame 1", "帧 1"), tr("State 1", "状态 1")),
                            (20, tr("Frame 2", "帧 2"), tr("State 2", "状态 2")),
                            (35, tr("Frame 3", "帧 3"), tr("State 3", "状态 3"))]:
        node(x, 78, 10, frame)
        farrow(x + 5, 75.5, x + 5, 74)
        node(x, 71.5, 10, state, green, "#cfeade")
    farrow(15, 71.5, 20, 71.5, green)
    farrow(30, 71.5, 35, 71.5, green)
    text(3, 67.3, tr("New frames update persistent internal state.",
                     "新帧更新持续的内部状态。"))
    node(54, 78, 22, tr("Query 1: frames 1–2", "查询 1：帧 1–2"), purple, "#e6dcf1")
    node(54, 71.5, 22, tr("Query 2: frames 1–3", "查询 2：帧 1–3"), purple, "#e6dcf1")
    for y in [78, 71.5]:
        farrow(76, y, 81, y, purple)
        node(81, y, 14, tr("Model call", "模型调用"), purple, "#e6dcf1")
    text(53, 67.3, tr("Rebuild a legal prefix / window for each query.",
                      "为每次查询重建合法前缀 / 窗口。"))

    text(1, 62, tr("RESPONSE TRIGGERING  |  Who decides when to answer?",
                   "响应触发  |  谁决定何时回答？"), 15, green, True)
    rect(1, 38, 47, 21.5, "#edf7f2")
    rect(51, 38, 47, 21.5, "#fff5e9")
    text(3, 56.5, tr("Autonomous", "自主触发"), 14, green, True)
    text(53, 56.5, tr("Polling", "轮询"), 14, orange, True)
    node(3, 50.5, 13, tr("Instruction", "指令"), green, "#cfeade")
    farrow(16, 50.5, 20, 50.5, green)
    node(20, 50.5, 25, tr("Model monitors video", "模型监测视频"), green, "#cfeade")
    farrow(32.5, 48, 32.5, 45.4, green)
    node(20, 43, 25, tr("Self-timed response", "自行定时响应"), green, "#cfeade")
    text(3, 39.5, tr("No periodic external query is needed.",
                     "无需周期性外部查询。"))
    farrow(54, 49.5, 95, 49.5, orange)
    for x, caption in [(59, tr("Query 1", "查询 1")), (74, tr("Query 2", "查询 2")),
                       (89, tr("Query 3", "查询 3"))]:
        text(x, 52.3, caption, 11, orange, ha="center")
        ax.scatter([x], [49.5], marker="D", color=orange, s=45)
        farrow(x, 48.5, x, 45, orange)
        text(x, 43.5, tr("Response", "响应"), 10, ha="center")
    text(53, 39.5, tr("The evaluator initiates periodic checks.",
                      "由评测方发起周期性检查。"))

    text(1, 34.5, tr("EVALUATION BOUNDARY  |  Which components contribute to "
                     "the result?", "评测边界  |  哪些部分计入结果？"), 15, purple, True)
    rect(1, 11, 47, 21, "#f1f4f8")
    rect(51, 11, 47, 21, "#f1f4f8")
    text(3, 29, tr("Model + Adapter", "模型 + 适配器"), 14, blue, True)
    text(53, 29, tr("Complete system", "完整系统"), 14, purple, True)
    rect(3, 17, 43, 8, "white")
    node(5, 21, 16, tr("Adapter", "适配器"))
    farrow(21, 21, 27, 21)
    node(27, 21, 16, tr("Model", "模型"))
    rect(53, 16, 43, 9, "white")
    node(54, 20.5, 12, tr("Memory", "记忆"), purple, "#eee6f6")
    node(69, 20.5, 12, tr("Scheduler", "调度器"), purple, "#eee6f6")
    node(84, 20.5, 11, tr("Model(s)", "模型"), purple, "#eee6f6")
    farrow(66, 20.5, 69, 20.5, purple)
    farrow(81, 20.5, 84, 20.5, purple)
    text(3, 13.3, tr("Model behavior under the selected adaptation.",
                     "所选适配方式下的模型行为。"))
    text(53, 13.3, tr("External memory and orchestration are included.",
                      "外部记忆与编排计入其中。"))
    text(1, 7.5, tr("Independent choices: persistent state can use polling; a "
                    "complete system can contain native streaming models.",
                    "独立选择：持续状态可配合轮询；完整系统也可包含原生流式模型。"),
         11, bold=True)
    text(1, 4.4, tr("Deployment is declared separately: direct weights / local "
                    "service / remote API / edge device.",
                    "部署方式单独声明：直接权重 / 本地服务 / 远程 API / 边缘设备。"), 11, gray)
    text(1, 1.7, tr("Execution categories define comparison conditions, not "
                    "capability levels. Diagrams show representative patterns.",
                    "执行类别定义比较条件，而非能力等级。图示为代表性模式。"), 11, gray)
    assert_unclipped(fig, ax)
    save(fig, output, "execution-modes", lang)


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
        parser.error("install Noto Sans CJK or WenQuanYi Zen Hei for Chinese figures")
    matplotlib.rcParams.update({"font.family": ["DejaVu Sans", chinese],
                                "svg.fonttype": "path", "svg.hashsalt": "trace-homepage-v1"})
    args.output.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "zh-CN"):
        evaluation_design(args.output, lang)
        execution_modes(args.output, lang)
        findings(args.output, lang)


if __name__ == "__main__":
    main()
