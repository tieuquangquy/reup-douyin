from __future__ import annotations

import hashlib
import json
import shutil
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from src.media_pipeline.frame_sampling.local_text_detector import TextBox
from src.media_pipeline.frame_sampling.local_text_recognizer import LocalRecognition
from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    MasterPhase1Extractor,
)


class _SyntheticFlashDetector:
    def detect(self, image: np.ndarray, **_kwargs: object) -> list[TextBox]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return (
            [TextBox(0.10, 0.84, 0.80, 0.10)]
            if float(gray.std()) > 8.0
            else []
        )


class _ResidualOnlyFlashDetector:
    """Simulate a caption missed by the normal threshold but found by V27."""

    def detect(self, image: np.ndarray, **kwargs: object) -> list[TextBox]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        threshold = float(kwargs.get("bin_thresh") or 1.0)
        return (
            [TextBox(0.10, 0.84, 0.80, 0.10)]
            if float(gray.std()) > 8.0 and threshold <= 0.14
            else []
        )


class _SyntheticCjkRecognizer:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def recognize(self, _image: np.ndarray) -> LocalRecognition:
        return LocalRecognition(text="字幕", confidence=0.99, valid_char_ratio=1.0)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_v8_keeps_and_closes_a_real_one_frame_video_flash(tmp_path) -> None:
    video = tmp_path / "single_frame_flash.avi"
    output = tmp_path / "phase1"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (320, 180)
    )
    assert writer.isOpened()
    for frame_index in range(18):
        frame = np.full((180, 320, 3), 72, dtype=np.uint8)
        if frame_index == 7:
            for x in range(35, 285, 22):
                frame[152:174, x : x + 7] = 245
                frame[160:164, x : x + 15] = 245
        writer.write(frame)
    writer.release()

    with patch(
        "src.media_pipeline.frame_sampling.ensure_text_recognizer_model.ensure_text_recognizer_assets",
        return_value=(tmp_path / "rec.onnx", tmp_path / "dict.txt"),
    ), patch(
        "src.media_pipeline.frame_sampling.local_text_recognizer.LocalTextRecognizer",
        _SyntheticCjkRecognizer,
    ):
        result = MasterPhase1Extractor(
            detector=_SyntheticFlashDetector(),
            analysis_engine="audio_visual_temporal_v1",
            min_hits=2,
        ).extract(video, output)

    assert len(result.timeline) == 1
    coverage_path = output / "phase1_track_coverage_v2.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    assert coverage["scanned_frames"] == 18
    assert coverage["tracks"][0]["presence_ranges"] == [[7, 7]]
    assert coverage["master_timeline_ref"]["sha256"] == hashlib.sha256(
        (output / "master_timeline.json").read_bytes()
    ).hexdigest()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_v27_unassigned_closure_recovers_a_seedless_single_frame_flash(tmp_path) -> None:
    video = tmp_path / "seedless_flash.avi"
    output = tmp_path / "phase1"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (320, 180)
    )
    assert writer.isOpened()
    for frame_index in range(18):
        frame = np.full((180, 320, 3), 72, dtype=np.uint8)
        if frame_index == 7:
            for x in range(35, 285, 22):
                frame[152:174, x : x + 7] = 245
                frame[160:164, x : x + 15] = 245
        writer.write(frame)
    writer.release()

    with patch(
        "src.media_pipeline.frame_sampling.ensure_text_recognizer_model.ensure_text_recognizer_assets",
        return_value=(tmp_path / "rec.onnx", tmp_path / "dict.txt"),
    ), patch(
        "src.media_pipeline.frame_sampling.local_text_recognizer.LocalTextRecognizer",
        _SyntheticCjkRecognizer,
    ):
        result = MasterPhase1Extractor(
            detector=_ResidualOnlyFlashDetector(),
            analysis_engine="audio_visual_temporal_v1",
            min_hits=2,
        ).extract(video, output)

    assert len(result.timeline) == 1
    metrics = json.loads((output / "phase1_event_metrics.json").read_text(encoding="utf-8"))
    discovery = metrics["completeness_residual_discovery"]
    assert discovery["dbnet_hits"] >= 1
    assert discovery["new_tracks"] == 1
    assert discovery["second_closure"] is True
    coverage = json.loads((output / "phase1_track_coverage_v2.json").read_text(encoding="utf-8"))
    assert any(start <= 7 <= end for start, end in coverage["tracks"][0]["presence_ranges"])
