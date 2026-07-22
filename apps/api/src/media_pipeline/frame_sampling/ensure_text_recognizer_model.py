"""Download and verify the permissively licensed local OCR recognizer assets."""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
from pathlib import Path
from typing import Callable

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode

logger = logging.getLogger(__name__)

DEFAULT_RECOGNIZER_ONNX_URL = (
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.1/"
    "onnx/PP-OCRv4/rec/ch_PP-OCRv4_rec_mobile.onnx"
)
DEFAULT_RECOGNIZER_ONNX_SHA256 = (
    "48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b"
)
DEFAULT_RECOGNIZER_DICT_URL = (
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.1/"
    "paddle/PP-OCRv4/rec/ch_PP-OCRv4_rec_mobile/ppocr_keys_v1.txt"
)
DEFAULT_RECOGNIZER_DICT_SHA256 = (
    "28b2362ad4ab2dc38769aa72feb535e3a9ddb3fd2a7585a05920e6393b1dc7f7"
)

RECOGNIZER_ONNX_URL_ENV = "LOCAL_TEXT_RECOGNIZER_ONNX_URL"
RECOGNIZER_ONNX_SHA256_ENV = "LOCAL_TEXT_RECOGNIZER_ONNX_SHA256"
RECOGNIZER_DICT_URL_ENV = "LOCAL_TEXT_RECOGNIZER_DICT_URL"
RECOGNIZER_DICT_SHA256_ENV = "LOCAL_TEXT_RECOGNIZER_DICT_SHA256"

Downloader = Callable[[str, str], object]


def _api_models_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "models"


def default_recognizer_model_path() -> Path:
    return _api_models_dir() / "ch_PP-OCRv4_rec_mobile.onnx"


def default_recognizer_dictionary_path() -> Path:
    return _api_models_dir() / "ppocr_keys_v1.txt"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified_asset(
    *,
    url: str,
    dest: Path,
    expected_sha256: str,
    min_bytes: int,
    downloader: Downloader = urllib.request.urlretrieve,
) -> Path:
    """Return a checksum-valid cached asset, downloading atomically if needed."""
    path = Path(dest)
    expected = expected_sha256.strip().lower()
    if not expected or len(expected) != 64:
        raise FrameSamplingError(
            FrameSamplingErrorCode.MODEL_DOWNLOAD_FAILED,
            f"Invalid SHA256 configured for {path.name}",
        )
    if path.is_file() and path.stat().st_size >= min_bytes and _sha256(path) == expected:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(f"{path.suffix}.partial")
    partial.unlink(missing_ok=True)
    logger.info("local_ocr_asset_download_start asset=%s", path.name)
    try:
        downloader(url, str(partial))
        size = partial.stat().st_size if partial.is_file() else 0
        actual = _sha256(partial) if size >= min_bytes else ""
        if size < min_bytes or actual != expected:
            raise FrameSamplingError(
                FrameSamplingErrorCode.MODEL_DOWNLOAD_FAILED,
                f"Verification failed for {path.name}: bytes={size} sha256={actual or 'missing'}",
            )
        partial.replace(path)
    except FrameSamplingError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        partial.unlink(missing_ok=True)
        raise FrameSamplingError(
            FrameSamplingErrorCode.MODEL_DOWNLOAD_FAILED,
            f"Failed to download {path.name}: {exc}",
        ) from exc
    logger.info("local_ocr_asset_download_ok asset=%s bytes=%s", path.name, path.stat().st_size)
    return path


def ensure_text_recognizer_assets(
    model_dest: Path | None = None,
    dictionary_dest: Path | None = None,
) -> tuple[Path, Path]:
    """Ensure the pinned Apache-2.0 RapidOCR PP-OCRv4 recognizer is cached."""
    model_path = download_verified_asset(
        url=(os.environ.get(RECOGNIZER_ONNX_URL_ENV) or DEFAULT_RECOGNIZER_ONNX_URL).strip(),
        dest=model_dest or default_recognizer_model_path(),
        expected_sha256=(
            os.environ.get(RECOGNIZER_ONNX_SHA256_ENV) or DEFAULT_RECOGNIZER_ONNX_SHA256
        ),
        min_bytes=1_000_000,
    )
    dictionary_path = download_verified_asset(
        url=(os.environ.get(RECOGNIZER_DICT_URL_ENV) or DEFAULT_RECOGNIZER_DICT_URL).strip(),
        dest=dictionary_dest or default_recognizer_dictionary_path(),
        expected_sha256=(
            os.environ.get(RECOGNIZER_DICT_SHA256_ENV) or DEFAULT_RECOGNIZER_DICT_SHA256
        ),
        min_bytes=10_000,
    )
    return model_path, dictionary_path
