"""Ensure local DBNet ONNX weights exist (download once if missing)."""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode

logger = logging.getLogger(__name__)

# chineseocr_lite onnx branch — ~1.8MB det-only weights.
DEFAULT_DBNET_ONNX_URL = (
    "https://github.com/DayBreak-u/chineseocr_lite/raw/onnx/models/dbnet.onnx"
)
DBNET_ONNX_URL_ENV = "DBNET_ONNX_URL"
_MIN_MODEL_BYTES = 100_000


def default_dbnet_model_path() -> Path:
    """``apps/api/models/dbnet.onnx`` relative to this package tree."""
    # .../apps/api/src/media_pipeline/frame_sampling/ensure_dbnet_model.py
    api_root = Path(__file__).resolve().parents[3]
    return api_root / "models" / "dbnet.onnx"


def ensure_dbnet_onnx(dest: Path | None = None) -> Path:
    """
    Return path to ``dbnet.onnx``, downloading when missing or too small.

    Override URL via ``DBNET_ONNX_URL``. Raises ``FrameSamplingError`` on failure.
    """
    path = Path(dest) if dest is not None else default_dbnet_model_path()
    if path.is_file() and path.stat().st_size >= _MIN_MODEL_BYTES:
        return path

    url = (os.environ.get(DBNET_ONNX_URL_ENV) or DEFAULT_DBNET_ONNX_URL).strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".onnx.partial")
    logger.info("dbnet_onnx_download_start url=%s dest=%s", url[:120], path)
    try:
        urllib.request.urlretrieve(url, str(tmp))  # noqa: S310 — operator-controlled URL
        size = tmp.stat().st_size if tmp.is_file() else 0
        if size < _MIN_MODEL_BYTES:
            raise FrameSamplingError(
                FrameSamplingErrorCode.MODEL_DOWNLOAD_FAILED,
                f"Downloaded dbnet.onnx too small ({size} bytes) from {url[:80]}",
            )
        tmp.replace(path)
    except FrameSamplingError:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise FrameSamplingError(
            FrameSamplingErrorCode.MODEL_DOWNLOAD_FAILED,
            f"Failed to download dbnet.onnx: {exc}",
        ) from exc

    logger.info("dbnet_onnx_download_ok path=%s bytes=%s", path, path.stat().st_size)
    return path
