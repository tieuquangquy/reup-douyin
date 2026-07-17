"""Phase 2 pipeline: OCR sampled frames → keep bottom-band subtitle boxes.

Perf defaults (override via env):
- Crop bottom band before OCR (smaller upload / faster Paddle)
- Parallel HTTP detect (OCR_HTTP_CONCURRENCY, default 4)
- Probe stride + early-exit when probe finds no hard-sub (OCR_PROBE_STRIDE)
"""

from __future__ import annotations

import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.media_pipeline.ocr_filtering.errors import OcrFilteringError, OcrFilteringErrorCode
from src.media_pipeline.ocr_filtering.providers import OcrProvider, build_default_ocr_provider
from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    crop_bottom_band_jpeg,
    filter_subtitle_band_boxes,
    remap_box_from_band_crop,
)
from src.media_pipeline.ocr_filtering.types import (
    FrameOcrDetection,
    FrameOcrFilterResult,
    OcrFilteringResult,
    frame_id_from_path,
)

logger = logging.getLogger(__name__)

OCR_HTTP_CONCURRENCY_ENV = "OCR_HTTP_CONCURRENCY"
OCR_PROBE_STRIDE_ENV = "OCR_PROBE_STRIDE"
OCR_CROP_BAND_ENV = "OCR_CROP_BAND"
OCR_PROBE_EARLY_EXIT_ENV = "OCR_PROBE_EARLY_EXIT"

DEFAULT_OCR_HTTP_CONCURRENCY = 4
DEFAULT_OCR_PROBE_STRIDE = 2


def resolve_ocr_http_concurrency(override: int | None = None) -> int:
    if override is not None:
        return max(1, int(override))
    raw = os.environ.get(OCR_HTTP_CONCURRENCY_ENV, "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            logger.warning("invalid_%s", OCR_HTTP_CONCURRENCY_ENV, extra={"raw": raw[:40]})
    return DEFAULT_OCR_HTTP_CONCURRENCY


def resolve_ocr_probe_stride(override: int | None = None) -> int:
    if override is not None:
        return max(1, int(override))
    raw = os.environ.get(OCR_PROBE_STRIDE_ENV, "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            logger.warning("invalid_%s", OCR_PROBE_STRIDE_ENV, extra={"raw": raw[:40]})
    return DEFAULT_OCR_PROBE_STRIDE


def resolve_ocr_crop_band(override: bool | None = None) -> bool:
    if override is not None:
        return bool(override)
    raw = os.environ.get(OCR_CROP_BAND_ENV, "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return True


def resolve_ocr_probe_early_exit(override: bool | None = None) -> bool:
    if override is not None:
        return bool(override)
    raw = os.environ.get(OCR_PROBE_EARLY_EXIT_ENV, "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _time_ms_for_index(index: int, frame_time_ms: list[int] | None) -> int:
    if frame_time_ms is not None and index < len(frame_time_ms):
        return int(frame_time_ms[index])
    return index * 1000


def _detect_frame(
    provider: OcrProvider,
    path: Path,
    *,
    band_ratio: float,
    crop_band: bool,
    crop_dir: Path | None,
) -> FrameOcrDetection:
    """OCR one frame; optionally crop bottom band then remap boxes to full frame."""
    if crop_band and crop_dir is not None:
        crop_path = crop_dir / f"{path.stem}__band.jpg"
        try:
            full_w, full_h, _crop_h = crop_bottom_band_jpeg(
                path,
                crop_path,
                band_ratio=band_ratio,
            )
            detection = provider.detect_image(crop_path)
            remapped = [
                remap_box_from_band_crop(box, band_ratio=band_ratio) for box in detection.boxes
            ]
            return FrameOcrDetection(
                frame_width=full_w,
                frame_height=full_h,
                boxes=remapped,
            )
        except OcrFilteringError:
            raise
        except Exception as exc:  # noqa: BLE001 — invalid JPEG / missing PIL → full-frame fallback
            logger.warning(
                "ocr_band_crop_fallback",
                extra={"path": path.name, "error": str(exc)[:200]},
            )
    try:
        return provider.detect_image(path)
    except OcrFilteringError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
            f"OCR failed for {path.name}: {exc}",
        ) from exc


def _filter_detection(
    path: Path,
    time_ms: int,
    detection: FrameOcrDetection,
    *,
    band_ratio: float,
) -> tuple[FrameOcrFilterResult, list[str]]:
    kept = filter_subtitle_band_boxes(detection.boxes, band_ratio=band_ratio)
    filtered_out = len(detection.boxes) - len(kept)
    warnings: list[str] = []
    if filtered_out:
        warnings.append(f"filtered_top_region:{path.name}:{filtered_out}")
    result = FrameOcrFilterResult(
        frame_id=frame_id_from_path(path),
        path=str(path),
        time_ms=time_ms,
        frame_width=detection.frame_width,
        frame_height=detection.frame_height,
        boxes=kept,
        raw_box_count=len(detection.boxes),
        filtered_out_count=filtered_out,
    )
    return result, warnings


def _empty_frame_result(
    path: Path,
    time_ms: int,
    *,
    frame_width: int,
    frame_height: int,
) -> FrameOcrFilterResult:
    return FrameOcrFilterResult(
        frame_id=frame_id_from_path(path),
        path=str(path),
        time_ms=time_ms,
        frame_width=frame_width,
        frame_height=frame_height,
        boxes=[],
        raw_box_count=0,
        filtered_out_count=0,
    )


def _run_indices_parallel(
    indices: list[int],
    frame_paths: list[Path],
    *,
    provider: OcrProvider,
    frame_time_ms: list[int] | None,
    band_ratio: float,
    crop_band: bool,
    crop_dir: Path | None,
    concurrency: int,
) -> dict[int, tuple[FrameOcrFilterResult, list[str]]]:
    out: dict[int, tuple[FrameOcrFilterResult, list[str]]] = {}
    if not indices:
        return out

    def _one(index: int) -> tuple[int, FrameOcrFilterResult, list[str]]:
        path = Path(frame_paths[index])
        if not path.is_file():
            raise OcrFilteringError(
                OcrFilteringErrorCode.FRAME_MISSING,
                f"Frame image missing: {path}",
            )
        time_ms = _time_ms_for_index(index, frame_time_ms)
        detection = _detect_frame(
            provider,
            path,
            band_ratio=band_ratio,
            crop_band=crop_band,
            crop_dir=crop_dir,
        )
        filtered, warns = _filter_detection(path, time_ms, detection, band_ratio=band_ratio)
        logger.info(
            "ocr_frame_filtered",
            extra={
                "frame_id": path.stem,
                "time_ms": time_ms,
                "raw": filtered.raw_box_count,
                "kept": len(filtered.boxes),
            },
        )
        return index, filtered, warns

    workers = max(1, min(concurrency, len(indices)))
    if workers == 1:
        for index in indices:
            idx, filtered, warns = _one(index)
            out[idx] = (filtered, warns)
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, index) for index in indices]
        for fut in as_completed(futures):
            idx, filtered, warns = fut.result()
            out[idx] = (filtered, warns)
    return out


def run_ocr_filtering(
    frame_paths: list[Path],
    *,
    ocr_provider: OcrProvider | None = None,
    frame_time_ms: list[int] | None = None,
    band_ratio: float = BOTTOM_BAND_RATIO,
    crop_band: bool | None = None,
    concurrency: int | None = None,
    probe_stride: int | None = None,
    early_exit_empty_probe: bool | None = None,
) -> OcrFilteringResult:
    """Run OCR on sampled frames and keep only bottom-band (default: lower 1/3) boxes.

    Parameters
    ----------
    frame_paths:
        Output of Phase 1 `extract_video_frames` (JPEG paths).
    frame_time_ms:
        Optional aligned timecodes from Phase 1. If omitted, index * 1000 is used.
    band_ratio:
        Fraction of frame height treated as subtitle zone (default 1/3).
    crop_band:
        When True, OCR only the bottom band crop (remap boxes to full frame).
    concurrency:
        Parallel OCR workers (default OCR_HTTP_CONCURRENCY or 4).
    probe_stride:
        First OCR every Nth frame; if all empty and early_exit, skip the rest.
    early_exit_empty_probe:
        Skip unprobed frames when the probe pass finds no subtitle boxes.
    """
    if not frame_paths:
        raise OcrFilteringError(
            OcrFilteringErrorCode.EMPTY_INPUT,
            "frame_paths is empty — run Phase 1 extract_video_frames first",
        )

    provider = ocr_provider or build_default_ocr_provider()
    use_crop = resolve_ocr_crop_band(crop_band)
    workers = resolve_ocr_http_concurrency(concurrency)
    stride = resolve_ocr_probe_stride(probe_stride)
    early_exit = resolve_ocr_probe_early_exit(early_exit_empty_probe)

    warnings: list[str] = []
    n = len(frame_paths)
    all_indices = list(range(n))
    probe_indices = list(range(0, n, stride))
    remaining_indices = [i for i in all_indices if i not in set(probe_indices)]

    with tempfile.TemporaryDirectory(prefix="ocr_band_crop_") as crop_tmp:
        crop_dir = Path(crop_tmp) if use_crop else None
        probed = _run_indices_parallel(
            probe_indices,
            frame_paths,
            provider=provider,
            frame_time_ms=frame_time_ms,
            band_ratio=band_ratio,
            crop_band=use_crop,
            crop_dir=crop_dir,
            concurrency=workers,
        )
        probe_has_boxes = any(len(item[0].boxes) > 0 for item in probed.values())

        by_index: dict[int, FrameOcrFilterResult] = {
            idx: item[0] for idx, item in probed.items()
        }
        for _idx, (_frame, warns) in probed.items():
            warnings.extend(warns)

        if remaining_indices and (probe_has_boxes or not early_exit or stride <= 1):
            rest = _run_indices_parallel(
                remaining_indices,
                frame_paths,
                provider=provider,
                frame_time_ms=frame_time_ms,
                band_ratio=band_ratio,
                crop_band=use_crop,
                crop_dir=crop_dir,
                concurrency=workers,
            )
            for idx, (frame, warns) in rest.items():
                by_index[idx] = frame
                warnings.extend(warns)
        elif remaining_indices and early_exit and not probe_has_boxes:
            warnings.append("ocr_probe_empty_early_exit")
            # Prefer size from a probed frame; else leave 0.
            sample_w = next((f.frame_width for f in by_index.values() if f.frame_width), 0)
            sample_h = next((f.frame_height for f in by_index.values() if f.frame_height), 0)
            for idx in remaining_indices:
                path = Path(frame_paths[idx])
                by_index[idx] = _empty_frame_result(
                    path,
                    _time_ms_for_index(idx, frame_time_ms),
                    frame_width=sample_w,
                    frame_height=sample_h,
                )
            logger.info(
                "ocr_probe_early_exit",
                extra={
                    "probed": len(probe_indices),
                    "skipped": len(remaining_indices),
                    "stride": stride,
                },
            )

    frames = [by_index[i] for i in all_indices]
    result = OcrFilteringResult(
        frame_count=len(frames),
        frames=frames,
        warnings=list(dict.fromkeys(warnings)),
        provider=getattr(provider, "provider_name", "unknown"),
    )
    logger.info(
        "ocr_filtering_completed",
        extra={
            "frames": result.frame_count,
            "provider": result.provider,
            "concurrency": workers,
            "probe_stride": stride,
            "crop_band": use_crop,
        },
    )
    return result
