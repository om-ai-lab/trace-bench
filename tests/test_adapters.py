from pathlib import Path

import pytest

from open_stream_bench.adapters import TestDoubleAdapter as _TestDoubleAdapter, validate_adapter
from open_stream_bench.config import resolve_config
from open_stream_bench.models import TaskName


def test_v1_default_samples_one_frame_per_second(tmp_path: Path):
    config = resolve_config(
        release_dir=tmp_path,
        task=TaskName.QA,
        subset="tiny",
        adapter="open_stream_bench.adapters:TestDoubleAdapter",
        output_dir=tmp_path / "run",
    )

    assert config.stream_fps == 1.0


def test_wall_clock_pacing_requires_matching_adapter_capability(tmp_path: Path):
    config = resolve_config(
        release_dir=tmp_path,
        task=TaskName.QA,
        subset="tiny",
        adapter="open_stream_bench.adapters:TestDoubleAdapter",
        output_dir=tmp_path / "run",
        overrides={"pacing": "wall_clock"},
    )
    with pytest.raises(ValueError, match="does not match"):
        validate_adapter(_TestDoubleAdapter(), TaskName.QA, config)
    capabilities = validate_adapter(_TestDoubleAdapter(pacing="wall_clock"), TaskName.QA, config)
    assert capabilities.pacing == "wall_clock"
