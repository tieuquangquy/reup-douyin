"""OCR providers: protocol + mock + optional PaddleOCR with Windows-safe fallback."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

from src.ocr_pipeline.errors import OcrPipelineError, OcrPipelineErrorCode
from src.ocr_pipeline.types import FrameOcrResult, OcrBox

logger = logging.getLogger(__name__)


class OcrProvider(Protocol):
    provider_name: str

    def detect_frame(self, image_path: Path, *, frame_time_ms: int) -> FrameOcrResult: ...


def is_paddle_runtime_failure(exc: BaseException) -> bool:
    text = str(exc).lower()
    needles = (
        "convertpirattribute2runtimeattribute",
        "onednn_instruction",
        "flags_use_mkldnn",
        "not support [pir::arrayattribute",
    )
    return any(needle in text for needle in needles)


def _configure_paddle_cpu_safe_runtime() -> None:
    """Force-disable oneDNN/MKLDNN + PIR paths that crash on Windows Paddle 3.3.x.

    PaddleX defaults CPU run_mode to mkldnn and may set FLAGS_enable_pir_api=1.
    setdefault is not enough — overwrite so prior worker env cannot keep MKLDNN on.
    Must run BEFORE importing paddleocr/paddlex when possible.
    """
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["FLAGS_onednn"] = "0"
    os.environ["FLAGS_enable_pir_api"] = "0"
    os.environ["FLAGS_enable_pir_in_executor"] = "0"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    try:
        import paddle  # type: ignore

        paddle.set_flags({"FLAGS_use_mkldnn": False})
    except Exception:
        pass


class MockOcrProvider:
    """Deterministic bottom-band detections for tests / offline."""

    provider_name = "mock_ocr"

    def __init__(self, *, text: str = "硬字幕测试"):
        self.text = text

    def detect_frame(self, image_path: Path, *, frame_time_ms: int) -> FrameOcrResult:
        width, height = 1080, 1920
        try:
            from PIL import Image  # type: ignore

            with Image.open(image_path) as img:
                width, height = img.size
        except Exception:
            pass
        # Bottom ~22% band; works for landscape and portrait hard-sub pilot.
        return FrameOcrResult(
            frame_time_ms=frame_time_ms,
            frame_width=width,
            frame_height=height,
            boxes=[
                OcrBox(x=0.08, y=0.78, width=0.84, height=0.12, text=self.text, confidence=0.95),
            ],
        )


class FallbackOcrProvider:
    """Use primary OCR; optionally fall back to mock on known Paddle runtime crashes.

    Default is fail-closed: real-video OCR must not silently succeed with fake boxes.
    Tests / offline demos may pass allow_mock_fallback=True.
    """

    def __init__(
        self,
        *,
        primary: OcrProvider,
        fallback: OcrProvider,
        allow_mock_fallback: bool = False,
    ):
        self._primary = primary
        self._fallback = fallback
        self._allow_mock_fallback = allow_mock_fallback
        self._active: OcrProvider = primary
        self.warnings: list[str] = []

    @property
    def provider_name(self) -> str:
        return getattr(self._active, "provider_name", "fallback_ocr")

    def detect_frame(self, image_path: Path, *, frame_time_ms: int) -> FrameOcrResult:
        try:
            return self._active.detect_frame(image_path, frame_time_ms=frame_time_ms)
        except OcrPipelineError as exc:
            if self._active is self._primary and is_paddle_runtime_failure(exc):
                if not self._allow_mock_fallback:
                    raise OcrPipelineError(
                        OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
                        "PaddleOCR runtime failed (fail_closed; refusing mock boxes for real video). "
                        f"Detail: {exc.message}",
                    ) from exc
                logger.warning(
                    "ocr_provider_runtime_fallback",
                    extra={"reason": str(exc)[:240], "fallback": getattr(self._fallback, "provider_name", "mock")},
                )
                if "paddleocr_runtime_fallback_mock" not in self.warnings:
                    self.warnings.append("paddleocr_runtime_fallback_mock")
                self._active = self._fallback
                return self._fallback.detect_frame(image_path, frame_time_ms=frame_time_ms)
            raise


class PaddleOcrProvider:
    """Chinese OCR via PaddleOCR when installed."""

    provider_name = "paddleocr"

    def __init__(self):
        # Env must be set before paddlex forces PIR/MKLDNN on CPU import/init.
        _configure_paddle_cpu_safe_runtime()
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:
            raise OcrPipelineError(
                OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
                "paddleocr is not installed. Run: pip install paddleocr paddlepaddle",
            ) from exc
        _configure_paddle_cpu_safe_runtime()
        # enable_mkldnn=False is required on Windows Paddle 3.3.x (PIR↔oneDNN crash).
        # Douyin hardsub is horizontal → use_angle_cls=False; prefer lightweight PP-OCRv4.
        init_attempts: list[dict] = [
            {
                "lang": "ch",
                "use_angle_cls": False,
                "ocr_version": "PP-OCRv4",
                "use_textline_orientation": False,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "enable_mkldnn": False,
            },
            {
                "lang": "ch",
                "use_angle_cls": False,
                "enable_mkldnn": False,
                "use_gpu": False,
            },
            {"lang": "ch", "use_angle_cls": False, "enable_mkldnn": False},
            {"lang": "ch", "enable_mkldnn": False},
            {"lang": "ch"},
        ]
        last_exc: Exception | None = None
        self._ocr = None
        for kwargs in init_attempts:
            try:
                _configure_paddle_cpu_safe_runtime()
                self._ocr = PaddleOCR(**kwargs)
                break
            except (TypeError, ValueError) as exc:
                last_exc = exc
                continue
            except Exception as exc:
                last_exc = exc
                break
        if self._ocr is None:
            raise OcrPipelineError(
                OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
                f"PaddleOCR init failed: {last_exc}",
            ) from last_exc

    def detect_frame(self, image_path: Path, *, frame_time_ms: int) -> FrameOcrResult:
        try:
            from PIL import Image  # type: ignore
        except ImportError:
            Image = None  # type: ignore

        width, height = 1080, 1920
        if Image is not None:
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
            except Exception:
                pass

        # Re-assert flags in case paddlex mutated env during pipeline setup.
        _configure_paddle_cpu_safe_runtime()
        try:
            raw = self._run_paddle_ocr(image_path)
        except Exception as exc:
            raise OcrPipelineError(
                OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
                f"PaddleOCR failed: {exc}",
            ) from exc

        boxes = _parse_paddle_ocr_result(raw, width=width, height=height)
        return FrameOcrResult(
            frame_time_ms=frame_time_ms,
            frame_width=width,
            frame_height=height,
            boxes=boxes,
        )

    def _run_paddle_ocr(self, image_path: Path) -> object:
        path = str(image_path)
        # PaddleOCR 3.x prefers predict(); older builds use ocr().
        if hasattr(self._ocr, "predict"):
            try:
                return self._ocr.predict(path)
            except TypeError:
                pass
            except Exception as predict_exc:
                if not is_paddle_runtime_failure(predict_exc):
                    raise
                # Fall through to classic ocr() after another env harden.
                _configure_paddle_cpu_safe_runtime()
                logger.warning(
                    "paddleocr_predict_runtime_retry_ocr",
                    extra={"reason": str(predict_exc)[:240]},
                )
        try:
            return self._ocr.ocr(path, cls=True)
        except TypeError:
            return self._ocr.ocr(path)


def _parse_paddle_ocr_result(raw: object, *, width: int, height: int) -> list[OcrBox]:
    boxes: list[OcrBox] = []
    pages: list[object] = []
    if raw is None:
        return boxes
    if isinstance(raw, dict):
        pages = [raw]
    elif isinstance(raw, (list, tuple)):
        pages = list(raw)
    else:
        # predict() may return a generator / Result collection
        try:
            pages = list(raw)  # type: ignore[arg-type]
        except TypeError:
            pages = [raw]

    for page in pages:
        page_obj = page
        if hasattr(page, "json") and callable(page.json):
            try:
                page_obj = page.json
            except Exception:
                page_obj = page
        if hasattr(page_obj, "keys") and not isinstance(page_obj, dict):
            try:
                page_obj = dict(page_obj)
            except Exception:
                pass

        # PaddleOCR 3.x predict page: {dt_polys: [...], rec_texts: [...], rec_scores: [...]}
        if isinstance(page_obj, dict) and (
            "dt_polys" in page_obj or "rec_texts" in page_obj or "rec_polys" in page_obj
        ):
            polys = page_obj.get("dt_polys") or page_obj.get("rec_polys") or []
            texts = page_obj.get("rec_texts") or page_obj.get("texts") or []
            scores = page_obj.get("rec_scores") or page_obj.get("scores") or []
            if isinstance(texts, str):
                texts = [texts]
            for idx, pts in enumerate(polys):
                try:
                    if not pts:
                        continue
                    # Nested list of one polygon
                    if (
                        isinstance(pts, (list, tuple))
                        and pts
                        and isinstance(pts[0], (list, tuple))
                        and len(pts[0]) == 2
                    ):
                        poly = pts
                    elif isinstance(pts, (list, tuple)) and len(pts) == 4:
                        poly = pts
                    else:
                        continue
                    xs = [float(p[0]) for p in poly]
                    ys = [float(p[1]) for p in poly]
                    text = str(texts[idx] if idx < len(texts) else "")
                    conf = float(scores[idx] if idx < len(scores) else 0.0)
                    x0, x1 = min(xs), max(xs)
                    y0, y1 = min(ys), max(ys)
                    boxes.append(
                        OcrBox(
                            x=x0 / max(1, width),
                            y=y0 / max(1, height),
                            width=max(0.01, (x1 - x0) / max(1, width)),
                            height=max(0.01, (y1 - y0) / max(1, height)),
                            text=text,
                            confidence=conf,
                        )
                    )
                except Exception:
                    continue
            continue

        lines = page_obj
        if isinstance(page_obj, dict):
            lines = [page_obj]
        elif isinstance(page_obj, list) and page_obj and not isinstance(page_obj[0], dict):
            # Classic ocr(): raw == [ [ [pts, (text, conf)], ... ] ]
            lines = page_obj

        for line in lines or []:
            try:
                if isinstance(line, dict):
                    text = str(line.get("rec_texts") or line.get("text") or "")
                    if isinstance(text, list):
                        text = str(text[0] if text else "")
                    conf_raw = line.get("rec_scores") or line.get("confidence") or 0.0
                    if isinstance(conf_raw, list):
                        conf = float(conf_raw[0] if conf_raw else 0.0)
                    else:
                        conf = float(conf_raw or 0.0)
                    pts = line.get("dt_polys") or line.get("points") or []
                    if pts and isinstance(pts[0], (list, tuple)) and len(pts[0]) == 2:
                        pass
                    elif pts and isinstance(pts[0], (list, tuple)):
                        pts = pts[0]
                    else:
                        continue
                    xs = [float(p[0]) for p in pts]
                    ys = [float(p[1]) for p in pts]
                else:
                    pts, (text, conf) = line[0], line[1]
                    xs = [float(p[0]) for p in pts]
                    ys = [float(p[1]) for p in pts]
                x0, x1 = min(xs), max(xs)
                y0, y1 = min(ys), max(ys)
                boxes.append(
                    OcrBox(
                        x=x0 / max(1, width),
                        y=y0 / max(1, height),
                        width=max(0.01, (x1 - x0) / max(1, width)),
                        height=max(0.01, (y1 - y0) / max(1, height)),
                        text=str(text or ""),
                        confidence=float(conf or 0.0),
                    )
                )
            except Exception:
                continue
    return boxes


def build_default_ocr_provider(
    *,
    prefer_mock: bool = False,
    allow_mock_fallback: bool = False,
) -> OcrProvider:
    """Build OCR provider for ANALYZE_OCR.

    prefer_mock: force MockOcrProvider (unit tests only).
    allow_mock_fallback: if Paddle missing/crashes, use mock instead of failing closed.
    """
    if prefer_mock:
        return MockOcrProvider()
    try:
        paddle = PaddleOcrProvider()
    except (OcrPipelineError, ValueError, TypeError) as exc:
        if allow_mock_fallback:
            logger.warning("ocr_provider_fallback_mock", extra={"reason": str(exc)})
            return MockOcrProvider()
        raise OcrPipelineError(
            OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
            f"PaddleOCR unavailable (fail_closed; refusing mock boxes for real video): {exc}",
        ) from exc
    if allow_mock_fallback:
        return FallbackOcrProvider(
            primary=paddle,
            fallback=MockOcrProvider(),
            allow_mock_fallback=True,
        )
    return FallbackOcrProvider(primary=paddle, fallback=MockOcrProvider(), allow_mock_fallback=False)
