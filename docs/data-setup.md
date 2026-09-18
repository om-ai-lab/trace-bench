# Data and video setup

English | [简体中文](data-setup.zh-CN.md)

Use TRACE's `data/releases/v1.1.0` annotations. Download videos from the upstream
providers under their terms; do not replace TRACE annotations with upstream JSON.

## Sources

[StreamingBench](https://streamingbench.github.io/),
[repository](https://github.com/THUNLP-MT/StreamingBench),
[dataset](https://huggingface.co/datasets/mjuicem/StreamingBench).
This is different from the similarly named StreamBench.
Follow upstream Data Preparation to extract its video archives.
TRACE uses `videos/` with flat names such as
`videos/sample_49_Anomaly_Context_Understanding.mp4`.
If archives have category subdirectories, create individual symlinks preserving
the exact recorded filenames. Check duplicate basenames rather than arbitrarily
choosing a file. Only files referenced by your TRACE subset are needed.

[OVO-Bench](https://github.com/joeleelyf/ovo-bench),
[dataset](https://huggingface.co/datasets/JoeLeelyf/OVO-Bench).
Download `src_videos.tar.partaa` through `src_videos.tar.partae`,
concatenate in alphabetical order and extract per upstream instructions.
TRACE uses original timestamps and `src_videos/`.
Do not substitute timestamp-reset `chunked_videos`; upstream chunking is unnecessary.

## Map paths

The video root exposes `videos/` and `src_videos/`, with the latter containing
upstream trees such as `Ego4D/clips/`, `MovieNet/` and `COIN/`.
For relative record paths, Core and checker prepend the explicit `--video-root`.
Without it they resolve against the current directory. Absolute paths stay absolute.

Run from the TRACE root. Replace every `/path/to/...` with your actual location:

```bash
mkdir -p /path/to/trace-media
ln -s /path/to/prepared/streamingbench/videos /path/to/trace-media/videos
ln -s /path/to/ovo/data/src_videos /path/to/trace-media/src_videos
trace data validate --release data/releases/v1.1.0
python scripts/check_videos.py --release data/releases/v1.1.0 \
  --video-root /path/to/trace-media --subset tiny
```

The symlink commands assume those links do not already exist and that the
StreamingBench tree has been prepared as described above. Keep video downloads
outside Git. Missing-file checks report exact paths but do not test decoding.
Use `--subset full` for the full dataset.
See [data terms](../DATA_TERMS.md) and [dataset card](dataset-card.md).
