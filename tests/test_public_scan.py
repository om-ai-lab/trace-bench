from pathlib import Path
import runpy
import subprocess

import pytest


def test_missing_git_does_not_pass_scan(monkeypatch):
    scan = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_public_files.py"))
    def missing(*args, **kwargs):
        raise FileNotFoundError("git unavailable")
    monkeypatch.setattr(subprocess, "check_output", missing)
    with pytest.raises(FileNotFoundError, match="git unavailable"):
        scan["main"]()


def test_scan_flags_secret_without_printing_it(tmp_path, monkeypatch, capsys):
    scan = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_public_files.py"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: b"sample.txt\0")
    secret = "sk-" + "x" * 24
    (tmp_path / "sample.txt").write_text(secret)
    assert scan["main"]() == 1
    message = capsys.readouterr().out
    assert "sample.txt:1" in message
    assert secret not in message
