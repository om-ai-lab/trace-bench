"""Verify the synthetic QA/Proactive answer path, not only bundle integrity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_bench.bundle import RunBundle


def check(root: Path) -> None:
    for task in ("qa", "proactive"):
        bundle = RunBundle(root / task)
        bundle.validate()
        summary = json.loads((root / task / "summary.json").read_text())
        if summary.get("synthetic") is not True:
            raise ValueError(f"{task}: expected synthetic run")
        for filename in ("metrics.json", "rescored_metrics.json"):
            data = json.loads((root / task / filename).read_text())
            metrics = data.get("metrics", data)
            expected = {"record_count": 1, "failure_count": 0}
            if task == "qa":
                expected.update(accuracy=1.0, correct=1)
            else:
                expected.update(window_count=1, window_accuracy=1.0,
                                window_source_distribution={"in_window": 1})
            for key, value in expected.items():
                if metrics.get(key) != value:
                    raise ValueError(f"{task}/{filename}: {key}={metrics.get(key)!r}, expected {value!r}")
            eligibility = metrics.get("official_eligibility", {})
            if eligibility.get("official_eligible") is not False:
                raise ValueError(f"{task}/{filename}: synthetic run must be ineligible")
            if "synthetic_run" not in eligibility.get("reasons", []):
                raise ValueError(f"{task}/{filename}: missing synthetic reason")
        print(f"{task}: original and rescored answers verified; synthetic/ineligible")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    check(parser.parse_args().output)
