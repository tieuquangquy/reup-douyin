"""Scan every video frame with local DBNet and emit per-frame text boxes.

Detect-only: no Cloud OCR, blur, translate, or subtitle. Use this as the
authority for where text appears before any downstream clean/sub step.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import cv2

from src.media_pipeline.cache_provenance import video_content_fingerprint
from src.media_pipeline.frame_sampling.ensure_dbnet_model import ensure_dbnet_onnx
from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode
from src.media_pipeline.frame_sampling.local_text_detector import LocalTextDetector, TextBox
from src.media_pipeline.frame_sampling.resolve_source import resolve_video_source

logger = logging.getLogger(__name__)


def _box_to_dict(box: TextBox) -> dict[str, float]:
    return {
        "x": round(float(box.x), 6),
        "y": round(float(box.y), 6),
        "w": round(float(box.width), 6),
        "h": round(float(box.height), 6),
    }


def detect_text_boxes_every_frame(
    video_source: str | Path,
    *,
    frame_stride: int = 1,
    detector: LocalTextDetector | None = None,
    model_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Run local text detection on every Nth frame (default N=1 = every frame).

    Returns a JSON-serializable dict::

        {
          "video": "<resolved path>",
          "detector": "dbnet_onnx",
          "stride": 1,
          "frame_count": <decoded frames>,
          "frames": [
            {"frame_index": 0, "time_ms": 0, "boxes": [{"x","y","w","h"}, ...]},
            ...
          ]
        }

    Empty ``boxes`` means no text detected on that frame (still emitted).
    """
    stride = max(1, int(frame_stride))
    det = detector
    if det is None:
        path = ensure_dbnet_onnx(Path(model_path) if model_path else None)
        logger.info("[PerFrameDetect] LocalTextDetector model=%s", path)
        det = LocalTextDetector(path)

    frames_out: list[dict[str, Any]] = []
    decoded = 0

    with resolve_video_source(video_source) as video_path:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FrameSamplingError(
                FrameSamplingErrorCode.SOURCE_RESOLVE_FAILED,
                f"OpenCV cannot open video: {video_path}",
            )

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 1e-3:
            fps = 30.0
        total_hint = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

        try:
            frame_index = 0
            while True:
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    break
                decoded += 1

                if frame_index % stride != 0:
                    frame_index += 1
                    continue

                time_ms = int(round(frame_index * 1000.0 / fps))
                boxes = [_box_to_dict(b) for b in det.detect(bgr)]
                frames_out.append(
                    {
                        "frame_index": frame_index,
                        "time_ms": time_ms,
                        "boxes": boxes,
                    }
                )

                if frame_index % 50 == 0:
                    logger.info(
                        "[PerFrameDetect] frame=%s/%s boxes=%s",
                        frame_index,
                        total_hint or "?",
                        len(boxes),
                    )

                frame_index += 1
                if total_hint > 0 and frame_index > total_hint + stride:
                    break
        finally:
            cap.release()

        resolved = str(video_path.resolve())
        fingerprint = video_content_fingerprint(video_path)

    payload: dict[str, Any] = {
        "video": resolved,
        "video_fingerprint": fingerprint,
        "detector": "dbnet_onnx",
        "stride": stride,
        "frame_count": decoded,
        "evaluated_frames": len(frames_out),
        "frames": frames_out,
    }
    logger.info(
        "[PerFrameDetect] done decoded=%s evaluated=%s stride=%s",
        decoded,
        len(frames_out),
        stride,
    )
    return payload


def write_per_frame_boxes_json(payload: dict[str, Any], output_path: str | Path) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect text boxes on every video frame (local DBNet only).",
    )
    parser.add_argument("--video", required=True, help="Local video path or http(s) URL")
    parser.add_argument(
        "--out",
        required=True,
        help="Output JSON path (per-frame boxes)",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=1,
        help="Evaluate every Nth frame (default 1 = every frame)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional path to dbnet.onnx (default: apps/api/models/dbnet.onnx)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    payload = detect_text_boxes_every_frame(
        args.video,
        frame_stride=args.stride,
        model_path=args.model,
    )
    out = write_per_frame_boxes_json(payload, args.out)
    print(f"Wrote {out} evaluated_frames={payload['evaluated_frames']} decoded={payload['frame_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
