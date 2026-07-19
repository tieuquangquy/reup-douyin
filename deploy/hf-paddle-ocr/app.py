"""
API OCR nội bộ miễn phí — FastAPI bọc PaddleOCR (tiếng Trung).
Deploy lên Google Cloud Run (cổng 8080).
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Lazy-init: không load model lúc import (health check / cold start nhẹ hơn).
_ocr_engine = None


def configure_paddle_cpu_safe_runtime() -> None:
    """Force-disable oneDNN/MKLDNN + PIR (Paddle 3.3.x crash on Cloud Run CPU).

    Must run BEFORE importing/initializing paddleocr. Mirrors apps/api ocr_pipeline.
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


# Apply as early as possible (module import), before first /predict.
configure_paddle_cpu_safe_runtime()


def get_ocr_engine():
    """Khởi tạo PaddleOCR một lần, ưu tiên nhận diện tiếng Trung (lang='ch')."""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine

    configure_paddle_cpu_safe_runtime()
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "paddleocr chưa được cài. Kiểm tra requirements.txt / Docker build."
        ) from exc

    configure_paddle_cpu_safe_runtime()
    # High-res / small-glyph UI: raise det side + lower DB thresholds.
    # enable_mkldnn=False is required on Paddle 3.3.x (PIR↔oneDNN crash).
    # Prefer operator-requested det_* knobs; fall back if this PaddleOCR build
    # rejects unknown kwargs (3.x vs 2.x).
    init_attempts = [
        {
            "lang": "ch",
            "use_angle_cls": True,
            "det_limit_side_len": 1920,
            "det_db_thresh": 0.3,
            "det_db_box_thresh": 0.5,
            "det_db_unclip_ratio": 1.6,
            "enable_mkldnn": False,
            "use_gpu": False,
            "show_log": False,
        },
        {
            "lang": "ch",
            "use_angle_cls": True,
            "det_limit_side_len": 1920,
            "det_db_thresh": 0.3,
            "det_db_box_thresh": 0.5,
            "det_db_unclip_ratio": 1.6,
            "enable_mkldnn": False,
        },
        {
            "lang": "ch",
            "use_angle_cls": True,
            "det_limit_side_len": 1920,
            "det_db_thresh": 0.3,
            "det_db_box_thresh": 0.5,
            "det_db_unclip_ratio": 1.6,
        },
        {
            "lang": "ch",
            "use_textline_orientation": True,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "enable_mkldnn": False,
        },
        {
            "lang": "ch",
            "use_angle_cls": True,
            "enable_mkldnn": False,
            "use_gpu": False,
            "show_log": False,
        },
        {"lang": "ch", "enable_mkldnn": False},
        {"lang": "ch", "use_angle_cls": True, "show_log": False},
        {"lang": "ch"},
    ]
    last_error: Exception | None = None
    for kwargs in init_attempts:
        try:
            configure_paddle_cpu_safe_runtime()
            _ocr_engine = PaddleOCR(**kwargs)
            logger.info("paddleocr_initialized", extra={"kwargs": list(kwargs.keys())})
            return _ocr_engine
        except (TypeError, ValueError) as exc:
            last_error = exc
            continue
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            break
    raise RuntimeError(f"Không khởi tạo được PaddleOCR: {last_error}")


def _normalize_quad(pts: Any) -> list[list[float]]:
    """Chuẩn hóa 4 góc bbox thành [[x,y], [x,y], [x,y], [x,y]]."""
    points: list[list[float]] = []
    for p in pts:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            points.append([float(p[0]), float(p[1])])
    if len(points) < 4:
        # Pad nếu thiếu góc (hiếm).
        while len(points) < 4 and points:
            points.append(points[-1])
    return points[:4]


def _unwrap_page_payload(page: Any) -> Any:
    """Normalize PaddleOCR 3.x Result / ``{'res': {...}}`` into a plain dict or classic page."""
    page_obj = page

    # Prefer .json — property (dict) or callable method.
    if hasattr(page, "json"):
        json_attr = getattr(page, "json")
        try:
            page_obj = json_attr() if callable(json_attr) else json_attr
        except Exception:
            page_obj = page

    # Mapping-like Result without being a dict.
    if page_obj is not None and hasattr(page_obj, "keys") and not isinstance(page_obj, (dict, list, tuple, str, bytes)):
        try:
            page_obj = dict(page_obj)
        except Exception:
            try:
                page_obj = {k: page_obj[k] for k in page_obj.keys()}  # type: ignore[index]
            except Exception:
                pass

    # PaddleX / PaddleOCR 3.x wraps fields under ``res``.
    if isinstance(page_obj, dict) and "res" in page_obj and isinstance(page_obj.get("res"), dict):
        nested = page_obj["res"]
        if any(key in nested for key in ("dt_polys", "rec_texts", "rec_polys", "rec_scores")):
            page_obj = nested

    return page_obj


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    # numpy arrays
    if hasattr(value, "tolist"):
        try:
            converted = value.tolist()
            if isinstance(converted, list):
                return converted
            return [converted]
        except Exception:
            pass
    try:
        return list(value)
    except TypeError:
        return [value]


def parse_paddle_ocr_result(raw: Any) -> list[dict[str, Any]]:
    """
    Phân tích output PaddleOCR → mảng JSON:
    [{"bbox": [[x,y]x4], "text": "...", "score": 0.99}, ...]

    Hỗ trợ:
    - Classic: [ [ [pts], (text, conf) ], ... ]
    - Dict / PaddleOCR 3.x: rec_texts + dt_polys / rec_scores
    - Result objects with ``.json`` property (not only callable)
    - Nested ``{"res": {...}}`` PaddleX envelope
    """
    items: list[dict[str, Any]] = []
    if raw is None:
        return items

    # predict() / ocr() có thể trả generator hoặc list trang.
    pages: list[Any]
    if isinstance(raw, dict):
        pages = [raw]
    elif isinstance(raw, (list, tuple)):
        pages = list(raw)
    else:
        try:
            pages = list(raw)
        except TypeError:
            pages = [raw]

    for page in pages:
        page_obj = _unwrap_page_payload(page)

        # PaddleOCR 3.x page dict
        if isinstance(page_obj, dict) and (
            "dt_polys" in page_obj or "rec_texts" in page_obj or "rec_polys" in page_obj
        ):
            polys = _as_sequence(page_obj.get("dt_polys") or page_obj.get("rec_polys") or [])
            texts = _as_sequence(page_obj.get("rec_texts") or page_obj.get("texts") or [])
            scores = _as_sequence(page_obj.get("rec_scores") or page_obj.get("scores") or [])
            for idx, pts in enumerate(polys):
                try:
                    if pts is None:
                        continue
                    poly = pts
                    # numpy polygon → list
                    if hasattr(pts, "tolist"):
                        try:
                            poly = pts.tolist()
                        except Exception:
                            poly = pts
                    if (
                        isinstance(poly, (list, tuple))
                        and poly
                        and isinstance(poly[0], (list, tuple))
                        and len(poly[0]) == 2
                    ):
                        pass
                    elif isinstance(poly, (list, tuple)) and len(poly) >= 4:
                        pass
                    else:
                        continue
                    text = str(texts[idx] if idx < len(texts) else "")
                    score = float(scores[idx] if idx < len(scores) else 0.0)
                    items.append(
                        {
                            "bbox": _normalize_quad(poly),
                            "text": text,
                            "score": score,
                        }
                    )
                except Exception:
                    continue
            continue

        # Classic: page = list of lines; đôi khi raw = [page]
        lines = page_obj
        if isinstance(page_obj, list) and page_obj and not isinstance(page_obj[0], dict):
            # Có thể là [[[pts],(text,conf)], ...] hoặc nested thêm 1 lớp
            first = page_obj[0]
            if (
                isinstance(first, (list, tuple))
                and len(first) == 2
                and isinstance(first[0], (list, tuple))
            ):
                lines = page_obj
            elif isinstance(first, list):
                lines = first
        elif not isinstance(page_obj, list):
            # Unknown non-list page — skip instead of iterating mapping keys as lines.
            continue

        for line in lines or []:
            try:
                if isinstance(line, dict):
                    text = str(line.get("text") or line.get("txt") or "")
                    score = float(line.get("score") or line.get("confidence") or 0.0)
                    pts = line.get("bbox") or line.get("boxes") or line.get("points") or []
                    items.append(
                        {
                            "bbox": _normalize_quad(pts),
                            "text": text,
                            "score": score,
                        }
                    )
                    continue
                pts, meta = line[0], line[1]
                if isinstance(meta, (list, tuple)) and len(meta) >= 2:
                    text, score = meta[0], float(meta[1])
                else:
                    text, score = str(meta), 0.0
                items.append(
                    {
                        "bbox": _normalize_quad(pts),
                        "text": str(text or ""),
                        "score": float(score or 0.0),
                    }
                )
            except Exception:
                continue
    return items


app = FastAPI(
    title="HF PaddleOCR API",
    description="POST /predict — nhận ảnh, trả bbox + text + score (lang=ch).",
    version="1.0.1",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Probe nhẹ — không load model (scale-to-zero ready nhanh; tránh 503 do preload)."""
    return {"status": "ok"}


@app.post("/predict")
async def predict(file: UploadFile = File(...)) -> JSONResponse:
    """
    Nhận file ảnh upload (.jpg / png...), chạy PaddleOCR (lang=ch),
    trả về mảng JSON: bbox (4 góc) + text + score.
    """
    try:
        # Đọc bytes từ multipart upload.
        content = await file.read()
        if not content:
            raise HTTPException(status_code=422, detail="File ảnh trống.")

        # Chuyển bytes → RGB numpy array cho PaddleOCR.
        try:
            image = Image.open(io.BytesIO(content)).convert("RGB")
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Không đọc được ảnh: {exc}",
            ) from exc
        img_np = np.array(image)

        # Lấy engine (lazy) và chạy OCR.
        engine = get_ocr_engine()
        try:
            raw = engine.ocr(img_np, cls=True)
        except TypeError:
            # PaddleOCR 3.x có thể không nhận cls=
            try:
                raw = engine.ocr(img_np)
            except Exception:
                if hasattr(engine, "predict"):
                    raw = engine.predict(img_np)
                else:
                    raise

        items = parse_paddle_ocr_result(raw)
        if not items:
            logger.warning(
                "predict_empty_parse",
                extra={
                    "raw_type": type(raw).__name__,
                    "image_w": int(image.size[0]),
                    "image_h": int(image.size[1]),
                },
            )
        return JSONResponse(content=items)

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — không để Spaces sập process
        logger.exception("predict_failed")
        raise HTTPException(
            status_code=500,
            detail=f"OCR thất bại: {exc}",
        ) from exc
