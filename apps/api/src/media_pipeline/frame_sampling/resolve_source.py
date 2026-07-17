"""Resolve local path or remote URL to a local video file for FFmpeg."""

from __future__ import annotations

import logging
import tempfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode

logger = logging.getLogger(__name__)


def _is_remote_url(source: str) -> bool:
    parsed = urlparse(source)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@contextmanager
def resolve_video_source(video_source: str | Path) -> Iterator[Path]:
    """Yield a local filesystem path for FFmpeg input.

    - Local path: must exist as a file.
    - http(s) URL: download once into a temp file (Cloud Run ephemeral disk).
    """
    source_text = str(video_source).strip()
    if not source_text:
        raise FrameSamplingError(
            FrameSamplingErrorCode.SOURCE_MISSING,
            "video_source is empty",
        )

    if _is_remote_url(source_text):
        suffix = Path(urlparse(source_text).path).suffix or ".mp4"
        tmp = tempfile.NamedTemporaryFile(prefix="frame-sample-", suffix=suffix, delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            logger.info("frame_sampling_download_start", extra={"url_host": urlparse(source_text).netloc})
            urllib.request.urlretrieve(source_text, str(tmp_path))  # noqa: S310 — operator/job-controlled URL
            if tmp_path.stat().st_size <= 0:
                raise FrameSamplingError(
                    FrameSamplingErrorCode.SOURCE_RESOLVE_FAILED,
                    "Downloaded video is empty",
                )
            yield tmp_path
        except FrameSamplingError:
            raise
        except Exception as exc:
            raise FrameSamplingError(
                FrameSamplingErrorCode.SOURCE_RESOLVE_FAILED,
                f"Failed to download video URL: {exc}",
            ) from exc
        finally:
            tmp_path.unlink(missing_ok=True)
        return

    path = Path(source_text)
    if not path.is_file():
        raise FrameSamplingError(
            FrameSamplingErrorCode.SOURCE_MISSING,
            f"Source video file missing: {path}",
        )
    yield path
