"""Ensure local FSRCNN SuperRes weights exist (download once if missing)."""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# Saafke FSRCNN TensorFlow → OpenCV .pb (x2).
DEFAULT_FSRCNN_PB_URL = (
    "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x2.pb"
)
FSRCNN_PB_URL_ENV = "FSRCNN_PB_URL"
_MIN_MODEL_BYTES = 10_000


def default_fsrcnn_model_path() -> Path:
    """``apps/api/models/FSRCNN_x2.pb`` relative to this package tree."""
    api_root = Path(__file__).resolve().parents[3]
    return api_root / "models" / "FSRCNN_x2.pb"


def ensure_fsrcnn_pb(dest: Path | None = None) -> Path:
    """
    Return path to ``FSRCNN_x2.pb``, downloading when missing or too small.

    Override URL via ``FSRCNN_PB_URL``. Raises ``OSError`` / ``RuntimeError`` on failure.
    """
    path = Path(dest) if dest is not None else default_fsrcnn_model_path()
    if path.is_file() and path.stat().st_size >= _MIN_MODEL_BYTES:
        return path

    url = (os.environ.get(FSRCNN_PB_URL_ENV) or DEFAULT_FSRCNN_PB_URL).strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".pb.partial")
    logger.info("fsrcnn_pb_download_start url=%s dest=%s", url[:120], path)
    try:
        urllib.request.urlretrieve(url, str(tmp))  # noqa: S310 — operator-controlled URL
        size = tmp.stat().st_size if tmp.is_file() else 0
        if size < _MIN_MODEL_BYTES:
            raise RuntimeError(
                f"Downloaded FSRCNN_x2.pb too small ({size} bytes) from {url[:80]}"
            )
        tmp.replace(path)
    except Exception:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise

    logger.info("fsrcnn_pb_download_ok path=%s bytes=%s", path, path.stat().st_size)
    return path
