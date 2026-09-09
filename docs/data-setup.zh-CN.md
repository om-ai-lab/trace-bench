# 数据与视频准备

[English](data-setup.md) | 简体中文

使用 OSB 的 `data/releases/v1.1.0` 标注。按上游条款下载视频，
不要用上游 JSON 替换 OSB 标注。

## 来源

[StreamingBench](https://streamingbench.github.io/)、
[代码仓库](https://github.com/THUNLP-MT/StreamingBench)、
[数据集](https://huggingface.co/datasets/mjuicem/StreamingBench)。
它与名称相近的 StreamBench 不同。按上游 Data Preparation 下载并解压视频。
OSB 使用 `videos/` 下的平铺文件名，例如
`videos/sample_49_Anomaly_Context_Understanding.mp4`。
若视频分在类别子目录中，逐个创建保留记录文件名的软链接。
先检查同名文件，不要任意选择。只需要所选 OSB 子集引用的视频。

[OVO-Bench](https://github.com/joeleelyf/ovo-bench)、
[数据集](https://huggingface.co/datasets/JoeLeelyf/OVO-Bench)。
下载 `src_videos.tar.partaa` 至 `src_videos.tar.partae`，
按字母顺序拼接并根据上游说明解压。
OSB 使用原始时间戳和 `src_videos/`，不能替换为时间戳归零的
`chunked_videos`，不需要运行上游切片脚本。

## 路径映射

视频根目录需有 `videos/` 与 `src_videos/`；
后者包含 `Ego4D/clips/`、`MovieNet/`、`COIN/` 等上游目录。
记录使用相对路径时，Core 和 checker 优先拼接显式的 `--video-root`；
未设置时相对于当前工作目录。绝对路径保持原样。

在 OSB 根目录运行，把每个 `/path/to/...` 换为实际路径：

```bash
mkdir -p /path/to/osb-media
ln -s /path/to/prepared/streamingbench/videos /path/to/osb-media/videos
ln -s /path/to/ovo/data/src_videos /path/to/osb-media/src_videos
osb data validate --release data/releases/v1.1.0
python scripts/check_videos.py --release data/releases/v1.1.0 \
  --video-root /path/to/osb-media --subset tiny
```

软链接命令假定目标链接尚不存在，且 StreamingBench 目录已经按上述规则整理。
视频下载保存在 Git 之外。缺失文件检查给出具体路径，但不测试解码。
全量数据检查使用 `--subset full`。
参见[数据条款](../DATA_TERMS.zh-CN.md)与[数据卡](dataset-card.zh-CN.md)。
