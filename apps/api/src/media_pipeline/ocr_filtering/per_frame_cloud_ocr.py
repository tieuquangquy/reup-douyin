"""Full per-frame Cloud OCR: one OCR call per frame per band crop.

Position and text both come from Paddle on the same frame — no hold-forward,
no local ink/DBNet geometry authority. Uses bottom hardsub band (+ optional
mid-title band) crops to keep payloads small.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.resolve_source import resolve_video_source
from src.media_pipeline.ocr_filtering.async_batch import process_all_frames_sync
from src.media_pipeline.ocr_filtering.clean_box_authority import (
    DEFAULT_MIN_CONFIDENCE,
    filter_authority_boxes,
    merge_horizontal_line_boxes,
)
from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox
from src.media_pipeline.ocr_filtering.overlay_zones import MID_TITLE_Y_MAX, MID_TITLE_Y_MIN
from src.media_pipeline.ocr_filtering.providers import resolve_ocr_endpoint_url
from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    remap_box_from_vertical_crop,
    subtitle_band_top_normalized,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrDetection

logger = logging.getLogger(__name__)

CropJob = tuple[int, int, str, float, float]  # frame_index, time_ms, kind, y0, y1


@dataclass(frozen=True)
class CropJobEntry:
    frame_index: int
    time_ms: int
    kind: str
    path: Path
    y0: float
    y1: float


def _crop_band_jpeg(bgr: np.ndarray, dest: Path, *, y0: float, y1: float) -> None:
    from PIL import Image

    h, w = bgr.shape[:2]
    y0n = max(0.0, min(1.0, float(y0)))
    y1n = max(y0n + 0.05, min(1.0, float(y1)))
    top = max(0, min(h - 1, int(round(h * y0n))))
    bottom = max(top + 1, min(h, int(round(h * y1n))))
    rgb = cv2.cvtColor(bgr[top:bottom, :], cv2.COLOR_BGR2RGB)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(dest, format="JPEG", quality=90)


# Mid titles appear early; OCR mid-band every frame doubles API cost for little gain.
DEFAULT_MID_BAND_MAX_MS = 2500


def extract_per_frame_band_crops(
    video_path: Path,
    out_dir: Path,
    *,
    include_mid_band: bool = True,
    mid_band_max_ms: int = DEFAULT_MID_BAND_MAX_MS,
    frame_stride: int = 1,
) -> list[CropJobEntry]:
    """Extract bottom (+ optional early mid) band JPEG for every Nth frame."""
    stride = max(1, int(frame_stride))
    hard_y0 = subtitle_band_top_normalized(BOTTOM_BAND_RATIO)
    mid_y0 = float(MID_TITLE_Y_MIN)
    mid_y1 = min(float(MID_TITLE_Y_MAX), hard_y0)
    jobs: list[CropJobEntry] = []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        frame_index = 0
        while True:
            ok, bgr = cap.read()
            if not ok or bgr is None:
                break
            if frame_index % stride == 0:
                time_ms = int(round(frame_index * 1000.0 / fps))
                stem = f"f{frame_index:06d}_t{time_ms:06d}"
                hard_path = out_dir / f"{stem}_hard.jpg"
                _crop_band_jpeg(bgr, hard_path, y0=hard_y0, y1=1.0)
                jobs.append(
                    CropJobEntry(
                        frame_index=frame_index,
                        time_ms=time_ms,
                        kind="hard",
                        path=hard_path,
                        y0=hard_y0,
                        y1=1.0,
                    )
                )
                if include_mid_band and int(time_ms) <= int(mid_band_max_ms):
                    mid_path = out_dir / f"{stem}_mid.jpg"
                    _crop_band_jpeg(bgr, mid_path, y0=mid_y0, y1=mid_y1)
                    jobs.append(
                        CropJobEntry(
                            frame_index=frame_index,
                            time_ms=time_ms,
                            kind="mid",
                            path=mid_path,
                            y0=mid_y0,
                            y1=mid_y1,
                        )
                    )
                if frame_index % 100 == 0:
                    logger.info("[PerFrameCloudOCR] crop frame=%s", frame_index)
            frame_index += 1
    finally:
        cap.release()
    logger.info("[PerFrameCloudOCR] crops=%s frames=%s", len(jobs), frame_index)
    return jobs


def _detection_to_timed_boxes(
    det: FrameOcrDetection,
    *,
    y0: float,
    y1: float,
) -> list[TimedBox]:
    out: list[TimedBox] = []
    for b in det.boxes:
        remapped = (
            remap_box_from_vertical_crop(b, y0_norm=y0, y1_norm=y1)
            if (y0 > 0.0 or y1 < 1.0)
            else b
        )
        out.append(
            TimedBox(
                x=float(remapped.x),
                y=float(remapped.y),
                w=float(remapped.width),
                h=float(remapped.height),
                text=str(remapped.text or ""),
                confidence=float(remapped.confidence or 0.0),
            )
        )
    return out


def merge_boxes_by_frame(
    job_detections: Sequence[tuple[CropJob, FrameOcrDetection]],
) -> list[dict[str, Any]]:
    """Group remapped OCR boxes by frame_index."""
    by_frame: dict[int, dict[str, Any]] = {}
    for (frame_index, time_ms, _kind, y0, y1), det in job_detections:
        row = by_frame.setdefault(
            frame_index,
            {"frame_index": frame_index, "time_ms": time_ms, "raw_boxes": []},
        )
        row["raw_boxes"].extend(_detection_to_timed_boxes(det, y0=y0, y1=y1))
    return [by_frame[k] for k in sorted(by_frame.keys())]


def build_frames_from_crop_results(
    merged_rows: Sequence[dict[str, Any]],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> list[dict[str, Any]]:
    """Filter/merge line boxes per frame — authority is OCR on that frame only."""
    frames: list[dict[str, Any]] = []
    for row in merged_rows:
        raw: list[TimedBox] = list(row.get("raw_boxes") or [])
        filtered = filter_authority_boxes(raw, min_confidence=min_confidence)
        lines = merge_horizontal_line_boxes(filtered)
        frames.append(
            {
                "frame_index": int(row["frame_index"]),
                "time_ms": int(row["time_ms"]),
                "boxes": [b.to_dict() for b in lines],
                "ocr_source_frame": int(row["frame_index"]),
                "position_hold_forward": False,
            }
        )
    return frames


def run_per_frame_cloud_ocr(
    video_source: str | Path,
    *,
    out_json: Path,
    overlay_dir: Path | None = None,
    overlay_all: bool = False,
    overlay_indices: list[int] | None = None,
    concurrency: int | None = 2,
    include_mid_band: bool = True,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    frame_stride: int = 1,
) -> dict[str, Any]:
    with resolve_video_source(video_source) as video_path:
        with tempfile.TemporaryDirectory(prefix="pfc_ocr_") as tmp:
            tmp_path = Path(tmp)
            jobs = extract_per_frame_band_crops(
                video_path,
                tmp_path / "crops",
                include_mid_band=include_mid_band,
                frame_stride=frame_stride,
            )
            if not jobs:
                raise RuntimeError("No frames extracted")

            endpoint = resolve_ocr_endpoint_url()
            paths = [j.path for j in jobs]
            logger.info(
                "[PerFrameCloudOCR] ocr_start crops=%s concurrency=%s",
                len(paths),
                concurrency,
            )

            def _progress(done: int, total: int) -> None:
                if done == total or done % 25 == 0:
                    logger.info(
                        "[PerFrameCloudOCR] ocr_progress %s/%s (%.0f%%)",
                        done,
                        total,
                        100.0 * done / max(1, total),
                    )

            detections = process_all_frames_sync(
                paths,
                endpoint_url=endpoint,
                concurrency=concurrency,
                on_frame_done=_progress,
            )
            job_tuples: list[tuple[CropJob, FrameOcrDetection]] = []
            for job, det in zip(jobs, detections, strict=True):
                job_tuples.append(
                    (
                        (job.frame_index, job.time_ms, job.kind, job.y0, job.y1),
                        det,
                    )
                )
            merged = merge_boxes_by_frame(job_tuples)
            frames = build_frames_from_crop_results(merged, min_confidence=min_confidence)

            evaluated = len(frames)
            with_boxes = sum(1 for f in frames if f.get("boxes"))
            payload: dict[str, Any] = {
                "video": str(video_path.resolve()),
                "authority": "per_frame_cloud_ocr_v1",
                "frame_count": evaluated,
                "evaluated_frames": evaluated,
                "ocr_crop_calls": len(paths),
                "include_mid_band": include_mid_band,
                "frame_stride": frame_stride,
                "min_confidence": min_confidence,
                "position_hold_forward": False,
                "frames_with_boxes": with_boxes,
                "frames": frames,
            }
            out_json.parent.mkdir(parents=True, exist_ok=True)
            out_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "wrote %s frames=%s with_boxes=%s ocr_calls=%s",
                out_json,
                evaluated,
                with_boxes,
                len(paths),
            )

            if overlay_dir is not None:
                _write_overlays(
                    video_path,
                    frames,
                    overlay_dir,
                    indices=overlay_indices,
                    overlay_all=overlay_all,
                )
            return payload


def _write_overlays(
    video_path: Path,
    frames: list[dict[str, Any]],
    overlay_dir: Path,
    *,
    indices: list[int] | None,
    overlay_all: bool = False,
) -> None:
    from src.media_pipeline.ocr_filtering.ocr_track_prototype import (
        _draw_label_pil,
        _resolve_cjk_font,
    )
    from PIL import Image, ImageDraw

    overlay_dir.mkdir(parents=True, exist_ok=True)
    by_idx = {int(f["frame_index"]): f for f in frames}
    if overlay_all:
        indices = sorted(by_idx.keys())
    elif indices is None:
        with_boxes = [f for f in frames if f.get("boxes")]
        step = max(1, len(with_boxes) // 8)
        indices = [int(with_boxes[i]["frame_index"]) for i in range(0, len(with_boxes), step)][:8]

    font = _resolve_cjk_font(22)
    meta_font = _resolve_cjk_font(28)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video for overlay: {video_path}")
    try:
        for target in indices or []:
            entry = by_idx.get(target)
            if entry is None:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ok, bgr = cap.read()
            if not ok or bgr is None:
                continue
            h, w = bgr.shape[:2]
            rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(rgb)
            for b in entry.get("boxes") or []:
                bw = float(b.get("w") if "w" in b else b.get("width") or 0.01)
                bh = float(b.get("h") if "h" in b else b.get("height") or 0.01)
                x0 = int(round(float(b["x"]) * w))
                y0 = int(round(float(b["y"]) * h))
                x1 = int(round((float(b["x"]) + bw) * w))
                y1 = int(round((float(b["y"]) + bh) * h))
                draw.rectangle([x0, y0, x1, y1], outline=(255, 80, 220), width=3)
                label = (b.get("text") or "").strip()
                if label:
                    _draw_label_pil(rgb, label[:28], (x0, max(4, y0 - 28)), font, fill=(255, 80, 220))
            meta = (
                f"f{target} t={entry['time_ms']}ms n={len(entry.get('boxes') or [])} "
                f"ocr@f{entry.get('ocr_source_frame')}"
            )
            _draw_label_pil(rgb, meta, (12, 10), meta_font, fill=(255, 200, 120))
            dest = (
                overlay_dir
                / f"pfc_f{target:06d}_t{entry['time_ms']:06d}_n{len(entry.get('boxes') or [])}.jpg"
            )
            rgb.save(dest, format="JPEG", quality=90)
            if target % 100 == 0:
                logger.info("overlay %s", dest.name)
    finally:
        cap.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cloud OCR on every frame (band crops)")
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overlay-dir", default=None)
    parser.add_argument("--overlay-all", action="store_true")
    parser.add_argument("--overlay-indices", default=None)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--stride", type=int, default=1, help="Process every Nth frame")
    parser.add_argument(
        "--hard-only",
        action="store_true",
        help="Skip mid-title band OCR (half the API calls)",
    )
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    from src.media_pipeline.ocr_filtering.async_batch import _ensure_ocr_async_env_loaded

    _ensure_ocr_async_env_loaded()

    indices = None
    if args.overlay_indices:
        indices = [int(x.strip()) for x in args.overlay_indices.split(",") if x.strip()]

    run_per_frame_cloud_ocr(
        args.video,
        out_json=Path(args.out),
        overlay_dir=Path(args.overlay_dir) if args.overlay_dir else None,
        overlay_all=bool(args.overlay_all),
        overlay_indices=indices,
        concurrency=args.concurrency,
        include_mid_band=not bool(args.hard_only),
        min_confidence=args.min_confidence,
        frame_stride=args.stride,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
