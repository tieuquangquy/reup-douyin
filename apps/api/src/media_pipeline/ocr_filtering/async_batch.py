"""Async OCR batch: preprocess (≤1920px + contrast/sharpen JPEG) + Semaphore + 300s.

Full-frame uploads previously hung Cloud Run; local resize/compress cuts payload and
model work before aiohttp POST. Client concurrency defaults to 2 to match Cloud Run
``--concurrency 2`` (override via OCR_ASYNC_CONCURRENCY). Raise only when scale-out
is healthy; otherwise Cloud Run returns 429 Rate exceeded.
Timeout 300s matches Cloud Run --timeout 300.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import time
from collections.abc import Callable
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

# completed/total after each frame finishes (async batch heartbeat).
OcrFrameDoneCallback = Callable[[int, int], None]

from src.media_pipeline.ocr_filtering.errors import OcrFilteringError, OcrFilteringErrorCode
from src.media_pipeline.ocr_filtering.providers import (
    normalize_predict_endpoint,
    parse_predict_response,
)
from src.media_pipeline.ocr_filtering.types import FrameOcrDetection

logger = logging.getLogger(__name__)

# Client parallel POSTs — default matches Cloud Run --concurrency 2 / instance.
# Higher values need healthy scale-out; otherwise Cloud Run returns 429 Rate exceeded.
OCR_ASYNC_CONCURRENCY_ENV = "OCR_ASYNC_CONCURRENCY"
ASYNC_OCR_CONCURRENCY = 2
_ASYNC_OCR_CONCURRENCY_MAX = 20
ASYNC_OCR_TIMEOUT_SECONDS = 300
ASYNC_OCR_MAX_EDGE_PX = 1920
ASYNC_OCR_JPEG_QUALITY = 85
OCR_PREPROCESS_MAX_EDGE_ENV = "OCR_PREPROCESS_MAX_EDGE"
DEFAULT_ASYNC_CONCURRENCY = ASYNC_OCR_CONCURRENCY
_RETRYABLE_OCR_HTTP = frozenset({429, 502, 503, 504})


def _load_env_file(path: Path) -> None:
    """Best-effort KEY=VALUE load without requiring python-dotenv."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _ocr_dotenv_candidates() -> list[Path]:
    """Worker + API + repo-root .env (pydantic Settings does not export OCR_* to os.environ)."""
    here = Path(__file__).resolve()
    # async_batch.py → ocr_filtering → media_pipeline → src → api → apps → repo
    api_root = here.parents[3]
    apps_root = api_root.parent
    repo_root = apps_root.parent
    return [
        apps_root / "worker" / ".env",
        api_root / ".env",
        repo_root / ".env",
    ]


def _ensure_ocr_async_env_loaded() -> None:
    if (os.environ.get(OCR_ASYNC_CONCURRENCY_ENV) or "").strip():
        return
    for path in _ocr_dotenv_candidates():
        _load_env_file(path)


def resolve_async_ocr_concurrency(override: int | None = None) -> int:
    """Return client OCR concurrency (1–20). Env ``OCR_ASYNC_CONCURRENCY`` or default 2."""
    if override is not None:
        try:
            return max(1, min(_ASYNC_OCR_CONCURRENCY_MAX, int(override)))
        except (TypeError, ValueError):
            return ASYNC_OCR_CONCURRENCY
    _ensure_ocr_async_env_loaded()
    raw = (os.environ.get(OCR_ASYNC_CONCURRENCY_ENV) or "").strip()
    if not raw:
        return ASYNC_OCR_CONCURRENCY
    try:
        return max(1, min(_ASYNC_OCR_CONCURRENCY_MAX, int(raw)))
    except ValueError:
        logger.warning(
            "invalid_ocr_async_concurrency",
            extra={"raw": raw[:40]},
        )
        return ASYNC_OCR_CONCURRENCY

_OCR_SHARPEN_KERNEL = np.array(
    [[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]],
    dtype=np.float32,
)


def resolve_ocr_preprocess_max_edge() -> int:
    """Default 1920; override via OCR_PREPROCESS_MAX_EDGE; profile=best forces 1920."""
    from src.media_pipeline.ocr_filtering.ocr_quality_profile import (
        effective_ocr_preprocess_max_edge,
    )

    raw = os.environ.get(OCR_PREPROCESS_MAX_EDGE_ENV, "").strip()
    env_override: int | None = None
    if raw:
        try:
            env_override = max(64, int(raw))
        except ValueError:
            logger.warning(
                "invalid_%s",
                OCR_PREPROCESS_MAX_EDGE_ENV,
                extra={"raw": raw[:40]},
            )
    return effective_ocr_preprocess_max_edge(ASYNC_OCR_MAX_EDGE_PX, override=env_override)


def resolve_ocr_jpeg_quality() -> int:
    from src.media_pipeline.ocr_filtering.ocr_quality_profile import (
        effective_ocr_jpeg_quality,
    )

    return effective_ocr_jpeg_quality(ASYNC_OCR_JPEG_QUALITY)


def ocr_frame_progress_percent(completed: int, total: int) -> int:
    """
    Map finished OCR frames into job step percents 26–54.

    Leaves headroom under ``phase25_translate`` (55) so the UI moves during
    long Cloud Run batches instead of sitting frozen at ``phase2_ocr`` 25.
    """
    if total <= 0:
        return 26
    done = max(0, min(int(completed), int(total)))
    return 26 + int(round((done / int(total)) * 28))


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
            jpeg_q = resolve_ocr_jpeg_quality()
            out_img.save(buf, format="JPEG", quality=jpeg_q, optimize=True)
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
    if isinstance(exc, OcrRetryableHttpStatus) and exc.status in _RETRYABLE_OCR_HTTP:
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
    POST one JPEG to /predict with timeout=300s (Cloud Run request budget).

    Retried by tenacity on network errors / timeouts / HTTP 429|502|503|504.
    """
    timeout_s = float(
        os.environ.get("OCR_HTTP_TIMEOUT_SECONDS") or ASYNC_OCR_TIMEOUT_SECONDS
    )
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    form = aiohttp.FormData()
    form.add_field(
        "file",
        content,
        filename=filename,
        content_type="image/jpeg",
    )
    async with session.post(endpoint, data=form, timeout=timeout) as response:
        body = await response.read()
        if response.status in _RETRYABLE_OCR_HTTP:
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
            timeout_s = float(
                os.environ.get("OCR_HTTP_TIMEOUT_SECONDS") or ASYNC_OCR_TIMEOUT_SECONDS
            )
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR HTTP request timed out after {timeout_s}s",
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
    concurrency: int | None = None,
    on_frame_done: OcrFrameDoneCallback | None = None,
) -> list[FrameOcrDetection]:
    """
    Fire OCR /predict for all frames concurrently (asyncio.gather + Semaphore).

    Default concurrency 2 (env ``OCR_ASYNC_CONCURRENCY``) to match Cloud Run
    per-instance ``--concurrency``. Timeout 300s + local JPEG preprocess.
    ``on_frame_done(completed, total)`` fires after each successful frame detect
    (order of completion, not path order).
    """
    del timeout_seconds
    limit = resolve_async_ocr_concurrency(concurrency)

    if not frames:
        return []
    endpoint = normalize_predict_endpoint(endpoint_url)
    semaphore = asyncio.Semaphore(limit)
    connector = aiohttp.TCPConnector(limit=limit)
    batch_started = time.perf_counter()
    total = len(frames)
    completed = 0
    done_lock = asyncio.Lock()
    logger.info("ocr_async_batch_start frames=%s concurrency=%s", total, limit)

    results: list[FrameOcrDetection] = []
    try:
        async with aiohttp.ClientSession(connector=connector) as session:

            async def _detect_and_report(path: Path) -> FrameOcrDetection:
                nonlocal completed
                detection = await _detect_one(
                    session,
                    path,
                    endpoint=endpoint,
                    semaphore=semaphore,
                )
                if on_frame_done is not None:
                    async with done_lock:
                        completed += 1
                        current = completed
                    on_frame_done(current, total)
                return detection

            tasks = [_detect_and_report(Path(path)) for path in frames]
            results = list(await asyncio.gather(*tasks))
    except OcrFilteringError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
            f"OCR async batch failed: {exc}",
        ) from exc
    finally:
        # Deterministic connector shutdown before asyncio.run() closes the loop
        # (avoids Proactor transport EINVAL noise on Windows).
        if not connector.closed:
            await connector.close()

    batch_ms = int(round((time.perf_counter() - batch_started) * 1000))
    logger.info(
        "ocr_async_batch_done",
        extra={
            "frames": len(results),
            "concurrency": limit,
            "elapsed_ms": batch_ms,
        },
    )
    return results


def process_all_frames_sync(
    frames: list[Path],
    *,
    endpoint_url: str,
    timeout_seconds: float | None = None,
    concurrency: int | None = None,
    on_frame_done: OcrFrameDoneCallback | None = None,
) -> list[FrameOcrDetection]:
    """Sync entrypoint for Phase 2 (runs the async batch on a dedicated event loop)."""
    # Windows default ProactorEventLoop + aiohttp often raises
    # ``OSError: [Errno 22] Invalid argument`` when asyncio.run() tears down after
    # a long Cloud Run OCR batch — surfacing as STEP_UNHANDLED_ERROR mid-job.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        return asyncio.run(
            process_all_frames(
                frames,
                endpoint_url=endpoint_url,
                timeout_seconds=timeout_seconds,
                concurrency=concurrency,
                on_frame_done=on_frame_done,
            )
        )
    except OcrFilteringError:
        raise
    except OSError as exc:
        # Loop/socket teardown EINVAL (22) or similar WinError after a finished batch.
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
            f"OCR async batch failed: {exc}",
        ) from exc
