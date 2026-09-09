"""Check public Markdown links and identical bilingual command blocks."""

from __future__ import annotations

from pathlib import Path
import ast
import json
import re
import subprocess
import sys
import textwrap
from urllib.parse import unquote, urlsplit


def fenced_blocks(content: str) -> list[tuple[str, str]]:
    """Collect fenced blocks in every language, including unlabelled blocks."""
    blocks = []
    fence = None
    body: list[str] = []
    info = ""
    for line in content.splitlines(keepends=True):
        if fence is None:
            opening = re.match(r"^ {0,3}(`{3,}|~{3,})([^\n]*)\n?$", line)
            if opening:
                fence, info = opening.groups()
                info = info.strip()
                body = []
        elif re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*\n?$", line):
            blocks.append((info, "".join(body)))
            fence = None
        else:
            body.append(line)
    if fence is not None:
        raise ValueError("unclosed fenced code block")
    return blocks


def check_syntax(blocks: list[tuple[str, str]]) -> None:
    for info, command in blocks:
        language = info.split()[0] if info else ""
        if language in {"bash", "sh", "shell"}:
            subprocess.run(["bash", "-n"], input=command, text=True, check=True)
        elif language in {"python", "py"}:
            ast.parse(command)  # Parse only; never execute documentation code.
        elif language == "json":
            json.loads(command)


def main() -> int:
    try:
        names = subprocess.check_output([
            "git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
        ], stderr=subprocess.PIPE).decode().split("\0")
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("error: this check requires Git and a Git checkout (git ls-files); "
              "run it from the repository root", file=sys.stderr)
        return 1
    paths = sorted({Path(p) for p in names if p.endswith(".md") and Path(p).is_file()})
    inline_bilingual = {"SECURITY.md", "CODE_OF_CONDUCT.md"}
    for path in paths:
        content = path.read_text(encoding="utf-8")
        check_syntax(fenced_blocks(content))
        for target in re.findall(r"\]\(([^)]+)\)", content):
            parts = urlsplit(target.strip("<>"))
            if not parts.scheme and parts.path:
                if not (path.parent / unquote(parts.path)).exists():
                    raise ValueError(f"{path}: missing link {target}")
        if ".zh-CN." in path.name or path.name in inline_bilingual or ".github" in path.parts:
            continue
        translated = path.with_name(path.stem + ".zh-CN.md")
        if not translated.is_file():
            raise ValueError(f"missing translation: {translated}")
        if fenced_blocks(content) != fenced_blocks(translated.read_text(encoding="utf-8")):
            raise ValueError(f"command blocks differ: {path} / {translated}")
    readme = Path("README.md").read_text(encoding="utf-8")
    smoke = next(c for lang, c in fenced_blocks(readme) if "make_smoke_fixture.py" in c)
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    section = ci.split("      - name: README end-to-end software flow\n", 1)[1]
    section = section.split("      - name:", 1)[0].split("        run: |\n", 1)[1]
    if textwrap.dedent(section).strip() != smoke.strip():
        raise ValueError("CI smoke differs from README")
    print(f"Checked {len(paths)} Markdown files, bilingual commands and CI smoke parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
