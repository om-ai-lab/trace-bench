from pathlib import Path
import runpy
import subprocess
import sys

import pytest


@pytest.mark.parametrize("script", ["check_public_files.py", "check_docs.py"])
def test_missing_git_does_not_pass_scan(monkeypatch, capsys, script):
    scan = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / script))
    def missing(*args, **kwargs):
        raise FileNotFoundError("git unavailable")
    monkeypatch.setattr(subprocess, "check_output", missing)
    assert scan["main"]() == 1
    output = capsys.readouterr()
    assert "requires Git and a Git checkout" in output.err
    assert "Traceback" not in output.err
    assert not output.out


@pytest.mark.parametrize("script", ["check_public_files.py", "check_docs.py"])
def test_non_git_directory_has_concise_failure(tmp_path, script):
    path = Path(__file__).resolve().parents[1] / "scripts" / script
    # Isolated subprocess outside any repository models a ZIP download.
    import os
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path.parent))
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    result = subprocess.run([sys.executable, str(path)], cwd=tmp_path, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "requires Git and a Git checkout" in result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert not result.stdout


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
