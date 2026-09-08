"""Canonical release loading and validation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, TypeVar

from .models import ProactiveRecord, QARecord, ReleaseManifest

T = TypeVar("T")


def _read_jsonl(path: Path, model_type: type[T]) -> list[T]:
    records: list[T] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(model_type.model_validate(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"invalid {path}:{line_number}: {exc}") from exc
    return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Release:
    def __init__(self, root: Path, manifest: ReleaseManifest):
        self.root = root
        self.manifest = manifest
        self.qa = _read_jsonl(root / manifest.qa_file, QARecord)
        self.proactive = _read_jsonl(root / manifest.proactive_file, ProactiveRecord)
        self._qa_by_id = _index_records(self.qa, "qa")
        self._proactive_by_id = _index_records(self.proactive, "proactive")

    def records(self, task: str, subset: str = "full") -> list[QARecord | ProactiveRecord]:
        if task == "qa":
            source = self.qa
            ids_file = self.manifest.tiny_qa_ids_file
            index = self._qa_by_id
        elif task == "proactive":
            source = self.proactive
            ids_file = self.manifest.tiny_proactive_ids_file
            index = self._proactive_by_id
        else:
            raise ValueError(f"unknown task: {task!r}")
        if subset == "full" or subset == "all":
            return list(source)
        if subset != "tiny":
            raise ValueError(f"unknown subset: {subset!r}")
        wanted = _read_id_list(self.root / ids_file)
        missing = [record_id for record_id in wanted if record_id not in index]
        if missing:
            raise ValueError(f"tiny {task} subset contains unknown record IDs: {missing[:3]}")
        return [index[record_id] for record_id in wanted]


def _index_records(records: list[QARecord | ProactiveRecord], task: str) -> dict[str, QARecord | ProactiveRecord]:
    index: dict[str, QARecord | ProactiveRecord] = {}
    for record in records:
        if record.record_id in index:
            raise ValueError(f"duplicate {task} record_id: {record.record_id}")
        _validate_record(record)
        index[record.record_id] = record
    return index


def _read_id_list(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as handle:
        value: Any = json.load(handle)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"ID subset must be a JSON list of strings: {path}")
    if len(value) != len(set(value)):
        raise ValueError(f"ID subset contains duplicates: {path}")
    return value


def _validate_record(record: QARecord | ProactiveRecord) -> None:
    def finite(value: float, name: str) -> None:
        if not math.isfinite(value):
            raise ValueError(f"{record.record_id}: {name} must be finite")
        if value < 0:
            raise ValueError(f"{record.record_id}: {name} must be non-negative")

    if isinstance(record, QARecord):
        finite(record.question_time_s, "question_time_s")
        finite(record.evidence_anchor_s, "evidence_anchor_s")
        if record.evidence_anchor_s > record.question_time_s:
            raise ValueError(f"{record.record_id}: evidence_anchor_s is after question_time_s")
        return

    finite(record.instruction_time_s, "instruction_time_s")
    # ``deadline_s`` is legacy provenance from the source release.  It is
    # intentionally not required and is not a legal evaluation boundary.
    if record.deadline_s is not None:
        finite(record.deadline_s, "deadline_s")
        if record.deadline_s < record.instruction_time_s:
            raise ValueError(f"{record.record_id}: deadline_s is before instruction_time_s")
    annotations = record.metadata.get("trigger_annotations", [])
    if annotations is not None and not isinstance(annotations, list):
        raise ValueError(f"{record.record_id}: metadata.trigger_annotations must be a list")
    if isinstance(annotations, list) and annotations and len(annotations) != len(record.windows):
        raise ValueError(
            f"{record.record_id}: trigger_annotations and windows must have the same length"
        )
    previous_start: float | None = None
    for window in record.windows:
        finite(window.start_s, "window.start_s")
        finite(window.end_s, "window.end_s")
        if window.end_s < window.start_s:
            raise ValueError(f"{record.record_id}: response window ends before it starts")
        if previous_start is not None and window.start_s < previous_start:
            raise ValueError(f"{record.record_id}: response windows are not ordered by start_s")
        previous_start = window.start_s
    if isinstance(annotations, list):
        for index, annotation in enumerate(annotations):
            if not isinstance(annotation, dict):
                raise ValueError(f"{record.record_id}: trigger annotation {index} is not an object")
            if annotation.get("trigger_type") == "state_interval":
                window = record.windows[index]
                if window.end_s <= window.start_s:
                    raise ValueError(
                        f"{record.record_id}: state interval {index} must have positive duration"
                    )


def _safe_relative_path(relative: str) -> None:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"release file path must stay inside the release directory: {relative!r}")


def load_release(root: Path) -> Release:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"release manifest does not exist: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = ReleaseManifest.model_validate(json.load(handle))
    required_files = (manifest.qa_file, manifest.proactive_file, manifest.tiny_qa_ids_file, manifest.tiny_proactive_ids_file)
    for relative in (*required_files, *manifest.files.keys()):
        _safe_relative_path(relative)
    for relative in required_files:
        if not (root / relative).is_file():
            raise FileNotFoundError(f"release file does not exist: {root / relative}")
    release = Release(root, manifest)
    tiny_qa_ids = _read_id_list(root / manifest.tiny_qa_ids_file)
    tiny_proactive_ids = _read_id_list(root / manifest.tiny_proactive_ids_file)
    missing_qa = [record_id for record_id in tiny_qa_ids if record_id not in release._qa_by_id]
    missing_proactive = [record_id for record_id in tiny_proactive_ids if record_id not in release._proactive_by_id]
    if missing_qa:
        raise ValueError(f"tiny qa subset contains unknown record IDs: {missing_qa[:3]}")
    if missing_proactive:
        raise ValueError(f"tiny proactive subset contains unknown record IDs: {missing_proactive[:3]}")
    if len(release.qa) != manifest.counts.get("qa", len(release.qa)):
        raise ValueError("QA count does not match release manifest")
    if len(release.proactive) != manifest.counts.get("proactive", len(release.proactive)):
        raise ValueError("proactive count does not match release manifest")
    return release


def validate_release(root: Path) -> dict[str, object]:
    release = load_release(root)
    checked = {"manifest.json", release.manifest.qa_file, release.manifest.proactive_file}
    mismatches: list[str] = []
    required_hashes = {
        release.manifest.qa_file,
        release.manifest.proactive_file,
        release.manifest.tiny_qa_ids_file,
        release.manifest.tiny_proactive_ids_file,
    }
    missing_hashes = sorted(required_hashes - set(release.manifest.files))
    if missing_hashes:
        mismatches.append("manifest has no hash for: " + ", ".join(missing_hashes))
    for relative, expected in release.manifest.files.items():
        path = root / relative
        if not path.is_file():
            mismatches.append(f"missing {relative}")
        elif expected and _sha256(path) != expected:
            mismatches.append(f"hash mismatch {relative}")
        checked.add(relative)
    if mismatches:
        raise ValueError("; ".join(mismatches))
    return {
        "release_id": release.manifest.release_id,
        "qa_count": len(release.qa),
        "proactive_count": len(release.proactive),
        "checked_files": sorted(checked),
    }
