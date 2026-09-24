"""Test extracted sdist sources and a non-editable wheel in an isolated venv."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import venv


def check(dist: Path, output: Path) -> None:
    dist, output = dist.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    archives = list(dist.glob("*.tar.gz"))
    wheels = list(dist.glob("*.whl"))
    if len(archives) != 1 or len(wheels) != 1:
        raise ValueError("use a fresh dist directory with exactly one sdist and one wheel")
    with tarfile.open(archives[0]) as archive:
        for member in archive.getmembers():
            target = (output / member.name).resolve()
            if not target.is_relative_to(output) or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsafe archive member: {member.name}")
        if hasattr(tarfile, "data_filter"):
            archive.extractall(output, filter="data")
        else:  # Older Python 3.10: members were checked above.
            archive.extractall(output)
    sources = [p for p in output.iterdir() if p.is_dir()]
    if len(sources) != 1:
        raise ValueError("sdist must contain one source root")
    source = sources[0]
    if not (source / "tests/conftest.py").is_file():
        raise ValueError("sdist is missing tests/conftest.py")
    env = dict(os.environ, PYTHONPATH=str(source / "src"), PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        f"--basetemp={output / 'pytest'}",
    ], cwd=source, env=env, check=True)
    wheel_env = output / "wheel-env"
    venv.EnvBuilder(with_pip=True).create(wheel_env)
    python = wheel_env / "bin/python"
    subprocess.run([
        str(python), "-m", "pip", "install", str(wheels[0]),
    ], cwd=output, check=True)
    subprocess.run([
        str(python), "-I", "-c",
        "from pathlib import Path; import sys, trace_bench as trace; "
        "from importlib.resources import files; "
        "assert files('trace_bench').joinpath('presets/current.json').is_file(); "
        "assert Path(trace.__file__).resolve().is_relative_to(Path(sys.prefix)); "
        "assert trace.__version__ == '0.1.0'; "
        "print('Installed wheel:', trace.__file__)",
    ], cwd=output, check=True)
    subprocess.run([str(python), "-I", "-m", "trace_bench.cli", "--help"],
                   cwd=output, check=True)
    # The console entry points must both exist: `trace` and the compatibility
    # alias `osb` promised in the changelog.
    for script in ("trace", "osb"):
        subprocess.run([str(wheel_env / "bin" / script), "--version"],
                       cwd=output, check=True)
    smoke = output / "wheel-smoke"
    subprocess.run([
        str(python), "-I", str(source / "scripts/make_smoke_fixture.py"),
        "--output", str(smoke),
    ], cwd=output, check=True)
    cli = [str(python), "-I", "-m", "trace_bench.cli"]
    for task in ("qa", "proactive"):
        bundle = smoke / task
        subprocess.run(cli + [
            "run", "--task", task, "--release", str(smoke / "release"),
            "--adapter", "trace_bench.adapters:TestDoubleAdapter",
            "--video-root", str(smoke), "--output", str(bundle),
            "--synthetic", "--judge-mode", "exact",
            "--checkpoint-every", "5",
        ], cwd=output, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(cli + ["bundle", "validate", str(bundle)],
                       cwd=output, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(cli + ["score", str(bundle), "--judge-mode", "exact"],
                       cwd=output, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([
        str(python), "-I", str(source / "scripts/check_smoke_results.py"),
        "--output", str(smoke),
    ], cwd=output, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.dist, args.output)
