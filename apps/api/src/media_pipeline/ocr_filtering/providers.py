"""OCR providers for Phase 2: REST Cloud Run /predict, mock, retry wrapper."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Protocol

import requests

from src.media_pipeline.ocr_filtering.errors import OcrFilteringError, OcrFilteringErrorCode
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrDetection, Vertex

try:
    from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed
except ImportError:  # pragma: no cover — tenacity is a declared api dependency
    retry = None  # type: ignore[assignment]
    retry_if_exception = None  # type: ignore[assignment]
    stop_after_attempt = None  # type: ignore[assignment]
    wait_fixed = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

OCR_ENDPOINT_ENV = "OCR_ENDPOINT_URL"
OCR_HTTP_TIMEOUT_ENV = "OCR_HTTP_TIMEOUT_SECONDS"
# Cloud Run scale-to-zero + Paddle cold start often exceeds 120s.
DEFAULT_TIMEOUT_SECONDS = 300.0


def resolve_ocr_http_timeout_seconds() -> float:
    """HTTP timeout for Cloud Run /predict; override via OCR_HTTP_TIMEOUT_SECONDS."""
    raw = os.environ.get(OCR_HTTP_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("invalid_%s", OCR_HTTP_TIMEOUT_ENV, extra={"raw": raw[:40]})
        return DEFAULT_TIMEOUT_SECONDS
    return max(30.0, value)


def is_transient_ocr_http_error(message: str) -> bool:
    """True for Cloud Run cold-start / overload style failures worth long backoff."""
    text = (message or "").lower()
    needles = (
        "503",
        "502",
        "504",
        "429",
        "service unavailable",
        "timed out",
        "timeout",
        "connection reset",
        "connection aborted",
        "connection refused",
        "temporarily unavailable",
    )
    return any(needle in text for needle in needles)


def ocr_health_url(predict_or_base_url: str) -> str:
    """Derive ``…/health`` from ``OCR_ENDPOINT_URL`` (…/predict or service base)."""
    base = predict_or_base_url.strip().rstrip("/")
    if base.endswith("/predict"):
        base = base[: -len("/predict")].rstrip("/")
    return f"{base}/health"


def resolve_ocr_warmup_deadline_seconds() -> float:
    raw = os.environ.get("OCR_WARMUP_DEADLINE_SECONDS", "").strip()
    if not raw:
        return 180.0
    try:
        return max(30.0, float(raw))
    except ValueError:
        return 180.0


def wait_for_ocr_endpoint_ready(
    predict_or_base_url: str,
    *,
    deadline_seconds: float | None = None,
    poll_timeout_seconds: float = 20.0,
    warm_predict: bool = True,
) -> None:
    """
    Poll Cloud Run ``/health`` until 200, then optionally warm ``/predict``.

    Scale-to-zero often returns timeout/503 for 30–90s before the instance accepts traffic.
    Health-only ready is not enough: first ``/predict`` can still 503 while the model loads.
    """
    deadline = float(deadline_seconds) if deadline_seconds is not None else resolve_ocr_warmup_deadline_seconds()
    health = ocr_health_url(predict_or_base_url)
    predict = normalize_predict_endpoint(predict_or_base_url)
    started = time.monotonic()
    attempt = 0
    last_status = "none"
    logger.info("ocr_endpoint_warmup_start", extra={"health": health, "deadline_s": deadline})
    while True:
        elapsed = time.monotonic() - started
        if elapsed >= deadline:
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR endpoint not ready after {deadline:.0f}s cold-start wait "
                f"(last={last_status}). Check Cloud Run {health}, or set OCR_FILTERING_USE_MOCK=1.",
            )
        attempt += 1
        remaining = max(1.0, deadline - elapsed)
        try:
            response = requests.get(
                health,
                timeout=min(poll_timeout_seconds, remaining),
            )
            last_status = f"health:{response.status_code}"
            if response.status_code == 200:
                logger.info(
                    "ocr_endpoint_health_ok",
                    extra={"attempts": attempt, "elapsed_s": round(elapsed, 1)},
                )
                break
        except requests.RequestException as exc:
            last_status = f"health:{str(exc)[:140]}"
        time.sleep(min(8.0, 2.0 + float(attempt)))

    if not warm_predict:
        logger.info("ocr_endpoint_ready", extra={"warm_predict": False})
        return

    # Tiny JPEG — forces Paddle load so the first real frame does not race a 503.
    tiny = _warmup_jpeg_bytes()
    predict_attempt = 0
    while True:
        elapsed = time.monotonic() - started
        if elapsed >= deadline:
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR /predict warm-up failed after {deadline:.0f}s "
                f"(last={last_status}). Check Cloud Run {predict}.",
            )
        predict_attempt += 1
        remaining = max(5.0, deadline - elapsed)
        try:
            response = requests.post(
                predict,
                files={"file": ("warmup.jpg", tiny, "image/jpeg")},
                timeout=min(resolve_ocr_http_timeout_seconds(), remaining),
            )
            last_status = f"predict:{response.status_code}"
            if response.status_code == 200:
                logger.info(
                    "ocr_endpoint_ready",
                    extra={
                        "health_attempts": attempt,
                        "predict_attempts": predict_attempt,
                        "elapsed_s": round(elapsed, 1),
                    },
                )
                return
            if response.status_code not in {429, 502, 503, 504}:
                raise OcrFilteringError(
                    OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                    f"OCR /predict warm-up failed: HTTP {response.status_code} {response.text[:200]}",
                )
        except OcrFilteringError:
            raise
        except requests.RequestException as exc:
            last_status = f"predict:{str(exc)[:140]}"
            if not is_transient_ocr_http_error(str(exc)):
                raise OcrFilteringError(
                    OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                    f"OCR /predict warm-up failed: {exc}",
                ) from exc
        time.sleep(min(10.0, 3.0 + float(predict_attempt)))


def _warmup_jpeg_bytes() -> bytes:
    """Minimal valid JPEG for Cloud Run /predict warm-up (no Pillow dependency)."""
    # 1x1 pixel JPEG
    return bytes(
        [
            0xFF,
            0xD8,
            0xFF,
            0xE0,
            0x00,
            0x10,
            0x4A,
            0x46,
            0x49,
            0x46,
            0x00,
            0x01,
            0x01,
            0x00,
            0x00,
            0x01,
            0x00,
            0x01,
            0x00,
            0x00,
            0xFF,
            0xDB,
            0x00,
            0x43,
            0x00,
            0x08,
            0x06,
            0x06,
            0x07,
            0x06,
            0x05,
            0x08,
            0x07,
            0x07,
            0x07,
            0x09,
            0x09,
            0x08,
            0x0A,
            0x0C,
            0x14,
            0x0D,
            0x0C,
            0x0B,
            0x0B,
            0x0C,
            0x19,
            0x12,
            0x13,
            0x0F,
            0x14,
            0x1D,
            0x1A,
            0x1F,
            0x1E,
            0x1D,
            0x1A,
            0x1C,
            0x1C,
            0x20,
            0x24,
            0x2E,
            0x27,
            0x20,
            0x22,
            0x2C,
            0x23,
            0x1C,
            0x1C,
            0x28,
            0x37,
            0x29,
            0x2C,
            0x30,
            0x31,
            0x34,
            0x34,
            0x34,
            0x1F,
            0x27,
            0x39,
            0x3D,
            0x38,
            0x32,
            0x3C,
            0x2E,
            0x33,
            0x34,
            0x32,
            0xFF,
            0xC0,
            0x00,
            0x0B,
            0x08,
            0x00,
            0x01,
            0x00,
            0x01,
            0x01,
            0x01,
            0x11,
            0x00,
            0xFF,
            0xC4,
            0x00,
            0x14,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x08,
            0xFF,
            0xC4,
            0x00,
            0x14,
            0x10,
            0x01,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0xFF,
            0xDA,
            0x00,
            0x08,
            0x01,
            0x01,
            0x00,
            0x00,
            0x3F,
            0x00,
            0x7F,
            0xDF,
            0xFF,
            0xD9,
        ]
    )


class OcrProvider(Protocol):
    provider_name: str

    def detect_image(self, image_path: Path) -> FrameOcrDetection: ...


def normalize_predict_endpoint(url: str) -> str:
    """Ensure endpoint ends with /predict (auto_deploy writes with suffix; tolerate base URL)."""
    cleaned = url.strip().rstrip("/")
    if not cleaned:
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_UNAVAILABLE,
            f"{OCR_ENDPOINT_ENV} is empty",
        )
    if cleaned.endswith("/predict"):
        return cleaned
    return f"{cleaned}/predict"


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


def resolve_ocr_endpoint_url() -> str:
    """Read OCR_ENDPOINT_URL from process env, then repo-root / apps/api .env."""
    value = os.environ.get(OCR_ENDPOINT_ENV, "").strip()
    if value:
        return normalize_predict_endpoint(value)

    here = Path(__file__).resolve()
    # providers.py → ocr_filtering → media_pipeline → src → api → apps → repo
    repo_root = here.parents[5]
    api_root = here.parents[3]
    _load_env_file(repo_root / ".env")
    _load_env_file(api_root / ".env")

    value = os.environ.get(OCR_ENDPOINT_ENV, "").strip()
    if not value:
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_UNAVAILABLE,
            f"{OCR_ENDPOINT_ENV} is not set. "
            "Run deploy/hf-paddle-ocr/auto_deploy.py after gcloud auth, "
            "or set OCR_ENDPOINT_URL=<service-url>/predict in the repo root .env.",
        )
    return normalize_predict_endpoint(value)


def parse_predict_response(
    payload: Any,
    *,
    width: int,
    height: int,
) -> list[DetectedTextBox]:
    """Map Cloud Run /predict JSON to normalized DetectedTextBox list."""
    if not isinstance(payload, list):
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
            "OCR /predict response must be a JSON array",
        )
    safe_w = max(1, int(width))
    safe_h = max(1, int(height))

    boxes: list[DetectedTextBox] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        raw_bbox = item.get("bbox")
        if not isinstance(raw_bbox, list) or len(raw_bbox) < 2:
            continue
        xs: list[float] = []
        ys: list[float] = []
        vertices: list[Vertex] = []
        for point in raw_bbox:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            px = float(point[0])
            py = float(point[1])
            xs.append(px)
            ys.append(py)
            vertices.append(Vertex(x=px / safe_w, y=py / safe_h))
        if len(xs) < 2 or len(ys) < 2:
            continue
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        try:
            confidence = float(item.get("score", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        boxes.append(
            DetectedTextBox(
                x=left / safe_w,
                y=top / safe_h,
                width=max(0.01, (right - left) / safe_w),
                height=max(0.01, (bottom - top) / safe_h),
                text=text,
                confidence=max(0.0, min(1.0, confidence)),
                vertices=tuple(vertices[:4]),
            )
        )
    return boxes


def _image_size(image_path: Path) -> tuple[int, int]:
    try:
        from PIL import Image  # type: ignore

        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return 1080, 1920


class RestOcrEndpointProvider:
    """POST multipart JPEG to Cloud Run PaddleOCR /predict (OCR_ENDPOINT_URL)."""

    provider_name = "rest_ocr"

    def __init__(
        self,
        endpoint_url: str | None = None,
        *,
        timeout_seconds: float | None = None,
        skip_warmup: bool = False,
    ) -> None:
        resolved = endpoint_url if endpoint_url is not None else resolve_ocr_endpoint_url()
        self._endpoint = normalize_predict_endpoint(resolved)
        self._timeout = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else resolve_ocr_http_timeout_seconds()
        )
        self._skip_warmup = bool(skip_warmup)
        self._warmed = False
        self._warmup_lock = threading.Lock()

    def detect_image(self, image_path: Path) -> FrameOcrDetection:
        if not image_path.is_file():
            raise OcrFilteringError(
                OcrFilteringErrorCode.FRAME_MISSING,
                f"Frame image missing: {image_path}",
            )
        if not self._skip_warmup and not self._warmed:
            with self._warmup_lock:
                if not self._warmed:
                    wait_for_ocr_endpoint_ready(self._endpoint)
                    self._warmed = True
        width, height = _image_size(image_path)
        content = image_path.read_bytes()
        try:
            payload = self._post_predict_json_with_gateway_retry(image_path.name, content)
        except OcrFilteringError:
            raise
        except requests.RequestException as exc:
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR HTTP request failed: {exc}",
            ) from exc
        except ValueError as exc:
            raise OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                f"OCR response is not valid JSON: {exc}",
            ) from exc

        boxes = parse_predict_response(payload, width=width, height=height)
        logger.info(
            "rest_ocr_detect_ok",
            extra={
                "path": image_path.name,
                "boxes": len(boxes),
                "endpoint": self._endpoint,
            },
        )
        return FrameOcrDetection(frame_width=width, frame_height=height, boxes=boxes)

    def _post_predict_json(self, filename: str, content: bytes) -> Any:
        response = requests.post(
            self._endpoint,
            files={"file": (filename, content, "image/jpeg")},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    def _post_predict_json_with_gateway_retry(self, filename: str, content: bytes) -> Any:
        """Retry HTTP 502/503/504 up to 3 times with 15s wait (Cloud Run cold start)."""
        if retry is None:
            return self._post_predict_json(filename, content)

        def _before_sleep(_retry_state: Any) -> None:
            logger.warning("Container OCR đang khởi động lạnh, tiến hành đợi và thử lại...")

        wrapped = retry(
            retry=retry_if_exception(_is_http_gateway_unavailable),
            stop=stop_after_attempt(3),
            wait=wait_fixed(15),
            before_sleep=_before_sleep,
            reraise=True,
        )(self._post_predict_json)
        return wrapped(filename, content)


def _is_http_gateway_unavailable(exc: BaseException) -> bool:
    """True only for gateway-style HTTP statuses (502/503/504)."""
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        if response is not None and int(getattr(response, "status_code", 0) or 0) in {
            502,
            503,
            504,
        }:
            return True
    return False


class MockOcrProvider:
    """Deterministic detections for unit tests / offline Cloud Run dry-runs."""

    provider_name = "mock_ocr"

    def __init__(
        self,
        *,
        boxes_by_stem: dict[str, list[DetectedTextBox]] | None = None,
        frame_size: tuple[int, int] = (1080, 1920),
        default_boxes: list[DetectedTextBox] | None = None,
    ):
        self._boxes_by_stem = boxes_by_stem or {}
        self._frame_size = frame_size
        self._default_boxes = default_boxes or [
            DetectedTextBox(x=0.08, y=0.78, width=0.84, height=0.12, text="硬字幕测试", confidence=0.95),
        ]

    def detect_image(self, image_path: Path) -> FrameOcrDetection:
        width, height = self._frame_size
        boxes = list(self._boxes_by_stem.get(image_path.stem, self._default_boxes))
        return FrameOcrDetection(frame_width=width, frame_height=height, boxes=boxes)


class RetryingOcrProvider:
    """Retry transient OCR provider failures (network / 429 / 5xx / cold start)."""

    def __init__(
        self,
        primary: OcrProvider,
        *,
        max_attempts: int = 6,
        base_delay_seconds: float = 5.0,
        max_delay_seconds: float = 45.0,
    ):
        self._primary = primary
        self._max_attempts = max(1, int(max_attempts))
        self._base_delay_seconds = max(0.0, float(base_delay_seconds))
        self._max_delay_seconds = max(self._base_delay_seconds, float(max_delay_seconds))

    @property
    def provider_name(self) -> str:
        return f"retry({getattr(self._primary, 'provider_name', 'ocr')})"

    def _delay_for_attempt(self, attempt: int) -> float:
        delay = self._base_delay_seconds * (2 ** (attempt - 1))
        return min(delay, self._max_delay_seconds)

    def detect_image(self, image_path: Path) -> FrameOcrDetection:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._primary.detect_image(image_path)
            except OcrFilteringError as exc:
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                if is_transient_ocr_http_error(exc.message):
                    delay = self._delay_for_attempt(attempt)
                else:
                    # Non-cold-start failures: short backoff (tests / permanent errors).
                    delay = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    delay = min(delay, self._max_delay_seconds)
                logger.warning(
                    "ocr_provider_retry",
                    extra={
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "delay_seconds": delay,
                        "path": image_path.name,
                        "error": exc.message[:200],
                    },
                )
                if delay > 0:
                    time.sleep(delay)
            except Exception as exc:  # noqa: BLE001 — wrap unknown provider crashes
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                delay = (
                    self._delay_for_attempt(attempt)
                    if is_transient_ocr_http_error(str(exc))
                    else min(0.5 * (2 ** (attempt - 1)), 2.0)
                )
                logger.warning(
                    "ocr_provider_retry_unexpected",
                    extra={"attempt": attempt, "path": image_path.name, "error": str(exc)[:200]},
                )
                if delay > 0:
                    time.sleep(delay)
        if isinstance(last_error, OcrFilteringError):
            raise last_error
        raise OcrFilteringError(
            OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
            f"OCR failed after {self._max_attempts} attempts: {last_error}",
        )


def build_default_ocr_provider(*, prefer_mock: bool = False) -> OcrProvider:
    """Prefer REST OCR_ENDPOINT_URL when set; otherwise mock for local/dev."""
    if prefer_mock or os.environ.get("OCR_FILTERING_USE_MOCK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return RetryingOcrProvider(MockOcrProvider(), max_attempts=2, base_delay_seconds=0.0)
    try:
        # Gateway 502/503/504 retried inside RestOcrEndpointProvider (15s × 3).
        return RetryingOcrProvider(
            RestOcrEndpointProvider(),
            max_attempts=2,
            base_delay_seconds=5.0,
            max_delay_seconds=15.0,
        )
    except OcrFilteringError as exc:
        logger.warning("ocr_filtering_fallback_mock", extra={"reason": exc.message[:240]})
        return RetryingOcrProvider(MockOcrProvider(), max_attempts=2, base_delay_seconds=0.0)
