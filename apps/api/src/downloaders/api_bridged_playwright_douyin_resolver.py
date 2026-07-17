from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib import error, request as urlrequest

from src.downloaders.source_video_filename import parse_height_from_format_label
from src.downloaders.playwright_douyin_video_resolver import staging_path_for_aweme
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest, ResolvedDouyinVideo
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.core.settings import get_settings

logger = logging.getLogger(__name__)


class ApiBridgedPlaywrightDouyinResolver:
    """Worker-side bridge: ask the API process (which owns Playwright) to download."""

    @staticmethod
    def bridge_http_timeout_seconds(settings=None) -> float:
        """HTTP client budget must exceed nested Playwright waits or urllib raises TimeoutError."""
        cfg = settings or get_settings()
        playwright_ms = float(getattr(cfg, "douyin_playwright_download_timeout_ms", 90_000) or 90_000)
        # Playwright may spend timeout_ms on goto + again on CDN fetch; add buffer for JSON/staging.
        return max(180.0, (playwright_ms / 1000.0) * 2.5 + 30.0)

    def is_available(self) -> bool:
        settings = get_settings()
        if not getattr(settings, "douyin_playwright_download_enabled", True):
            return False
        base = getattr(settings, "douyin_download_api_base_url", None) or "http://127.0.0.1:8000"
        return bool(str(base).strip())

    def resolve(self, request: DouyinVideoResolveRequest) -> ResolvedDouyinVideo:
        settings = get_settings()
        base = (getattr(settings, "douyin_download_api_base_url", None) or "http://127.0.0.1:8000").rstrip("/")
        timeout = self.bridge_http_timeout_seconds(settings)
        payload = {
            "aweme_id": request.aweme_id,
            "page_url": request.page_url,
            "workspace_id": str(request.workspace_id) if request.workspace_id else None,
            "account_connection_id": str(request.account_connection_id) if request.account_connection_id else None,
        }
        url = f"{base}/internal/douyin/aweme-download"
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlrequest.urlopen(req, timeout=timeout) as response:
                raw = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"Playwright download bridge HTTP {exc.code}: {detail}",
            ) from exc
        except TimeoutError as exc:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"Playwright download bridge timed out after {timeout:.0f}s waiting for API at {url}",
            ) from exc
        except error.URLError as exc:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"Playwright download bridge could not reach API at {url}: {exc.reason}",
            ) from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise DownloadError(DownloadErrorCode.RESOLVE_FAILED, "Playwright download bridge returned invalid JSON") from exc

        staging_path = data.get("staging_path")
        if not isinstance(staging_path, str) or not staging_path.strip():
            raise DownloadError(DownloadErrorCode.RESOLVE_FAILED, "Playwright download bridge returned no staging_path")

        path = Path(staging_path)
        if not path.exists():
            fallback = staging_path_for_aweme(request.aweme_id)
            if fallback.exists():
                path = fallback
            else:
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    f"Playwright staging file missing: {staging_path}",
                )

        content = path.read_bytes()
        if not content:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, "Playwright staging file is empty")

        watermark_free = data.get("watermark_free")
        if not isinstance(watermark_free, bool):
            format_id = str(data.get("format_id") or "")
            # download_addr is commonly logo-burned; play/bit_rate labels are preferred no-logo.
            watermark_free = not format_id.startswith("download_addr")

        format_id = str(data.get("format_id") or "playwright")
        height = data.get("height")
        if not isinstance(height, int) or height <= 0:
            height = parse_height_from_format_label(format_id)
        author_handle = data.get("author_handle")
        author_display_name = data.get("author_display_name")
        author_handle = author_handle.strip().lstrip("@") if isinstance(author_handle, str) and author_handle.strip() else None
        author_display_name = author_display_name.strip() if isinstance(author_display_name, str) and author_display_name.strip() else None

        logger.info(
            "playwright_bridge_download_loaded",
            extra={
                "aweme_id": request.aweme_id,
                "bytes": len(content),
                "staging_path": str(path),
                "watermark_free": watermark_free,
                "height": height,
                "author_handle": author_handle,
            },
        )
        return ResolvedDouyinVideo(
            content=content,
            mime_type="video/mp4",
            filename=f"{request.aweme_id}.mp4",
            resolver_name="playwright_browser",
            format_id=format_id,
            height=height,
            watermark_free=watermark_free,
            author_handle=author_handle,
            author_display_name=author_display_name,
        )
