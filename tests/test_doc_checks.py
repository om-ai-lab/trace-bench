from pathlib import Path
import runpy

import pytest


def _checker():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_docs.py"))


@pytest.mark.parametrize("language", ["python", "yaml", "typescript", "", "mermaid"])
def test_all_fenced_languages_are_compared(tmp_path, monkeypatch, language):
    checker = _checker()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "guide.md").write_text(f"```{language}\nx = 1\n```\n")
    (tmp_path / "guide.zh-CN.md").write_text(f"```{language}\nx = 2\n```\n")
    monkeypatch.setattr(checker["subprocess"], "check_output", lambda *a, **kw: b"guide.md\0")
    with pytest.raises(ValueError, match="command blocks differ"):
        checker["main"]()


def test_tilde_long_fences_and_python_never_execute(tmp_path):
    checker = _checker()
    code = f"from pathlib import Path\nPath({str(tmp_path / 'must-not-exist')!r}).touch()\n"
    blocks = checker["fenced_blocks"]("~~~python\n" + code + "~~~~\n````yaml\nx: 1\n`````\n")
    assert blocks == [("python", code), ("yaml", "x: 1\n")]
    checker["check_syntax"](blocks)
    assert not (tmp_path / "must-not-exist").exists()
    with pytest.raises(SyntaxError):
        checker["check_syntax"]([("python", "def invalid(:")])
