"""Portable file-based Run Bundle persistence and validation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    serialized = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    _atomic_write_text(path, serialized)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RunBundle:
    def __init__(self, root: Path):
        self.root = root

    @property
    def records_path(self) -> Path:
        return self.root / "records.jsonl"

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def checkpoints_root(self) -> Path:
        return self.root / "checkpoints"

    def records(self) -> list[dict[str, Any]]:
        if self.records_path.is_file():
            return _read_jsonl(self.records_path)
        checkpoint = self.latest_checkpoint()
        return _read_jsonl(checkpoint / "records.jsonl") if checkpoint else []

    def events(self) -> list[dict[str, Any]]:
        if self.events_path.is_file():
            return _read_jsonl(self.events_path)
        checkpoint = self.latest_checkpoint()
        return _read_jsonl(checkpoint / "events.jsonl") if checkpoint else []

    def is_finalized(self) -> bool:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.is_file():
            return False
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return manifest.get("finalized") is True

    def prepare(self, resolved_config: dict[str, Any]) -> None:
        """Persist the frozen run configuration before record execution."""
        if self.is_finalized():
            raise ValueError(f"finalized bundle is immutable: {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        _write_json(self.root / "resolved_config.json", resolved_config)
        latest = self.latest_checkpoint()
        latest_sequence = int(latest.name) if latest is not None else None
        _write_json(
            self.root / "manifest.json",
            {
                "bundle_schema": "osb-run-bundle-v0",
                "finalized": False,
                "latest_checkpoint": latest_sequence,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _checkpoint_dirs(self) -> list[Path]:
        if not self.checkpoints_root.is_dir():
            return []
        return sorted(
            (
                path
                for path in self.checkpoints_root.iterdir()
                if path.is_dir() and path.name.isdigit()
            ),
            key=lambda path: int(path.name),
            reverse=True,
        )

    def _validate_committed_checkpoint(self, directory: Path) -> Path:
        """Validate a commit marker instead of silently falling back past it."""
        commit_path = directory / "commit.json"
        try:
            commit = json.loads(commit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"corrupt checkpoint commit marker: {commit_path}") from exc
        try:
            expected_sequence = int(directory.name)
        except ValueError as exc:
            raise ValueError(f"invalid checkpoint directory: {directory}") from exc
        if commit.get("sequence") != expected_sequence:
            raise ValueError(f"checkpoint sequence mismatch: {directory}")
        required = ("records.jsonl", "events.jsonl", "resolved_config.json")
        files = commit.get("files")
        if not isinstance(files, dict):
            raise ValueError(f"checkpoint commit omits file hashes: {commit_path}")
        for name in required:
            path = directory / name
            expected_hash = files.get(name)
            if not path.is_file() or not isinstance(expected_hash, str):
                raise ValueError(f"corrupt checkpoint file: {path}")
            if file_sha256(path) != expected_hash:
                raise ValueError(f"checkpoint integrity mismatch: {path}")
        records = _read_jsonl(directory / "records.jsonl")
        events = _read_jsonl(directory / "events.jsonl")
        if commit.get("record_count") != len(records) or commit.get("event_count") != len(events):
            raise ValueError(f"checkpoint count mismatch: {directory}")
        return directory

    def latest_checkpoint(self) -> Path | None:
        for directory in self._checkpoint_dirs():
            commit_path = directory / "commit.json"
            if not commit_path.is_file():
                continue
            return self._validate_committed_checkpoint(directory)
        return None

    @staticmethod
    def _validate_state(
        records: list[dict[str, Any]], events: list[dict[str, Any]]
    ) -> None:
        record_ids = [record.get("record_id") for record in records]
        if (
            any(not isinstance(record_id, str) for record_id in record_ids)
            or len(record_ids) != len(set(record_ids))
            or any(record.get("status") not in {"completed", "failed"} for record in records)
            or any(event.get("record_id") not in set(record_ids) for event in events)
        ):
            raise ValueError("checkpoint has invalid record/event membership")

    def checkpoint(
        self,
        *,
        resolved_config: dict[str, Any],
        records: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> Path:
        if self.is_finalized():
            raise ValueError(f"finalized bundle is immutable: {self.root}")
        record_ids = [record.get("record_id") for record in records]
        if (
            any(not isinstance(record_id, str) for record_id in record_ids)
            or len(record_ids) != len(set(record_ids))
            or any(record.get("status") not in {"completed", "failed"} for record in records)
        ):
            raise ValueError("checkpoint contains invalid or non-terminal records")
        if any(event.get("record_id") not in set(record_ids) for event in events):
            raise ValueError("checkpoint event does not belong to a checkpointed record")
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoints_root.mkdir(parents=True, exist_ok=True)
        existing_sequences = [
            int(path.name)
            for path in self.checkpoints_root.iterdir()
            if path.is_dir() and path.name.isdigit()
        ]
        sequence = max(existing_sequences, default=0) + 1
        directory = self.checkpoints_root / f"{sequence:08d}"
        directory.mkdir()
        _write_json(directory / "resolved_config.json", resolved_config)
        _write_jsonl(directory / "records.jsonl", records)
        _write_jsonl(directory / "events.jsonl", events)
        files = {
            name: file_sha256(directory / name)
            for name in ("records.jsonl", "events.jsonl", "resolved_config.json")
        }
        _write_json(
            directory / "commit.json",
            {
                "sequence": sequence,
                "record_count": len(records),
                "event_count": len(events),
                "config_hash": resolved_config.get("config_hash"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": files,
            },
        )
        _write_json(
            self.root / "manifest.json",
            {
                "bundle_schema": "osb-run-bundle-v0",
                "finalized": False,
                "latest_checkpoint": sequence,
            },
        )
        return directory

    def resume_state(
        self,
        *,
        expected_config_hash: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        checkpoint = self.latest_checkpoint()
        if checkpoint is not None:
            with (checkpoint / "resolved_config.json").open("r", encoding="utf-8") as handle:
                config = json.load(handle)
            if config.get("config_hash") != expected_config_hash:
                raise ValueError("resume config identity does not match latest checkpoint")
            records = _read_jsonl(checkpoint / "records.jsonl")
            events = _read_jsonl(checkpoint / "events.jsonl")
            self._validate_state(records, events)
            return records, events
        if self.records_path.is_file() or self.events_path.is_file():
            if self.records_path.is_file() != self.events_path.is_file():
                raise ValueError("existing bundle must contain both records.jsonl and events.jsonl")
            config_path = self.root / "resolved_config.json"
            if not config_path.is_file():
                raise ValueError("existing bundle is missing resolved_config.json")
            with config_path.open("r", encoding="utf-8") as handle:
                config = json.load(handle)
            if config.get("config_hash") != expected_config_hash:
                raise ValueError("resume config identity does not match existing bundle")
            records, events = self.records(), self.events()
            self._validate_state(records, events)
            return records, events
        return [], []

    def write(
        self,
        *,
        resolved_config: dict[str, Any],
        records: list[dict[str, Any]],
        events: list[dict[str, Any]],
        metrics: dict[str, Any],
        synthetic: bool,
        provisional: bool = True,
        official_eligibility: dict[str, Any] | None = None,
    ) -> None:
        if self.is_finalized():
            raise ValueError(f"finalized bundle is immutable: {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        _write_json(self.root / "resolved_config.json", resolved_config)
        _write_jsonl(self.records_path, records)
        _write_jsonl(self.events_path, events)
        _write_json(self.root / "metrics.json", metrics)
        _write_json(
            self.root / "summary.json",
            {
                "record_count": len(records),
                "synthetic": synthetic,
                "provisional": provisional,
                "official_eligibility": official_eligibility or {
                    "official_eligible": False,
                    "reasons": ["eligibility_not_evaluated"],
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        manifest = {
            "bundle_schema": "osb-run-bundle-v0",
            "synthetic": synthetic,
            "provisional": provisional,
            "finalized": True,
            "official_eligibility": official_eligibility or {
                "official_eligible": False,
                "reasons": ["eligibility_not_evaluated"],
            },
            "files": {},
        }
        _write_json(self.root / "manifest.json", manifest)
        files = {}
        for path in sorted(self.root.iterdir()):
            if path.name in {"integrity.json", "checkpoints"}:
                continue
            if path.is_file():
                files[path.name] = file_sha256(path)
        _write_json(self.root / "integrity.json", {"files": files})

    def write_rescored(
        self,
        *,
        records: list[dict[str, Any]],
        metrics: dict[str, Any],
        scoring: dict[str, Any],
        source_bundle: str | None = None,
    ) -> None:
        """Persist derived rescoring without mutating an immutable bundle.

        Raw inference records, events, manifest hashes, and finalization state
        remain unchanged.  The sidecar is intentionally outside integrity.json
        so a judge endpoint can be changed and rerun safely.
        """

        self.root.mkdir(parents=True, exist_ok=True)
        _write_jsonl(self.root / "rescored_records.jsonl", records)
        _write_json(
            self.root / "rescored_metrics.json",
            {
                "metrics": metrics,
                "scoring": scoring,
                "scored_record_count": len(records),
                "source_bundle": source_bundle or str(self.root),
            },
        )

    def discard_checkpoints(self) -> None:
        if self.checkpoints_root.is_dir():
            shutil.rmtree(self.checkpoints_root)

    def validate(self) -> dict[str, Any]:
        manifest_path = self.root / "manifest.json"
        if manifest_path.is_file():
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            if manifest.get("finalized") is not True:
                raise ValueError("run bundle is not finalized")
        required = [
            "manifest.json",
            "resolved_config.json",
            "records.jsonl",
            "events.jsonl",
            "metrics.json",
            "summary.json",
            "integrity.json",
        ]
        missing = [name for name in required if not (self.root / name).is_file()]
        if missing:
            raise ValueError(f"missing bundle files: {', '.join(missing)}")
        with (self.root / "integrity.json").open("r", encoding="utf-8") as handle:
            integrity = json.load(handle)
        listed = set(integrity.get("files", {}))
        required_hashes = set(required) - {"integrity.json"}
        missing_hashes = sorted(required_hashes - listed)
        if missing_hashes:
            raise ValueError("integrity manifest omits: " + ", ".join(missing_hashes))
        mismatches = []
        for name, expected in integrity.get("files", {}).items():
            actual_path = self.root / name
            if not actual_path.is_file() or file_sha256(actual_path) != expected:
                mismatches.append(name)
        if mismatches:
            raise ValueError("integrity mismatch: " + ", ".join(mismatches))
        records = self.records()
        events = self.events()
        self._validate_state(records, events)
        record_ids = {str(record.get("record_id")) for record in records}
        if any(str(event.get("record_id")) not in record_ids for event in events):
            raise ValueError("events.jsonl contains an event for an unknown record")
        events_by_record: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            events_by_record.setdefault(str(event.get("record_id")), []).append(
                {key: value for key, value in event.items() if key != "record_id"}
            )
        for record in records:
            embedded = record.get("events")
            if isinstance(embedded, list) and embedded != events_by_record.get(
                str(record.get("record_id")), []
            ):
                raise ValueError(
                    f"embedded events disagree with events.jsonl: {record.get('record_id')}"
                )
        with (self.root / "summary.json").open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        eligibility = summary.get("official_eligibility") or manifest.get(
            "official_eligibility"
        ) or {"official_eligible": False, "reasons": ["eligibility_not_evaluated"]}
        return {
            "root": str(self.root),
            "record_count": len(records),
            "valid": True,
            **eligibility,
        }
