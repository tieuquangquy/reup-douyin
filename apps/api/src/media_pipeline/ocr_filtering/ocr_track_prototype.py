"""Prototype: Cloud OCR @ N fps → hold-forward densify → JSON + overlay previews.

Does not wire into ANALYZE_OCR. Detect/OCR authority only; no blur/sub.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2

from src.media_pipeline.frame_sampling.resolve_source import resolve_video_source
from src.media_pipeline.ocr_filtering.async_batch import process_all_frames_sync
from src.media_pipeline.ocr_filtering.box_timeline_tracker import (
    OcrObservation,
    densify_hold_forward,
    observations_from_ocr_payload,
)
from src.media_pipeline.ocr_filtering.clean_box_authority import (
    DEFAULT_MIN_CONFIDENCE,
    apply_temporal_consensus,
    collapse_nearby_observations,
)
from src.media_pipeline.ocr_filtering.box_geometry_refine import refine_timed_boxes_from_jpeg
from src.media_pipeline.ocr_filtering.per_frame_ink_scan import scan_refine_dense_timeline
from src.media_pipeline.ocr_filtering.overlay_zones import MID_TITLE_Y_MAX, MID_TITLE_Y_MIN
from src.media_pipeline.ocr_filtering.providers import resolve_ocr_endpoint_url
from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    crop_vertical_band_jpeg,
    remap_box_from_vertical_crop,
    subtitle_band_top_normalized,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox

logger = logging.getLogger(__name__)


def _extract_stills_at_times(
    video_path: Path,
    times_ms: list[int],
    out_dir: Path,
) -> list[tuple[int, Path]]:
    """Extract one JPEG per time_ms (seek by frame index from fps)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    written: list[tuple[int, Path]] = []
    try:
        for t_ms in times_ms:
            frame_index = int(round((t_ms / 1000.0) * fps))
            if total > 0:
                frame_index = max(0, min(frame_index, total - 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, bgr = cap.read()
            if not ok or bgr is None:
                logger.warning("extract_miss time_ms=%s index=%s", t_ms, frame_index)
                continue
            dest = out_dir / f"ocr_{t_ms:06d}.jpg"
            cv2.imwrite(str(dest), bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            written.append((t_ms, dest))
    finally:
        cap.release()
    return written


def _all_frame_times_ms(video_path: Path) -> list[int]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            # Fallback: read through
            times: list[int] = []
            idx = 0
            while True:
                ok, _ = cap.read()
                if not ok:
                    break
                times.append(int(round(idx * 1000.0 / fps)))
                idx += 1
            return times
        return [int(round(i * 1000.0 / fps)) for i in range(total)]
    finally:
        cap.release()


def _sample_times_ms(duration_ms: int, sample_fps: float) -> list[int]:
    if sample_fps <= 0:
        raise ValueError("sample_fps must be > 0")
    step = int(round(1000.0 / float(sample_fps)))
    step = max(1, step)
    times = list(range(0, max(0, duration_ms) + 1, step))
    if not times or times[-1] < duration_ms:
        times.append(duration_ms)
    # unique sorted
    return sorted(set(times))


def _dual_band_crops(
    full_jpeg: Path,
    out_dir: Path,
    *,
    stem: str,
) -> list[tuple[str, Path, float, float]]:
    """Return [(kind, crop_path, y0, y1), ...] for mid-title + hardsub bands."""
    out_dir.mkdir(parents=True, exist_ok=True)
    hard_y0 = subtitle_band_top_normalized(BOTTOM_BAND_RATIO)
    mid_y0 = float(MID_TITLE_Y_MIN)
    mid_y1 = min(float(MID_TITLE_Y_MAX), hard_y0)
    crops: list[tuple[str, Path, float, float]] = []
    mid_path = out_dir / f"{stem}_mid.jpg"
    crop_vertical_band_jpeg(full_jpeg, mid_path, y0_norm=mid_y0, y1_norm=mid_y1)
    crops.append(("mid", mid_path, mid_y0, mid_y1))
    hard_path = out_dir / f"{stem}_hard.jpg"
    crop_vertical_band_jpeg(full_jpeg, hard_path, y0_norm=hard_y0, y1_norm=1.0)
    crops.append(("hard", hard_path, hard_y0, 1.0))
    return crops


def _bottom_band_crop(full_jpeg: Path, out_dir: Path, *, stem: str) -> tuple[Path, float, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hard_y0 = subtitle_band_top_normalized(BOTTOM_BAND_RATIO)
    hard_path = out_dir / f"{stem}_hard.jpg"
    crop_vertical_band_jpeg(full_jpeg, hard_path, y0_norm=hard_y0, y1_norm=1.0)
    return hard_path, hard_y0, 1.0


def _mid_title_band_crop(full_jpeg: Path, out_dir: Path, *, stem: str) -> tuple[Path, float, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hard_y0 = subtitle_band_top_normalized(BOTTOM_BAND_RATIO)
    mid_y0 = float(MID_TITLE_Y_MIN)
    mid_y1 = min(float(MID_TITLE_Y_MAX), hard_y0)
    mid_path = out_dir / f"{stem}_mid.jpg"
    crop_vertical_band_jpeg(full_jpeg, mid_path, y0_norm=mid_y0, y1_norm=mid_y1)
    return mid_path, mid_y0, mid_y1


def run_ocr_track_prototype(
    video_source: str | Path,
    *,
    sample_fps: float = 2.0,
    ocr_frame_indices: list[int] | None = None,
    out_json: Path,
    overlay_dir: Path | None = None,
    overlay_indices: list[int] | None = None,
    overlay_all: bool = False,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    concurrency: int | None = 2,
    use_dual_band: bool = False,
    use_hard_band_only: bool = True,
    use_mid_title_band: bool = True,
    use_bottom_band_assist: bool = False,
    use_change_ticks: bool = True,
    consensus_min_hits: int = 2,
) -> dict[str, Any]:
    with resolve_video_source(video_source) as video_path:
        frame_times = _all_frame_times_ms(video_path)
        duration_ms = frame_times[-1] if frame_times else 0
        if ocr_frame_indices:
            sample_times = []
            for idx in ocr_frame_indices:
                i = max(0, min(int(idx), len(frame_times) - 1)) if frame_times else 0
                sample_times.append(frame_times[i] if frame_times else 0)
            sample_times = sorted(set(sample_times))
        elif use_change_ticks and not use_dual_band:
            from src.media_pipeline.ocr_filtering.bottom_band_change_ticks import (
                sample_bottom_band_change_times_ms,
            )

            sample_times = sample_bottom_band_change_times_ms(video_path)
        else:
            sample_times = _sample_times_ms(duration_ms, sample_fps)
        # Always OCR explicit overlay QA frames so visual checks are not hold-only.
        if overlay_indices and frame_times:
            for idx in overlay_indices:
                i = max(0, min(int(idx), len(frame_times) - 1))
                sample_times.append(frame_times[i])
            sample_times = sorted(set(sample_times))
        logger.info(
            "ocr_track_proto video=%s frames=%s duration_ms=%s ocr_ticks=%s "
            "hard_only=%s mid=%s dual_band=%s change_ticks=%s",
            video_path.name,
            len(frame_times),
            duration_ms,
            len(sample_times),
            use_hard_band_only,
            use_mid_title_band,
            use_dual_band,
            use_change_ticks and not bool(ocr_frame_indices),
        )

        with tempfile.TemporaryDirectory(prefix="ocr_track_") as tmp:
            tmp_path = Path(tmp)
            stills = _extract_stills_at_times(video_path, sample_times, tmp_path / "full")
            endpoint = resolve_ocr_endpoint_url()

            crop_jobs: list[tuple[int, str, Path, float, float]] = []
            if use_dual_band:
                for t_ms, full in stills:
                    for kind, crop_path, y0, y1 in _dual_band_crops(
                        full, tmp_path / "crops", stem=f"t{t_ms:06d}"
                    ):
                        crop_jobs.append((t_ms, kind, crop_path, y0, y1))
            elif use_hard_band_only:
                for t_ms, full in stills:
                    hard_path, y0, y1 = _bottom_band_crop(
                        full, tmp_path / "crops", stem=f"t{t_ms:06d}"
                    )
                    crop_jobs.append((t_ms, "hard", hard_path, y0, y1))
                    # Mid titles are early / sparse — avoid OCR mid on every hardsub change.
                    if use_mid_title_band and int(t_ms) <= 2500:
                        mid_path, my0, my1 = _mid_title_band_crop(
                            full, tmp_path / "crops", stem=f"t{t_ms:06d}"
                        )
                        crop_jobs.append((t_ms, "mid", mid_path, my0, my1))
            else:
                for t_ms, full in stills:
                    crop_jobs.append((t_ms, "full", full, 0.0, 1.0))
                    if use_bottom_band_assist:
                        hard_path, y0, y1 = _bottom_band_crop(
                            full, tmp_path / "crops", stem=f"t{t_ms:06d}"
                        )
                        crop_jobs.append((t_ms, "hard", hard_path, y0, y1))

            paths = [c[2] for c in crop_jobs]
            detections = process_all_frames_sync(
                paths,
                endpoint_url=endpoint,
                concurrency=concurrency,
            )

            by_time: dict[int, list[DetectedTextBox]] = {}
            for (t_ms, kind, _path, y0, y1), det in zip(crop_jobs, detections, strict=True):
                del kind
                remapped = [
                    remap_box_from_vertical_crop(b, y0_norm=y0, y1_norm=y1)
                    if (y0 > 0.0 or y1 < 1.0)
                    else b
                    for b in det.boxes
                ]
                by_time.setdefault(t_ms, []).extend(remapped)

            ocr_frames: list[dict[str, Any]] = []
            for t_ms in sorted(by_time.keys()):
                boxes = by_time[t_ms]
                ocr_frames.append(
                    {
                        "time_ms": t_ms,
                        "path": f"t{t_ms:06d}",
                        "frame_width": 0,
                        "frame_height": 0,
                        "boxes": [
                            {
                                "x": b.x,
                                "y": b.y,
                                "w": b.width,
                                "h": b.height,
                                "text": b.text,
                                "confidence": b.confidence,
                            }
                            for b in boxes
                        ],
                    }
                )

            raw_observations = observations_from_ocr_payload(
                ocr_frames,
                min_confidence=0.0,
                require_text=True,
            )
            observations = apply_temporal_consensus(
                raw_observations,
                min_hits=consensus_min_hits,
            )
            observations = collapse_nearby_observations(observations, gap_ms=900)
            still_by_time = {t_ms: path for t_ms, path in stills}
            refined_obs: list[OcrObservation] = []
            for o in observations:
                still = still_by_time.get(o.time_ms)
                if still is None:
                    # Collapsed tick may map earliest_ms — use nearest still within 50ms.
                    for t_ms, path in stills:
                        if abs(int(t_ms) - int(o.time_ms)) <= 50:
                            still = path
                            break
                if still is not None and o.boxes:
                    boxes = tuple(
                        refine_timed_boxes_from_jpeg(still, list(o.boxes), expand_hardsub=True)
                    )
                    refined_obs.append(OcrObservation(time_ms=o.time_ms, boxes=boxes))
                else:
                    refined_obs.append(o)
            observations = refined_obs
            dense = densify_hold_forward(observations, frame_times, skip_empty=True)
            dense = scan_refine_dense_timeline(video_path, dense, use_band_scan=True)
            for i, row in enumerate(dense):
                row["frame_index"] = i

            authority = (
                "cloud_ocr_hard_mid_change_inkscan_v6"
                if use_hard_band_only
                else "cloud_ocr_full_plus_band_clean_consensus"
            )
            payload: dict[str, Any] = {
                "video": str(video_path.resolve()),
                "authority": authority,
                "sample_fps": None if (ocr_frame_indices or use_change_ticks) else sample_fps,
                "ocr_frame_indices": list(ocr_frame_indices) if ocr_frame_indices else None,
                "ocr_ticks": len(stills),
                "ocr_crop_calls": len(paths),
                "frame_count": len(frame_times),
                "min_confidence": min_confidence,
                "consensus_min_hits": consensus_min_hits,
                "use_dual_band": use_dual_band,
                "use_hard_band_only": use_hard_band_only and not use_dual_band,
                "use_mid_title_band": use_mid_title_band and use_hard_band_only and not use_dual_band,
                "use_change_ticks": use_change_ticks and not bool(ocr_frame_indices),
                "use_bottom_band_assist": use_bottom_band_assist and not use_dual_band and not use_hard_band_only,
                "ocr_observations_raw": [
                    {
                        "time_ms": o.time_ms,
                        "boxes": [b.to_dict() for b in o.boxes],
                    }
                    for o in raw_observations
                ],
                "ocr_observations": [
                    {
                        "time_ms": o.time_ms,
                        "boxes": [b.to_dict() for b in o.boxes],
                    }
                    for o in observations
                ],
                "frames": dense,
            }

            out_json.parent.mkdir(parents=True, exist_ok=True)
            out_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("wrote %s", out_json)

            if overlay_dir is not None:
                _write_overlays(
                    video_path,
                    dense,
                    overlay_dir,
                    indices=overlay_indices,
                    overlay_all=overlay_all,
                )

            return payload


def _resolve_cjk_font(size: int = 22):
    from PIL import ImageFont

    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\arialuni.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_label_pil(rgb, text: str, xy: tuple[int, int], font, fill=(255, 220, 0)) -> None:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(rgb)
    x, y = xy
    # Shadow for readability on busy frames.
    draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)


def _write_overlays(
    video_path: Path,
    dense_frames: list[dict[str, Any]],
    overlay_dir: Path,
    *,
    indices: list[int] | None,
    overlay_all: bool = False,
) -> None:
    from PIL import Image, ImageDraw

    overlay_dir.mkdir(parents=True, exist_ok=True)
    by_idx = {int(f["frame_index"]): f for f in dense_frames}
    if overlay_all:
        indices = sorted(by_idx.keys())
    elif indices is None:
        with_boxes = [f for f in dense_frames if f.get("boxes")]
        if not with_boxes:
            return
        by_count = sorted(with_boxes, key=lambda f: len(f["boxes"]), reverse=True)
        picks = [int(by_count[0]["frame_index"])]
        step = max(1, len(with_boxes) // 7)
        for i in range(0, len(with_boxes), step):
            picks.append(int(with_boxes[i]["frame_index"]))
        indices = []
        seen: set[int] = set()
        for i in sorted(picks):
            if i not in seen:
                seen.add(i)
                indices.append(i)
        indices = indices[:8]

    font = _resolve_cjk_font(22)
    meta_font = _resolve_cjk_font(28)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video for overlay: {video_path}")
    try:
        for target in indices:
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
                draw.rectangle([x0, y0, x1, y1], outline=(255, 220, 0), width=3)
                label = (b.get("text") or "").strip()
                if label:
                    _draw_label_pil(rgb, label[:24], (x0, max(4, y0 - 28)), font)
            src = entry.get("ocr_source_ms")
            meta = (
                f"f{target} t={entry['time_ms']}ms n={len(entry.get('boxes') or [])} "
                f"ocr@{src}ms"
            )
            _draw_label_pil(rgb, meta, (12, 10), meta_font)
            dest = (
                overlay_dir
                / f"ocr_track_f{target:06d}_t{entry['time_ms']:06d}_n{len(entry.get('boxes') or [])}.jpg"
            )
            rgb.save(dest, format="JPEG", quality=90)
            logger.info("overlay %s", dest.name)
    finally:
        cap.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCR@Nfps + hold-forward track prototype")
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True, help="Dense per-frame boxes JSON")
    parser.add_argument("--overlay-dir", default=None)
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument(
        "--ocr-frame-indices",
        default=None,
        help="Comma-separated frame indices to OCR (overrides --sample-fps)",
    )
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument(
        "--dual-band",
        action="store_true",
        help="Legacy mid+hard dual crops (overrides hard-band-only)",
    )
    parser.add_argument(
        "--full-frame",
        action="store_true",
        help="OCR full frames instead of hard-band-only (legacy)",
    )
    parser.add_argument(
        "--no-mid-title",
        action="store_true",
        help="Skip mid-title band OCR (hardsub band only)",
    )
    parser.add_argument(
        "--fixed-fps",
        action="store_true",
        help="Use --sample-fps grid instead of bottom-band change ticks",
    )
    parser.add_argument("--consensus-min-hits", type=int, default=2)
    parser.add_argument(
        "--overlay-all",
        action="store_true",
        help="Write overlay JPG for every densified frame (default: auto pick 8)",
    )
    parser.add_argument(
        "--overlay-indices",
        default=None,
        help="Comma-separated frame indices (default: auto pick 8)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    indices = None
    if args.overlay_indices:
        indices = [int(x.strip()) for x in args.overlay_indices.split(",") if x.strip()]
    ocr_indices = None
    if args.ocr_frame_indices:
        ocr_indices = [int(x.strip()) for x in args.ocr_frame_indices.split(",") if x.strip()]

    from src.media_pipeline.ocr_filtering.async_batch import _ensure_ocr_async_env_loaded

    _ensure_ocr_async_env_loaded()

    run_ocr_track_prototype(
        args.video,
        sample_fps=args.sample_fps,
        ocr_frame_indices=ocr_indices,
        out_json=Path(args.out),
        overlay_dir=Path(args.overlay_dir) if args.overlay_dir else None,
        overlay_indices=indices,
        overlay_all=bool(args.overlay_all),
        min_confidence=args.min_confidence,
        concurrency=args.concurrency,
        use_dual_band=bool(args.dual_band),
        use_hard_band_only=not bool(args.full_frame) and not bool(args.dual_band),
        use_mid_title_band=not bool(args.no_mid_title),
        use_bottom_band_assist=False,
        use_change_ticks=not bool(args.fixed_fps),
        consensus_min_hits=args.consensus_min_hits,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
