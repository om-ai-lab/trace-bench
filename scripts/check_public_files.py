"""Scan Git's public file list; missing Git or read errors fail the check."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        paths = subprocess.check_output([
            "git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
        ], stderr=subprocess.PIPE).decode().split("\0")
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("error: this check requires Git and a Git checkout (git ls-files); "
              "run it from the repository root", file=sys.stderr)
        return 1
    pattern = re.compile(
        rb"10\.[0-9]+\.[0-9]+\.[0-9]+|/data[0-9]+|/training|/vsan|vlx_eval/|"
        rb"BEGIN (RSA|OPENSSH) PRIVATE KEY|sk-[A-Za-z0-9]{20,}"
    )
    failed = False
    for name in sorted(set(paths) - {"", "scripts/check_public_files.py"}):
        path = Path(name)
        if not path.exists():  # staged deletion / removed working-tree file
            continue
        if path.is_symlink():
            raise ValueError(f"public symlink needs explicit review: {name}")
        for number, line in enumerate(path.read_bytes().splitlines(), 1):
            if pattern.search(line):
                print(f"Potential private content: {name}:{number}")
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
