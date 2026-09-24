"""Verify homepage assets copied verbatim from the current LaTeX report.

The historical filename is kept for compatibility with older checkout notes.
This public repository does not redraw report figures: the checked-in PNG/SVG
files are the publication assets and this script only verifies their hashes.
The manuscript source is the authority for producing a future revision.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_DIR = ROOT / "docs" / "assets" / "results"

# These hashes are the current LaTeX report assets. Keeping the manifest here
# makes an accidental redraw or partial replacement fail loudly in the public
# checkout instead of silently changing the paper presentation.
PAPER_ASSET_SHA256 = {
    "fig_qa_accuracy_workload.png": "249552eef2f6aab4ccdf2875e83b4d565fdb98be26fccda7e28d47b18182dfeb",
    "fig_qa_accuracy_workload.svg": "265bf3b704ff0dbd1df4c1e3cf63c426de834f838146ec7afb14276339d2f7d3",
    "fig_proactive_quality_delay.png": "a849ba29c254ce30f999cec95b23500eacba9959624a2a0cdc8254c771176864",
    "fig_proactive_quality_delay.svg": "03d3924e8fbb7748c1fb4eaaa4e3c2603202cd445eec695f5e60af6babbd7040",
    "fig_proactive_fa_miss.png": "a2a7b9b5871bd6b43c4f0f2f5c739e5bf3065f382784e09692933c5acc77365d",
    "fig_proactive_fa_miss.svg": "6ffe83b6ae2ee7e3546c8ca8e0ffb5cd5e655b6e7670a21cb17c5007a64457b8",
    "evaluation-design-report.en.png": "0b5c617454c1c7b79392b9eff5a1d9492b318ea2c7303b11bc6b5c7ef7e1bee8",
    "evaluation-design-report.en.svg": "57369dcc53aa63c58aeb0c5df189b474aa8629ec749edadb3af04f9b7b5ef358",
    "execution-modes-report.en.png": "4f3ce66d127570aec15281b98fec0f7b9654603db5bd22438ce72ac9db27a4f8",
    "execution-modes-report.en.svg": "bef7bc2aed189d4d8350cfc8e36c96a9be722d7f0f1ec9f894f296a6930b9af4",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(asset_dir: Path) -> int:
    failures: list[str] = []
    for name, expected in PAPER_ASSET_SHA256.items():
        path = asset_dir / name
        if not path.is_file():
            failures.append(f"missing {path}")
            continue
        actual = sha256(path)
        if actual != expected:
            failures.append(f"hash mismatch {path}: {actual} != {expected}")
    if failures:
        for failure in failures:
            print(f"error: {failure}")
        return 1
    print(f"Verified {len(PAPER_ASSET_SHA256)} paper PNG/SVG assets in {asset_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify checked-in homepage assets from the current LaTeX report"
    )
    parser.add_argument(
        "--assets-dir",
        "--output",
        dest="asset_dir",
        type=Path,
        default=DEFAULT_ASSET_DIR,
        help="directory containing the checked-in paper assets",
    )
    args = parser.parse_args()
    return verify(args.asset_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
