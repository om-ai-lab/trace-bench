"""Check selected release video paths without decoding or loading a model."""

import argparse
from pathlib import Path

from trace_bench.data import load_release, validate_release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--video-root", type=Path, required=True)
    parser.add_argument("--subset", choices=("tiny", "full", "all", "standard"), default="tiny")
    args = parser.parse_args()
    validate_release(args.release)
    release = load_release(args.release)
    records = release.records("qa", args.subset) + release.records("proactive", args.subset)
    paths = sorted({args.video_root / record.video_path for record in records})
    missing = [path for path in paths if not path.is_file()]
    for path in missing:
        print(f"MISSING {path}")
    print(f"{len(paths) - len(missing)}/{len(paths)} video files present")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
