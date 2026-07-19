"""Async OCR batch: preprocess (≤1920px + contrast/sharpen JPEG) + Semaphore(3) + 120s.

Full-frame uploads previously hung Cloud Run; local resize/compress cuts payload and
model work before aiohttp POST. Client concurrency 3 matches Cloud Run --concurrency 2
plus light multi-instance headroom. Contrast + sharpen boost thin/low-contrast UI glyphs.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from pathlib import Path
from typing import Any

import aiohttp
import numpy as np
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.media_pipeline.ocr_filtering.errors import OcrFilteringError, OcrFilteringErrorCode
from src.media_pipeline.ocr_filtering.providers import (
    normalize_predict_endpoint,
    parse_predict_response,
)
from src.media_pipeline.ocr_filtering.types import FrameOcrDetection

logger = logging.getLogger(__name__)

# Cloud Run --concurrency 2 → client hardcap 3 (not 5+) to avoid queue/timeout storms.
ASYNC_OCR_CONCURRENCY = 3
ASYNC_OCR_TIMEOUT_SECONDS = 120
ASYNC_OCR_MAX_EDGE_PX = 1920
ASYNC_OCR_JPEG_QUALITY = 85
OCR_PREPROCESS_MAX_EDGE_ENV = "OCR_PREPROCESS_MAX_EDGE"
DEFAULT_ASYNC_CONCURRENCY = ASYNC_OCR_CONCURRENCY

_OCR_SHARPEN_KERNEL = np.array(
    [[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]],
    dtype=np.float32,
)


def resolve_ocr_preprocess_max_edge() -> int:
    """Default 1920; override via OCR_PREPROCESS_MAX_EDGE (e.g. 720 fast / 1280 lighter)."""
    raw = os.environ.get(OCR_PREPROCESS_MAX_EDGE_ENV, "").strip()
    if not raw:
        return ASYNC_OCR_MAX_EDGE_PX
    try:
        return max(64, int(raw))
    except ValueError:
        logger.warning(
            "invalid_%s",
            OCR_PREPROCESS_MAX_EDGE_ENV,
            extra={"raw": raw[:40]},
        )
        return ASYNC_OCR_MAX_EDGE_PX


def enhance_ocr_frame_bgr(frame_bgr: np.ndarray) -> np.ndarray:
    """
    Light contrast + sharpen for thin/low-contrast Chinese UI glyphs.

    Fail-soft: returns a safe copy (or the input) if OpenCV / shape is unusable.
    """
    try:
        if frame_bgr is None:
            return frame_bgr
        arr = np.asarray(frame_bgr)
        if arr.ndim != 3 or arr.shape[0] < 2 or arr.shape[1] < 2 or arr.shape[2] != 3:
            return arr.copy() if hasattr(arr, "copy") else arr
        import cv2

        contrasted = cv2.convertScaleAbs(arr, alpha=1.2, beta=10)
        sharpened = cv2.filter2D(contrasted, -1, _OCR_SHARPEN_KERNEL)
        return sharpened
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ocr_enhance_failed",
            extra={"error": str(exc)[:200]},
        )
        try:
            return np.asarray(frame_bgr).copy()
        except Exception:  # noqa: BLE001
            return frame_bgr


class OcrRetryableHttpStatus(Exception):
    """Raised for gateway overload statuses that tenacity should retry."""

    def __init__(self, status: int, detail: str):
        self.status = int(status)
        super().__init__(detail)


def prepare_ocr_jpeg_bytes(path: Path) -> tuple[bytes, int, int, int, int]:
    """
    Optional resize (max edge 1920) + contrast/sharpen + JPEG into memory.

    Returns ``(jpeg_bytes, upload_w, upload_h, original_w, original_h)``.
    Uniform scale keeps normalized OCR boxes valid for the original frame.
    """
    path = Path(path)
    if not path.is_file():
        raise OcrFilteringError(
            OcrFilteringErrorCode.FRAME_MISSING,
            f"Frame image missing: {path}",
        )
    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
            "Pillow is required for OCR frame preprocess (pip install Pillow)",
        ) from exc

    max_edge = resolve_ocr_preprocess_max_edge()
    try:
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            orig_w, orig_h = rgb.size
            if orig_w < 1 or orig_h < 1:
                raise ValueError(f"invalid image size {orig_w}x{orig_h}")
            long_edge = max(orig_w, orig_h)
            if long_edge > max_edge:
                scale = max_edge / float(long_edge)
                upload_w = max(1, int(round(orig_w * scale)))
                upload_h = max(1, int(round(orig_h * scale)))
                rgb = rgb.resize((upload_w, upload_h), Image.Resampling.BILINEAR)
            else:
                upload_w, upload_h = orig_w, orig_h

            # PIL RGB → OpenCV BGR enhance → back to RGB JPEG.
            rgb_np = np.asarray(rgb, dtype=np.uint8)
            bgr = rgb_np[:, :, ::-1].copy()
            enhanced_bgr = enhance_ocr_frame_bgr(bgr)
            enhanced_rgb = np.asarray(enhanced_bgr)[:, :, ::-1]
            out_img = Image.fromarray(enhanced_rgb, mode="RGB")

            buf = io.BytesIO()
            out_img.save(buf, format="JPEG", quality=ASYNC_OCR_JPEG_QUALITY, optimize=True)
            return buf.getvalue(), upload_w, upload_h, orig_w, orig_h
    except OcrFilteringError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OcrFilteringError(
            OcrFilteringErrorCode.FRAME_MISSING,
            f"Cannot read/preprocess frame {path.name}: {exc}",
        ) from exc


def _is_retryable_ocr_exception(exc: BaseException) -> bool:
    if isinstance(exc, (aiohttp.ClientError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, OcrRetryableHttpStatus) and exc.status in {502, 503, 504}:
        return True
    return False


def _log_ocr_retry(retry_state: Any) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome is not None else None
    attempt = retry_state.attempt_number
    if exc is None:
        detail = "unknown"
    else:
        detail = str(exc).strip() or type(exc).__name__
        detail = detail[:200]
    msg = f"WARNING: OCR request failed (attempt {attempt}/3), retrying — {detail}"
    print(msg, flush=True)
    logger.warning(
        "ocr_async_retry",
        extra={
            "attempt": attempt,
            "max_attempts": 3,
            "error": detail,
        },
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=20),
    retry=retry_if_exception(_is_retryable_ocr_exception),
    before_sleep=_log_ocr_retry,
)
async def post_ocr_predict(
    session: aiohttp.ClientSession,
    *,
    endpoint: str,
    filename: str,
    content: bytes,
) -> Any:
    """
    POST one JPEG to /predict with fail-fast timeout=120s.

    Retried by tenacity on network errors / timeouts / HTTP 502|503|504.
    """
    timeout = aiohttp.ClientTimeout(total=ASYNC_OCR_TIMEOUT_SECONDS)
    form = aiohttp.FormData()
    form.add_field(
        "file",
        content,
        filename=filename,
        content_type="image/jpeg",
    )
    async with session.post(endpoint, data=form, timeout=timeout) as response:
        body = await response.read()
        if response.status in {502, 503, 504}:
            raise OcrRetryableHttpStatus(
                response.status,
                f"OCR HTTP {response.status}: {body[:200]!r}",
            )
        if response.status >= 400:
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR HTTP {response.status}: {body[:200]!r}",
            )
        try:
            return await response.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR response is not valid JSON: {exc}",
            ) from exc


async def _detect_one(
    session: aiohttp.ClientSession,
    path: Path,
    *,
    endpoint: str,
    semaphore: asyncio.Semaphore,
) -> FrameOcrDetection:
    async with semaphore:
        started = time.perf_counter()
        content, upload_w, upload_h, orig_w, orig_h = prepare_ocr_jpeg_bytes(path)
        try:
            payload = await post_ocr_predict(
                session,
                endpoint=endpoint,
                filename=path.name,
                content=content,
            )
        except OcrRetryableHttpStatus as exc:
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                str(exc),
            ) from exc
        except asyncio.TimeoutError as exc:
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR HTTP request timed out after {ASYNC_OCR_TIMEOUT_SECONDS}s",
            ) from exc
        except aiohttp.ClientError as exc:
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR HTTP request failed: {exc}",
            ) from exc
        # Parse against upload pixels; uniform scale → normalized boxes match original.
        boxes = parse_predict_response(payload, width=upload_w, height=upload_h)
        elapsed_ms = int(round((time.perf_counter() - started) * 1000))
        logger.info(
            "rest_ocr_async_detect_ok",
            extra={
                "path": path.name,
                "boxes": len(boxes),
                "upload_px": f"{upload_w}x{upload_h}",
                "original_px": f"{orig_w}x{orig_h}",
                "payload_bytes": len(content),
                "elapsed_ms": elapsed_ms,
            },
        )
        return FrameOcrDetection(frame_width=orig_w, frame_height=orig_h, boxes=boxes)


async def process_all_frames(
    frames: list[Path],
    *,
    endpoint_url: str,
    timeout_seconds: float | None = None,
    concurrency: int = ASYNC_OCR_CONCURRENCY,
) -> list[FrameOcrDetection]:
    """
    Fire OCR /predict for all frames concurrently (asyncio.gather + Semaphore(3)).

    ``concurrency`` / ``timeout_seconds`` are accepted for API compat but hardcoded
    to the Cloud Run profile (3 / 120s) with local JPEG preprocess.
    """
    del timeout_seconds
    del concurrency

    if not frames:
        return []
    endpoint = normalize_predict_endpoint(endpoint_url)
    semaphore = asyncio.Semaphore(ASYNC_OCR_CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=ASYNC_OCR_CONCURRENCY)
    batch_started = time.perf_counter()
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                _detect_one(
                    session,
                    Path(path),
                    endpoint=endpoint,
                    semaphore=semaphore,
                )
                for path in frames
            ]
            results = list(await asyncio.gather(*tasks))
    except OcrFilteringError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
            f"OCR async batch failed: {exc}",
        ) from exc

    batch_ms = int(round((time.perf_counter() - batch_started) * 1000))
    logger.info(
        "ocr_async_batch_done",
        extra={
            "frames": len(results),
            "concurrency": ASYNC_OCR_CONCURRENCY,
            "elapsed_ms": batch_ms,
        },
    )
    return results


def process_all_frames_sync(
    frames: list[Path],
    *,
    endpoint_url: str,
    timeout_seconds: float | None = None,
    concurrency: int = ASYNC_OCR_CONCURRENCY,
) -> list[FrameOcrDetection]:
    """Sync entrypoint for Phase 2 (runs the async batch on a dedicated event loop)."""
    return asyncio.run(
        process_all_frames(
            frames,
            endpoint_url=endpoint_url,
            timeout_seconds=timeout_seconds,
            concurrency=concurrency,
        )
    )
