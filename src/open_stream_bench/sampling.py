"""The single V0 OpenCV video sampler."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import cv2

from .models import Observation


class MediaError(RuntimeError):
    """A video cannot be sampled under the V0 media contract."""


SAMPLER_IDENTITY = "opencv-uniform-timestamp-v0"
RESIZE_POLICY = "width_at_most_max_width_preserve_aspect_no_upscale"


@dataclass(frozen=True)
class SampledVideo:
    observations: list[Observation]
    source_fps: float
    video_sha256: str
    decoder: str
    width: int = 0
    height: int = 0
    source_frame_count: int | None = None


def parse_timestamp(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    parts = value.strip().split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc


def timestamp_plan(start_s: float, end_s: float, fps: float) -> list[float]:
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps!r}")
    if end_s < start_s:
        raise ValueError(f"end_s must be >= start_s, got {end_s} < {start_s}")
    count = max(1, int(math.floor((end_s - start_s) * fps + 1e-9)) + 1)
    timestamps = [round(start_s + index / fps, 9) for index in range(count)]
    rounded_end = round(end_s, 9)
    if timestamps[-1] < rounded_end - 1e-9:
        timestamps.append(rounded_end)
    return timestamps


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resize_rgb(rgb: object, max_width: int | None):
    if max_width is None:
        return rgb
    height, width = rgb.shape[:2]  # type: ignore[union-attr]
    if width <= max_width:
        return rgb
    target_height = max(1, int(math.floor(height * max_width / width + 0.5)))
    return cv2.resize(rgb, (max_width, target_height), interpolation=cv2.INTER_AREA)


def _frame_count(capture: cv2.VideoCapture) -> int | None:
    """Return a trustworthy positive frame count when the backend exposes one."""
    value = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if not math.isfinite(value) or value <= 0:
        return None
    return max(1, int(math.floor(value + 0.5)))


def _sequential_frame(video_path: Path, frame_index: int) -> object | None:
    """Decode one frame sequentially after a backend seek failure.

    Some H.264 files accept ``set(CAP_PROP_POS_FRAMES, ...)`` but return no
    frame near the end of the stream. Reopening and decoding from the start is
    slower, but makes the sampler deterministic for this rare fallback path.
    """
    fallback = cv2.VideoCapture(str(video_path))
    if not fallback.isOpened():
        return None
    try:
        frame = None
        for _ in range(frame_index + 1):
            ok, candidate = fallback.read()
            if not ok or candidate is None:
                return None
            frame = candidate
        return frame
    finally:
        fallback.release()


def _read_frame(
    capture: cv2.VideoCapture, video_path: Path, frame_index: int
) -> object | None:
    """Read a frame by index, falling back to sequential decoding if needed."""
    if capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
        ok, bgr = capture.read()
        if ok and bgr is not None:
            return bgr
    return _sequential_frame(video_path, frame_index)


def sample_video(
    video_path: Path, timestamps: list[float], *, max_width: int | None = None
) -> SampledVideo:
    if not video_path.is_file():
        raise MediaError(f"video does not exist: {video_path}")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise MediaError(f"cannot open video: {video_path}")
    try:
        source_fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(source_fps) or source_fps <= 0:
            raise MediaError(f"invalid source FPS {source_fps!r}: {video_path}")
        source_frame_count = _frame_count(capture)
        observations: list[Observation] = []
        width = height = 0
        for timestamp_s in timestamps:
            frame_index = int(math.floor(timestamp_s * source_fps + 0.5))
            if source_frame_count is not None:
                frame_index = min(max(frame_index, 0), source_frame_count - 1)
            bgr = _read_frame(capture, video_path, frame_index)
            if bgr is None:
                raise MediaError(f"cannot read frame {frame_index}: {video_path}")
            rgb = _resize_rgb(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), max_width)
            height, width = rgb.shape[:2]
            observations.append(Observation(timestamp_s, frame_index, rgb))
        return SampledVideo(
            observations=observations,
            source_fps=source_fps,
            source_frame_count=source_frame_count,
            width=width,
            height=height,
            video_sha256=sha256_file(video_path),
            decoder=f"opencv-{cv2.__version__}",
        )
    finally:
        capture.release()


def video_duration_s(video_path: Path) -> float | None:
    """Return a metadata-derived source endpoint without decoding the tail.

    Source duration is provenance only.  Some OpenCV backends expose no frame
    count; walking every frame to discover the duration would accidentally
    turn a bounded Proactive evaluation into a full-video scan.  In that case
    return ``None`` and let Core use the GT-derived evaluation endpoint.
    """

    if not video_path.is_file():
        raise MediaError(f"video does not exist: {video_path}")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise MediaError(f"cannot open video: {video_path}")
    try:
        source_fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = _frame_count(capture)
        if not math.isfinite(source_fps) or source_fps <= 0:
            raise MediaError(f"invalid source FPS {source_fps!r}: {video_path}")
        if frame_count is None:
            return None
        return max(0.0, (frame_count - 1) / source_fps)
    finally:
        capture.release()
