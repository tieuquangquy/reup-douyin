"""Phase 2 pipeline: OCR sampled frames → keep ALL on-screen text boxes.

Perf defaults (override via env):
- Full-frame OCR (no band crop) — set OCR_CROP_BAND=1 to restore legacy crop
- Async aiohttp batch for REST OCR (OCR_HTTP_CONCURRENCY, default 3)
- Probe stride / early-exit optional (off by default for full-screen coverage)
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.media_pipeline.ocr_filtering.async_batch import (
    DEFAULT_ASYNC_CONCURRENCY,
    process_all_frames_sync,
)
from src.media_pipeline.ocr_filtering.errors import OcrFilteringError, OcrFilteringErrorCode
from src.media_pipeline.ocr_filtering.providers import (
    OcrProvider,
    RestOcrEndpointProvider,
    RetryingOcrProvider,
    build_default_ocr_provider,
)
from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    crop_vertical_band_jpeg,
    remap_box_from_vertical_crop,
)
from src.media_pipeline.ocr_filtering.overlay_zones import OVERLAY_CROP_TOP
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

DEFAULT_OCR_HTTP_CONCURRENCY = DEFAULT_ASYNC_CONCURRENCY
DEFAULT_OCR_PROBE_STRIDE = 1


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
    """Default False: full-frame OCR. Opt-in via OCR_CROP_BAND=1."""
    if override is not None:
        return bool(override)
    raw = os.environ.get(OCR_CROP_BAND_ENV, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    return False


def resolve_ocr_probe_early_exit(override: bool | None = None) -> bool:
    """Default False so mid/end-card text is not skipped after empty probes."""
    if override is not None:
        return bool(override)
    raw = os.environ.get(OCR_PROBE_EARLY_EXIT_ENV, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    return False


def _time_ms_for_index(index: int, frame_time_ms: list[int] | None) -> int:
    if frame_time_ms is not None and index < len(frame_time_ms):
        return int(frame_time_ms[index])
    return index * 1000


def _unwrap_rest_provider(provider: OcrProvider) -> RestOcrEndpointProvider | None:
    if isinstance(provider, RestOcrEndpointProvider):
        return provider
    if isinstance(provider, RetryingOcrProvider):
        primary = getattr(provider, "_primary", None)
        if isinstance(primary, RestOcrEndpointProvider):
            return primary
    return None


def _detect_frame(
    provider: OcrProvider,
    path: Path,
    *,
    band_ratio: float,
    crop_band: bool,
    crop_dir: Path | None,
) -> FrameOcrDetection:
    """OCR one frame; optionally crop overlay region then remap boxes to full frame."""
    del band_ratio
    if crop_band and crop_dir is not None:
        crop_path = crop_dir / f"{path.stem}__band.jpg"
        try:
            full_w, full_h, _crop_h = crop_vertical_band_jpeg(
                path,
                crop_path,
                y0_norm=OVERLAY_CROP_TOP,
                y1_norm=1.0,
            )
            detection = provider.detect_image(crop_path)
            remapped = [
                remap_box_from_vertical_crop(box, y0_norm=OVERLAY_CROP_TOP, y1_norm=1.0)
                for box in detection.boxes
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
    """Keep every OCR box (full-screen UI / titles / hard-sub)."""
    del band_ratio
    kept = list(detection.boxes)
    result = FrameOcrFilterResult(
        frame_id=frame_id_from_path(path),
        path=str(path),
        time_ms=time_ms,
        frame_width=detection.frame_width,
        frame_height=detection.frame_height,
        boxes=kept,
        raw_box_count=len(detection.boxes),
        filtered_out_count=0,
    )
    return result, []


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


def _run_async_rest_batch(
    frame_paths: list[Path],
    *,
    rest: RestOcrEndpointProvider,
    frame_time_ms: list[int] | None,
    concurrency: int,
) -> dict[int, tuple[FrameOcrFilterResult, list[str]]]:
    """Warm endpoint once, then aiohttp.gather all frames."""
    # Trigger sync warmup (requests /health) before the concurrent storm.
    if not rest._skip_warmup and not rest._warmed:
        with rest._warmup_lock:
            if not rest._warmed:
                from src.media_pipeline.ocr_filtering.providers import wait_for_ocr_endpoint_ready

                wait_for_ocr_endpoint_ready(rest._endpoint)
                rest._warmed = True

    paths = [Path(p) for p in frame_paths]
    detections = process_all_frames_sync(
        paths,
        endpoint_url=rest._endpoint,
        timeout_seconds=rest._timeout,
        concurrency=concurrency,
    )
    out: dict[int, tuple[FrameOcrFilterResult, list[str]]] = {}
    for index, detection in enumerate(detections):
        path = paths[index]
        time_ms = _time_ms_for_index(index, frame_time_ms)
        filtered, warns = _filter_detection(path, time_ms, detection, band_ratio=BOTTOM_BAND_RATIO)
        logger.info(
            "ocr_frame_filtered",
            extra={
                "frame_id": path.stem,
                "time_ms": time_ms,
                "raw": filtered.raw_box_count,
                "kept": len(filtered.boxes),
                "mode": "async_batch",
            },
        )
        out[index] = (filtered, warns)
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
    """Run OCR on sampled frames and keep **all** detected text boxes (full-frame).

    Parameters
    ----------
    frame_paths:
        Output of Phase 1 `extract_video_frames` (JPEG paths), may include ``thumbnail.jpg``.
    frame_time_ms:
        Optional aligned timecodes from Phase 1. If omitted, index * 1000 is used.
    band_ratio:
        Retained for API compatibility; full-screen keep no longer filters by band.
    crop_band:
        When True, OCR a vertical crop (legacy). Default False = full frame.
    concurrency:
        Async / thread pool workers (default OCR_HTTP_CONCURRENCY or 3).
    probe_stride:
        First OCR every Nth frame; if all empty and early_exit, skip the rest.
    early_exit_empty_probe:
        Skip unprobed frames when the probe pass finds no boxes (default off).
    """
    if not frame_paths:
        raise OcrFilteringError(
            OcrFilteringErrorCode.EMPTY_INPUT,
            "frame_paths is empty — run Phase 1 extract_video_frames first",
        )

    started = time.perf_counter()
    provider = ocr_provider or build_default_ocr_provider()
    use_crop = resolve_ocr_crop_band(crop_band)
    workers = resolve_ocr_http_concurrency(concurrency)
    stride = resolve_ocr_probe_stride(probe_stride)
    early_exit = resolve_ocr_probe_early_exit(early_exit_empty_probe)
    rest = _unwrap_rest_provider(provider)

    warnings: list[str] = []
    n = len(frame_paths)
    all_indices = list(range(n))
    by_index: dict[int, FrameOcrFilterResult] = {}

    try:
        # Fast path: full-frame REST OCR via aiohttp.gather (no band crop).
        if rest is not None and not use_crop and stride <= 1:
            batch = _run_async_rest_batch(
                list(frame_paths),
                rest=rest,
                frame_time_ms=frame_time_ms,
                concurrency=workers,
            )
            for idx, (frame, warns) in batch.items():
                by_index[idx] = frame
                warnings.extend(warns)
        else:
            probe_indices = list(range(0, n, stride))
            remaining_indices = [i for i in all_indices if i not in set(probe_indices)]
            with tempfile.TemporaryDirectory(prefix="ocr_band_crop_") as crop_tmp:
                crop_dir = Path(crop_tmp) if use_crop else None
                # Prefer async for the probe/rest sets when possible.
                if rest is not None and not use_crop:
                    probe_paths = [Path(frame_paths[i]) for i in probe_indices]
                    probe_times = (
                        [_time_ms_for_index(i, frame_time_ms) for i in probe_indices]
                        if frame_time_ms is not None
                        else None
                    )
                    # Map local batch indices back to global.
                    local = _run_async_rest_batch(
                        probe_paths,
                        rest=rest,
                        frame_time_ms=probe_times,
                        concurrency=workers,
                    )
                    probed = {
                        probe_indices[local_i]: item for local_i, item in local.items()
                    }
                else:
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
                by_index.update({idx: item[0] for idx, item in probed.items()})
                for _idx, (_frame, warns) in probed.items():
                    warnings.extend(warns)

                if remaining_indices and (probe_has_boxes or not early_exit or stride <= 1):
                    if rest is not None and not use_crop:
                        rest_paths = [Path(frame_paths[i]) for i in remaining_indices]
                        rest_times = (
                            [_time_ms_for_index(i, frame_time_ms) for i in remaining_indices]
                            if frame_time_ms is not None
                            else None
                        )
                        local = _run_async_rest_batch(
                            rest_paths,
                            rest=rest,
                            frame_time_ms=rest_times,
                            concurrency=workers,
                        )
                        rest_map = {
                            remaining_indices[local_i]: item
                            for local_i, item in local.items()
                        }
                    else:
                        rest_map = _run_indices_parallel(
                            remaining_indices,
                            frame_paths,
                            provider=provider,
                            frame_time_ms=frame_time_ms,
                            band_ratio=band_ratio,
                            crop_band=use_crop,
                            crop_dir=crop_dir,
                            concurrency=workers,
                        )
                    for idx, (frame, warns) in rest_map.items():
                        by_index[idx] = frame
                        warnings.extend(warns)
                elif remaining_indices and early_exit and not probe_has_boxes:
                    warnings.append("ocr_probe_empty_early_exit")
                    sample_w = next(
                        (f.frame_width for f in by_index.values() if f.frame_width), 0
                    )
                    sample_h = next(
                        (f.frame_height for f in by_index.values() if f.frame_height), 0
                    )
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
    finally:
        elapsed = time.perf_counter() - started
        msg = f"Phase 2 OCR execution time: {elapsed:.2f}s"
        print(msg, flush=True)
        logger.info(
            "phase2_ocr_execution_time",
            extra={"seconds": round(elapsed, 3), "frames": n, "concurrency": workers},
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
            "full_frame_keep": True,
        },
    )
    return result
