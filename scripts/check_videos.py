"""Check selected release video paths without decoding or loading a model."""

import argparse
from pathlib import Path

from trace_bench.data import load_release, validate_release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--video-root", type=Path, required=True)
    parser.add_argument("--subset", choices=("tiny", "full"), default="tiny")
    args = parser.parse_args()
    validate_release(args.release)
    release = load_release(args.release)
    records = release.qa + release.proactive
    if args.subset == "tiny":
        import json

        ids = set()
        for name in (release.manifest.tiny_qa_ids_file, release.manifest.tiny_proactive_ids_file):
            ids.update(json.loads((args.release / name).read_text(encoding="utf-8")))
        records = [record for record in records if record.record_id in ids]
    paths = sorted({args.video_root / record.video_path for record in records})
    missing = [path for path in paths if not path.is_file()]
    for path in missing:
        print(f"MISSING {path}")
    print(f"{len(paths) - len(missing)}/{len(paths)} video files present")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
