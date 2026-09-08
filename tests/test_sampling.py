from __future__ import annotations

import cv2
import numpy as np

from open_stream_bench.sampling import sample_video, timestamp_plan, video_duration_s


def test_timestamp_plan_and_opencv_sampling(synthetic_release):
    release, root = synthetic_release
    timestamps = timestamp_plan(0.0, 1.0, 2.0)
    sampled = sample_video(root / "video.avi", timestamps)
    assert timestamps == [0.0, 0.5, 1.0]
    assert [item.frame_index for item in sampled.observations] == [0, 5, 10]
    assert sampled.observations[0].rgb.shape == (48, 64, 3)
    assert sampled.observations[0].rgb.dtype.name == "uint8"
    assert sampled.decoder.startswith("opencv-")


def test_timestamp_plan_includes_fractional_legal_endpoint():
    assert timestamp_plan(377.73, 396.0, 1.0)[-2:] == [395.73, 396.0]


def test_sampling_applies_fixed_long_edge_limit(synthetic_release):
    _, root = synthetic_release
    sampled = sample_video(root / "video.avi", [0.0], max_width=32)
    assert sampled.observations[0].rgb.shape == (24, 32, 3)
    assert (sampled.width, sampled.height) == (32, 24)


def test_sampling_clamps_timestamp_past_video_end_to_last_frame(synthetic_release):
    _, root = synthetic_release
    sampled = sample_video(root / "video.avi", [100.0])
    assert sampled.observations[0].frame_index == 39
    assert sampled.source_frame_count == 40


def test_sampling_reopens_and_decodes_sequentially_after_seek_failure(
    synthetic_release, monkeypatch
):
    _, root = synthetic_release
    frames = [np.full((8, 10, 3), index, dtype=np.uint8) for index in range(4)]

    class FakeCapture:
        def __init__(self, *, seek_fails: bool):
            self.seek_fails = seek_fails
            self.index = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == cv2.CAP_PROP_FPS:
                return 10.0
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return 4.0
            return 0.0

        def set(self, prop, value):
            if prop != cv2.CAP_PROP_POS_FRAMES or self.seek_fails:
                return False
            self.index = int(value)
            return True

        def read(self):
            if self.index >= len(frames):
                return False, None
            frame = frames[self.index]
            self.index += 1
            return True, frame

        def release(self):
            return None

    captures = []

    def factory(_path):
        capture = FakeCapture(seek_fails=bool(not captures))
        captures.append(capture)
        return capture

    monkeypatch.setattr("open_stream_bench.sampling.cv2.VideoCapture", factory)
    sampled = sample_video(root / "video.avi", [0.2])
    assert sampled.observations[0].frame_index == 2
    assert int(sampled.observations[0].rgb[0, 0, 0]) == 2
    assert len(captures) == 2


def test_duration_probe_does_not_decode_full_video_when_frame_count_is_unavailable(
    synthetic_release, monkeypatch
):
    _, root = synthetic_release

    class FakeCapture:
        released = False

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == cv2.CAP_PROP_FPS:
                return 24.0
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return 0.0
            return 0.0

        def read(self):
            raise AssertionError("duration provenance must not decode the source tail")

        def release(self):
            self.released = True

    capture = FakeCapture()
    monkeypatch.setattr(
        "open_stream_bench.sampling.cv2.VideoCapture", lambda _path: capture
    )

    assert video_duration_s(root / "video.avi") is None
    assert capture.released is True
