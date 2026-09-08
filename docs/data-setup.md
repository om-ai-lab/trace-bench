# Data and video setup

OSB ships one annotation snapshot, `data/releases/v1.1.0`. Download videos
directly from the original providers, accept their terms, and keep them outside
the Git checkout. Do not replace OSB annotations with upstream annotations.

## StreamingBench

Use [StreamingBench](https://streamingbench.github.io/), its
[repository](https://github.com/THUNLP-MT/StreamingBench), and its
[dataset](https://huggingface.co/datasets/mjuicem/StreamingBench).
The similarly named [StreamBench](https://stream-bench.github.io/) is a
different benchmark and is not the source of OSB's video annotations.

Follow upstream Data Preparation to download and extract the video archives.
Upstream organizes videos under `StreamingBench/data/{real,omni,sqa,proactive}`.
OSB records use paths beginning with `videos/`; keep the recorded suffixes when
mapping the extracted files. Archive nesting can differ, so check the actual
paths before starting inference. Only the videos referenced by the selected
OSB subset are needed.

OSB uses flat names such as `videos/sample_49_Anomaly_Context_Understanding.mp4`.
If extraction leaves them in category subdirectories, create individual
symlinks in your `osb-media/videos/` directory matching those names. Match exact
filenames and check duplicate basenames before linking; never arbitrarily
choose between different videos with the same name. No upstream model
inference/preprocessing script is needed for OSB frame extraction.

## OVO-Bench

Follow [OVO-Bench Data Preparation](https://github.com/joeleelyf/ovo-bench)
and download `src_videos.tar.partaa` through `src_videos.tar.partae` from the
[dataset page](https://huggingface.co/datasets/JoeLeelyf/OVO-Bench).
Concatenate the parts in alphabetical order and extract the resulting tar
archive outside this checkout, following upstream instructions.

OSB uses `src_videos/` and original-video timestamps. Its Core extracts frames,
so the upstream `chunked_videos` download and chunking script are unnecessary.
Do not substitute timestamp-reset clips for the original source videos.

## Local mapping

`--video-root` is a single directory prepended to each record's `video_path`.
It should expose both upstream trees, for example:

```text
/path/to/osb-media/
  videos/                   # StreamingBench files, preserving OSB suffixes
  src_videos/
    Ego4D/clips/
    MovieNet/
    COIN/
    ...
```

Run from a checkout without a second `videos/` or `src_videos/` tree: Core's
legacy path resolver prefers a matching file in the working directory before
using `--video-root`. The checker verifies the explicit root shown here.

Use symlinks to existing downloads instead of making another video copy:

```bash
mkdir -p /path/to/osb-media
ln -s /path/to/prepared/streamingbench/videos /path/to/osb-media/videos
ln -s /path/to/ovo/data/src_videos /path/to/osb-media/src_videos
osb data validate --release data/releases/v1.1.0
python scripts/check_videos.py --release data/releases/v1.1.0 \
  --video-root /path/to/osb-media --subset tiny
```

Replace paths with your actual extraction locations. `check_videos.py` reports
the exact missing paths; it checks file presence, not decode integrity or
permission to redistribute. Full evaluation uses `--subset full` for this check.
The two download sources above were checked on 2026-09-08.

See [data terms](../DATA_TERMS.md) and the [dataset card](dataset-card.md).
