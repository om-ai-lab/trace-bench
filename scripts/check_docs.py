"""Check public Markdown links and identical bilingual command blocks."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import textwrap
from urllib.parse import unquote, urlsplit


def main() -> None:
    names = subprocess.check_output([
        "git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
    ]).decode().split("\0")
    paths = sorted({Path(p) for p in names if p.endswith(".md") and Path(p).is_file()})
    block_re = re.compile(r"^```(bash|json|text)\n(.*?)^```", re.M | re.S)
    inline_bilingual = {"SECURITY.md", "CODE_OF_CONDUCT.md"}
    for path in paths:
        content = path.read_text(encoding="utf-8")
        for language, command in block_re.findall(content):
            if language == "bash":
                subprocess.run(["bash", "-n"], input=command, text=True, check=True)
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
        if block_re.findall(content) != block_re.findall(translated.read_text(encoding="utf-8")):
            raise ValueError(f"command blocks differ: {path} / {translated}")
    readme = Path("README.md").read_text(encoding="utf-8")
    smoke = next(c for lang, c in block_re.findall(readme) if "make_smoke_fixture.py" in c)
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    section = ci.split("      - name: README end-to-end software flow\n", 1)[1]
    section = section.split("      - name:", 1)[0].split("        run: |\n", 1)[1]
    if textwrap.dedent(section).strip() != smoke.strip():
        raise ValueError("CI smoke differs from README")
    print(f"Checked {len(paths)} Markdown files, bilingual commands and CI smoke parity")


if __name__ == "__main__":
    main()
