"""
API OCR nội bộ — FastAPI bọc PaddleOCR.

Default engine: ``OCR_PADDLE_ENGINE=auto`` — picks classic on low-RAM hosts
(<20 GiB) and PaddleOCR-VL-1.6 when RAM is enough. Explicit ``vl16`` still
falls back to classic on init/OOM failure.

Contract (Local or Cloud): ``POST /predict`` → JSON
``[{"bbox": [[x,y]x4], "text": "...", "score": 0.99}, ...]``
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
_ocr_engine: Any = None
_engine_kind: str | None = None
_engine_fallback: bool = False
_engine_reason: str | None = None

CLASSIC_DETECTION_MODEL = "PP-OCRv6_medium_det"
CLASSIC_RECOGNITION_MODEL = "PP-OCRv6_medium_rec"
CLASSIC_MODEL_VERSION = "ppocrv6-medium-det-rec"
VL_MODEL_VERSION = "paddleocr-vl-1.6"


def _mkldnn_requested() -> bool:
    """Local CPU boost via ``OCR_PADDLE_ENABLE_MKLDNN=1`` (off by default — Cloud Run crash)."""
    return (os.environ.get("OCR_PADDLE_ENABLE_MKLDNN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def configure_paddle_cpu_safe_runtime() -> None:
    """PIR off always; MKLDNN off unless ``OCR_PADDLE_ENABLE_MKLDNN=1`` (local CPU).

    Must run BEFORE importing/initializing paddleocr. Mirrors apps/api ocr_pipeline.
    Cloud Run / default: MKLDNN disabled (Paddle 3.3.x PIR↔oneDNN crash).
    """
    os.environ["FLAGS_enable_pir_api"] = "0"
    os.environ["FLAGS_enable_pir_in_executor"] = "0"
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    if _mkldnn_requested():
        os.environ["FLAGS_use_mkldnn"] = "1"
        os.environ["FLAGS_onednn"] = "1"
        os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "1"
        try:
            import paddle  # type: ignore

            paddle.set_flags({"FLAGS_use_mkldnn": True})
        except Exception:
            pass
        return
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["FLAGS_onednn"] = "0"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
    try:
        import paddle  # type: ignore

        paddle.set_flags({"FLAGS_use_mkldnn": False})
    except Exception:
        pass


# Apply as early as possible (module import), before first /predict.
configure_paddle_cpu_safe_runtime()


def _available_ram_gb() -> float | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return float(line.split()[1]) / (1024.0 * 1024.0)
    except Exception:
        return None
    return None


def _vl_force_inprocess() -> bool:
    return (os.environ.get("OCR_PADDLE_VL_INPROCESS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def resolve_engine_mode() -> str:
    """Return ``vl16`` or ``classic``.

    ``OCR_PADDLE_ENGINE``:
    - ``auto`` (default): classic if MemTotal < 20 GiB (unless force), else vl16
    - ``classic`` / ``vl16``: explicit
    """
    raw = (os.environ.get("OCR_PADDLE_ENGINE") or "auto").strip().lower()
    if raw in {"classic", "ppocr", "ch", "legacy"}:
        return "classic"
    if raw in {"vl16", "vl", "vl1.6", "paddleocr-vl"}:
        return "vl16"
    # auto
    ram_gb = _available_ram_gb()
    if ram_gb is not None and ram_gb < 20.0 and not _vl_force_inprocess():
        return "classic"
    return "vl16"


def engine_request_label() -> str:
    return (os.environ.get("OCR_PADDLE_ENGINE") or "auto").strip().lower() or "auto"


def _init_classic_paddleocr() -> Any:
    """Classic PP-OCR: pin v6 Medium for small Chinese Douyin text."""
    from paddleocr import PaddleOCR  # type: ignore

    configure_paddle_cpu_safe_runtime()
    want_mkldnn = _mkldnn_requested()
    # PaddleOCR 3.x: pin the exact model family observed to work best on the
    # Phase-2 candidate. Douyin hardsub is axis-aligned, so disable document,
    # unwarping, and text-line orientation stages.
    init_attempts = [
        {
            "lang": "ch",
            "text_detection_model_name": CLASSIC_DETECTION_MODEL,
            "text_recognition_model_name": CLASSIC_RECOGNITION_MODEL,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "enable_mkldnn": want_mkldnn,
        },
        # Compatibility fallbacks for older PaddleOCR releases.
        {
            "lang": "ch",
            "use_angle_cls": False,
            "ocr_version": "PP-OCRv4",
            "det_limit_side_len": 960,
            "enable_mkldnn": want_mkldnn,
            "use_gpu": False,
            "show_log": False,
        },
        {
            "lang": "ch",
            "use_angle_cls": False,
            "ocr_version": "PP-OCRv3",
            "enable_mkldnn": want_mkldnn,
            "use_gpu": False,
            "show_log": False,
        },
        {
            "lang": "ch",
            "use_angle_cls": False,
            "enable_mkldnn": want_mkldnn,
            "use_gpu": False,
            "show_log": False,
        },
        {
            "lang": "ch",
            "use_angle_cls": False,
            "use_textline_orientation": False,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "enable_mkldnn": want_mkldnn,
        },
        # Fallback: MKLDNN off if local enable crashes (Paddle 3.3.x).
        {
            "lang": "ch",
            "use_angle_cls": False,
            "enable_mkldnn": False,
            "use_gpu": False,
            "show_log": False,
        },
        {"lang": "ch", "use_angle_cls": False, "enable_mkldnn": False},
        {"lang": "ch", "enable_mkldnn": False},
        {"lang": "ch"},
    ]
    last_error: Exception | None = None
    for kwargs in init_attempts:
        try:
            configure_paddle_cpu_safe_runtime()
            engine = PaddleOCR(**kwargs)
            logger.info(
                "paddleocr_classic_initialized angle_cls=%s mkldnn=%s keys=%s",
                kwargs.get("use_angle_cls"),
                kwargs.get("enable_mkldnn"),
                list(kwargs.keys()),
            )
            return engine
        except (TypeError, ValueError) as exc:
            last_error = exc
            continue
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            # MKLDNN request may crash — retry remaining attempts with safer kwargs.
            continue
    raise RuntimeError(f"Không khởi tạo được PaddleOCR classic: {last_error}")


def _vl16_subprocess_probe(timeout_s: int = 600) -> None:
    """Init VL-1.6 in a child process so OOM cannot kill the API worker.

    If the child exits non-zero (including SIGKILL/OOM), raise RuntimeError so
    ``get_ocr_engine`` can fall back to classic PP-OCR in-process.
    """
    import subprocess
    import sys
    import textwrap

    ram_gb = _available_ram_gb()
    # Only ``auto`` refuses low RAM. Explicit ``vl16`` tries (may use swap / be slow).
    if (
        engine_request_label() == "auto"
        and ram_gb is not None
        and ram_gb < 20.0
        and not _vl_force_inprocess()
    ):
        raise RuntimeError(
            f"PaddleOCR-VL-1.6 refused: MemTotal={ram_gb:.1f}GiB < 20GiB "
            "(set OCR_PADDLE_ENGINE=vl16 or OCR_PADDLE_VL_INPROCESS=1 to force)"
        )

    device = (os.environ.get("OCR_PADDLE_VL_DEVICE") or "cpu").strip() or "cpu"
    script = textwrap.dedent(
        f"""
        import os
        os.environ["FLAGS_use_mkldnn"] = "0"
        os.environ["FLAGS_onednn"] = "0"
        os.environ["FLAGS_enable_pir_api"] = "0"
        os.environ["FLAGS_enable_pir_in_executor"] = "0"
        os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        from paddleocr import PaddleOCRVL
        PaddleOCRVL(
            pipeline_version="v1.6",
            device={device!r},
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_layout_detection=False,
        )
        print("vl16_probe_ok")
        """
    )
    logger.info("paddleocr_vl16_subprocess_probe_start device=%s ram_gb=%s", device, ram_gb)
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(60, int(timeout_s)),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"PaddleOCR-VL-1.6 probe timed out after {timeout_s}s") from exc

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0 or "vl16_probe_ok" not in stdout:
        detail = stderr[-2000:] if stderr else stdout[-2000:]
        raise RuntimeError(
            f"PaddleOCR-VL-1.6 probe failed (code={completed.returncode}): {detail}"
        )
    logger.info("paddleocr_vl16_subprocess_probe_ok")


def _vl16_skip_probe() -> bool:
    return (os.environ.get("OCR_PADDLE_VL_SKIP_PROBE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _init_vl16_paddleocr() -> Any:
    """PaddleOCR-VL pipeline_version=v1.6 after an optional subprocess probe."""
    from paddleocr import PaddleOCRVL  # type: ignore

    configure_paddle_cpu_safe_runtime()
    if not _vl16_skip_probe():
        _vl16_subprocess_probe(
            timeout_s=int(os.environ.get("OCR_PADDLE_VL_PROBE_TIMEOUT_S") or "600")
        )
    else:
        logger.info("paddleocr_vl16_subprocess_probe_skipped")
    device = (os.environ.get("OCR_PADDLE_VL_DEVICE") or "cpu").strip() or "cpu"
    init_attempts: list[dict[str, Any]] = [
        {
            "pipeline_version": "v1.6",
            "device": device,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_layout_detection": False,
        },
        {
            "pipeline_version": "v1.6",
            "device": "cpu",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_layout_detection": False,
        },
        {"pipeline_version": "v1.6"},
    ]
    last_error: Exception | None = None
    for kwargs in init_attempts:
        try:
            configure_paddle_cpu_safe_runtime()
            engine = PaddleOCRVL(**kwargs)
            logger.info(
                "paddleocr_vl16_initialized",
                extra={"kwargs": {k: str(v) for k, v in kwargs.items()}},
            )
            return engine
        except (TypeError, ValueError) as exc:
            last_error = exc
            continue
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("paddleocr_vl16_init_attempt_failed: %s", exc)
            continue
    raise RuntimeError(f"Không khởi tạo được PaddleOCR-VL-1.6: {last_error}")


def _no_classic_fallback() -> bool:
    """When set, VL init failure must not silently switch to classic."""
    return (os.environ.get("OCR_PADDLE_NO_FALLBACK") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_ocr_engine() -> Any:
    """Lazy-init OCR engine. VL falls back to classic unless NO_FALLBACK is set."""
    global _ocr_engine, _engine_kind, _engine_fallback, _engine_reason
    if _ocr_engine is not None:
        return _ocr_engine

    configure_paddle_cpu_safe_runtime()
    requested = engine_request_label()
    mode = resolve_engine_mode()
    _engine_fallback = False
    ram_gb = _available_ram_gb()

    if mode == "classic":
        _ocr_engine = _init_classic_paddleocr()
        _engine_kind = "classic"
        if requested in {"auto", ""} and ram_gb is not None and ram_gb < 20.0:
            _engine_reason = f"auto_classic_low_ram:{ram_gb:.1f}GiB"
        elif requested == "classic":
            _engine_reason = "explicit_classic"
        else:
            _engine_reason = f"resolved_classic:{requested}"
        logger.info(
            "paddleocr_engine_selected kind=classic reason=%s requested=%s ram_gb=%s",
            _engine_reason,
            requested,
            ram_gb,
        )
        return _ocr_engine

    try:
        _ocr_engine = _init_vl16_paddleocr()
        _engine_kind = "vl16"
        _engine_reason = "vl16_ok"
        return _ocr_engine
    except Exception as exc:  # noqa: BLE001
        if _no_classic_fallback():
            logger.exception("paddleocr_vl16_unavailable_no_fallback: %s", exc)
            _ocr_engine = None
            _engine_kind = None
            _engine_fallback = False
            _engine_reason = f"vl16_failed_no_fallback:{exc}"
            raise RuntimeError(
                f"PaddleOCR-VL-1.6 failed (no-fallback): {exc}"
            ) from exc
        logger.exception("paddleocr_vl16_unavailable_fallback_classic: %s", exc)
        _ocr_engine = _init_classic_paddleocr()
        _engine_kind = "classic"
        _engine_fallback = True
        _engine_reason = f"vl16_fallback:{exc}"
        return _ocr_engine


def _normalize_quad(pts: Any) -> list[list[float]]:
    """Chuẩn hóa 4 góc bbox thành [[x,y], [x,y], [x,y], [x,y]]."""
    points: list[list[float]] = []
    for p in pts:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            points.append([float(p[0]), float(p[1])])
    if len(points) < 4:
        while len(points) < 4 and points:
            points.append(points[-1])
    return points[:4]


def _xyxy_to_quad(box: Any) -> list[list[float]] | None:
    vals: list[float] = []
    if hasattr(box, "tolist"):
        try:
            box = box.tolist()
        except Exception:
            pass
    if isinstance(box, dict):
        if all(k in box for k in ("x1", "y1", "x2", "y2")):
            vals = [float(box["x1"]), float(box["y1"]), float(box["x2"]), float(box["y2"])]
        elif "coordinate" in box:
            return _xyxy_to_quad(box["coordinate"])
    elif isinstance(box, (list, tuple)) and len(box) >= 4:
        if isinstance(box[0], (list, tuple)) and len(box[0]) >= 2:
            return _normalize_quad(box)
        try:
            vals = [float(box[0]), float(box[1]), float(box[2]), float(box[3])]
        except (TypeError, ValueError):
            return None
    if len(vals) < 4:
        return None
    x1, y1, x2, y2 = vals[0], vals[1], vals[2], vals[3]
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _unwrap_page_payload(page: Any) -> Any:
    """Normalize PaddleOCR 3.x Result / ``{'res': {...}}`` into a plain dict or classic page."""
    page_obj = page

    if hasattr(page, "json"):
        json_attr = getattr(page, "json")
        try:
            page_obj = json_attr() if callable(json_attr) else json_attr
        except Exception:
            page_obj = page

    if page_obj is not None and hasattr(page_obj, "keys") and not isinstance(
        page_obj, (dict, list, tuple, str, bytes)
    ):
        try:
            page_obj = dict(page_obj)
        except Exception:
            try:
                page_obj = {k: page_obj[k] for k in page_obj.keys()}  # type: ignore[index]
            except Exception:
                pass

    if isinstance(page_obj, dict) and "res" in page_obj and isinstance(page_obj.get("res"), dict):
        nested = page_obj["res"]
        if any(
            key in nested
            for key in (
                "dt_polys",
                "rec_texts",
                "rec_polys",
                "rec_scores",
                "parsing_res_list",
            )
        ):
            page_obj = nested

    return page_obj


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
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


def _parse_vl_parsing_res_list(page_obj: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    blocks = _as_sequence(page_obj.get("parsing_res_list") or [])
    skip_labels = {"image", "figure", "chart", "table", "seal", "header", "footer"}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        label = str(block.get("block_label") or block.get("label") or "").lower()
        text = str(block.get("block_content") or block.get("content") or "").strip()
        if not text:
            continue
        if label in skip_labels:
            continue
        box = (
            block.get("block_bbox")
            or block.get("bbox")
            or block.get("coordinate")
            or block.get("box")
        )
        quad = _xyxy_to_quad(box) if box is not None else None
        if quad is None:
            continue
        score = float(
            block.get("block_score")
            or block.get("score")
            or block.get("confidence")
            or 0.0
        )
        items.append({"bbox": quad, "text": text, "score": score})
    return items


def parse_paddle_ocr_result(raw: Any) -> list[dict[str, Any]]:
    """
    Phân tích output PaddleOCR / PaddleOCR-VL → mảng JSON:
    [{"bbox": [[x,y]x4], "text": "...", "score": 0.99}, ...]
    """
    items: list[dict[str, Any]] = []
    if raw is None:
        return items

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

        if isinstance(page_obj, dict) and page_obj.get("parsing_res_list"):
            items.extend(_parse_vl_parsing_res_list(page_obj))
            continue

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

        lines = page_obj
        if isinstance(page_obj, list) and page_obj and not isinstance(page_obj[0], dict):
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


def run_ocr_on_image(engine: Any, img_np: np.ndarray) -> Any:
    """Call classic ``.ocr`` or VL ``.predict`` on an RGB numpy image."""
    if _engine_kind == "vl16" and hasattr(engine, "predict"):
        return engine.predict(img_np)
    try:
        return engine.ocr(img_np, cls=True)
    except TypeError:
        try:
            return engine.ocr(img_np)
        except Exception:
            if hasattr(engine, "predict"):
                return engine.predict(img_np)
            raise


app = FastAPI(
    title="HF PaddleOCR API",
    description=(
        "POST /predict — bbox + text + score. "
        "OCR_PADDLE_ENGINE=auto|vl16|classic (auto picks classic on low RAM)."
    ),
    version="1.2.0",
)


@app.get("/health")
def health() -> dict[str, Any]:
    """Probe nhẹ — không load model. Báo engine requested / resolved từ env+RAM."""
    resolved_engine = _engine_kind or resolve_engine_mode()
    return {
        "status": "ok",
        "ocr_paddle_engine_requested": engine_request_label(),
        "ocr_paddle_engine_resolved": resolve_engine_mode(),
        "ocr_paddle_engine_active": _engine_kind,
        "ocr_model_version": (
            CLASSIC_MODEL_VERSION
            if resolved_engine == "classic"
            else VL_MODEL_VERSION
        ),
        "ocr_paddle_engine_fallback": bool(_engine_fallback),
        "ocr_paddle_engine_reason": _engine_reason,
        "ocr_paddle_ram_gb": _available_ram_gb(),
    }


@app.post("/predict")
async def predict(file: UploadFile = File(...)) -> JSONResponse:
    """
    Nhận file ảnh upload (.jpg / png...), chạy PaddleOCR / VL-1.6,
    trả về mảng JSON: bbox (4 góc) + text + score.
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=422, detail="File ảnh trống.")

        try:
            image = Image.open(io.BytesIO(content)).convert("RGB")
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Không đọc được ảnh: {exc}",
            ) from exc
        img_np = np.array(image)

        engine = get_ocr_engine()
        raw = run_ocr_on_image(engine, img_np)
        items = parse_paddle_ocr_result(raw)
        if not items:
            logger.warning(
                "predict_empty_parse",
                extra={
                    "raw_type": type(raw).__name__,
                    "engine": _engine_kind,
                    "fallback": _engine_fallback,
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
