from __future__ import annotations

import json
import logging
import queue
import threading
import time
from pathlib import Path
from urllib import error, request as urlrequest
from uuid import UUID

from src.downloaders.source_video_filename import parse_height_from_format_label
from src.downloaders.playwright_douyin_video_resolver import staging_path_for_aweme
from src.downloaders.download_staging import download_staging_root
from src.downloaders.download_staging import is_managed_staging_path
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest, ResolvedDouyinVideo
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.download_quality_policy import WatermarkAuthority
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

    def discover(self, request: DouyinVideoResolveRequest) -> list[ResolvedDouyinVideo]:
        """Ask the API-owned browser for candidate metadata without transfer."""
        settings = get_settings()
        base = (getattr(settings, "douyin_download_api_base_url", None) or "http://127.0.0.1:8000").rstrip("/")
        timeout = max(5.0, float(request.timeout_seconds or self.bridge_http_timeout_seconds(settings)))
        payload = {
            "aweme_id": request.aweme_id,
            "page_url": request.page_url,
            "workspace_id": str(request.workspace_id) if request.workspace_id else None,
            "account_connection_id": str(request.account_connection_id) if request.account_connection_id else None,
            "transfer_id": str(request.transfer_id) if request.transfer_id else None,
            "timeout_seconds": request.timeout_seconds,
            "quality_profile": request.quality_profile,
            "target_long_edge": request.target_long_edge,
            "discovery_only": True,
        }
        req = urlrequest.Request(
            f"{base}/internal/douyin/aweme-download",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlrequest.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"Playwright metadata discovery bridge failed: {type(exc).__name__}",
            ) from exc
        rows = data.get("candidates") if isinstance(data, dict) and isinstance(data.get("candidates"), list) else []
        out: list[ResolvedDouyinVideo] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(
                ResolvedDouyinVideo(
                    content=None,
                    mime_type="video/mp4",
                    filename=None,
                    resolver_name="playwright_bridge_discovery",
                    format_id=str(row.get("format_id") or "playwright"),
                    height=row.get("height") if isinstance(row.get("height"), int) else None,
                    width=row.get("width") if isinstance(row.get("width"), int) else None,
                    bitrate=row.get("bitrate") if isinstance(row.get("bitrate"), int) else None,
                    codec=row.get("codec") if isinstance(row.get("codec"), str) else None,
                    fps=float(row["fps"]) if isinstance(row.get("fps"), (int, float)) else None,
                    hdr=row.get("hdr") if isinstance(row.get("hdr"), bool) else None,
                    watermark_free=row.get("watermark_free") if isinstance(row.get("watermark_free"), bool) else None,
                    watermark_authority=row.get("watermark_authority") if isinstance(row.get("watermark_authority"), str) else WatermarkAuthority.UNKNOWN.value,
                )
            )
        return out

    def resolve(self, request: DouyinVideoResolveRequest) -> ResolvedDouyinVideo:
        settings = get_settings()
        base = (getattr(settings, "douyin_download_api_base_url", None) or "http://127.0.0.1:8000").rstrip("/")
        timeout = (
            max(5.0, float(request.timeout_seconds))
            if request.timeout_seconds is not None
            else self.bridge_http_timeout_seconds(settings)
        )
        payload = {
            "aweme_id": request.aweme_id,
            "page_url": request.page_url,
            "workspace_id": str(request.workspace_id) if request.workspace_id else None,
            "account_connection_id": str(request.account_connection_id) if request.account_connection_id else None,
            "transfer_id": str(request.transfer_id) if request.transfer_id else None,
            "timeout_seconds": request.timeout_seconds,
            "quality_profile": request.quality_profile,
            "target_long_edge": request.target_long_edge,
            "preferred_format_id": request.preferred_format_id,
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
            raw = _read_bridge_response(req, timeout=timeout, resolve_request=request)
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
        if not is_managed_staging_path(path):
            raise DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                "Playwright download bridge returned a path outside the managed staging root",
            )
        resolved_account_raw = data.get("account_connection_id")
        resolved_account_id: UUID | None = None
        if resolved_account_raw:
            try:
                resolved_account_id = UUID(str(resolved_account_raw))
            except (TypeError, ValueError) as exc:
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    "Playwright download bridge returned an invalid account binding",
                ) from exc
        if request.account_connection_id is not None:
            if resolved_account_id is None:
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    "Playwright download bridge omitted the selected account binding",
                )
            if str(resolved_account_id) != str(request.account_connection_id):
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    "Playwright download bridge returned a different account than requested",
                )
        if request.transfer_id is not None:
            expected = staging_path_for_aweme(
                request.aweme_id,
                workspace_id=request.workspace_id,
                account_connection_id=resolved_account_id or request.account_connection_id,
                transfer_id=request.transfer_id,
            ).resolve()
            if path.resolve() != expected:
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    "Playwright download bridge returned a stale staging artifact for another transfer",
                )
        if not path.exists():
            fallback = staging_path_for_aweme(
                request.aweme_id,
                workspace_id=request.workspace_id,
                account_connection_id=resolved_account_id or request.account_connection_id,
                transfer_id=request.transfer_id,
            )
            if fallback.exists():
                path = fallback
            else:
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    f"Playwright staging file missing: {staging_path}",
                )

        size_bytes = path.stat().st_size
        if size_bytes <= 0:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, "Playwright staging file is empty")

        watermark_free = data.get("watermark_free")
        watermark_authority = data.get("watermark_authority")
        if not isinstance(watermark_free, bool):
            # Missing bridge evidence is unknown. Do not infer a clean stream
            # merely because the format does not look like download_addr.
            watermark_free = False
            watermark_authority = WatermarkAuthority.UNKNOWN.value
        elif not isinstance(watermark_authority, str) or not watermark_authority.strip():
            watermark_authority = (
                WatermarkAuthority.VERIFIED_PLAYBACK_PROVENANCE.value
                if watermark_free
                else WatermarkAuthority.EXPLICIT_WATERMARKED.value
            )

        format_id = str(data.get("format_id") or "playwright")
        height = data.get("height")
        if not isinstance(height, int) or height <= 0:
            height = parse_height_from_format_label(format_id)
        width = data.get("width")
        width = width if isinstance(width, int) and width > 0 else None
        bitrate = data.get("bitrate")
        bitrate = bitrate if isinstance(bitrate, int) and bitrate > 0 else None
        codec = data.get("codec")
        codec = codec.strip() if isinstance(codec, str) and codec.strip() else None
        fps = data.get("fps")
        fps = float(fps) if isinstance(fps, (int, float)) and not isinstance(fps, bool) and fps > 0 else None
        hdr = data.get("hdr") if isinstance(data.get("hdr"), bool) else None
        author_handle = data.get("author_handle")
        author_display_name = data.get("author_display_name")
        author_handle = author_handle.strip().lstrip("@") if isinstance(author_handle, str) and author_handle.strip() else None
        author_display_name = author_display_name.strip() if isinstance(author_display_name, str) and author_display_name.strip() else None

        logger.info(
            "playwright_bridge_download_loaded",
            extra={
                "aweme_id": request.aweme_id,
                "bytes": size_bytes,
                "staging_file": path.name,
                "watermark_free": watermark_free,
                "height": height,
                "width": width,
                "codec": codec,
                "author_handle": author_handle,
            },
        )
        return ResolvedDouyinVideo(
            content=None,
            mime_type="video/mp4",
            filename=f"{request.aweme_id}.mp4",
            resolver_name="playwright_browser",
            format_id=format_id,
            height=height,
            width=width,
            bitrate=bitrate,
            codec=codec,
            fps=fps,
            hdr=hdr,
            watermark_free=watermark_free,
            watermark_authority=watermark_authority,
            author_handle=author_handle,
            author_display_name=author_display_name,
            local_path=str(path.resolve()),
            size_bytes=size_bytes,
            cleanup_local_path=True,
        )


def _read_bridge_response(
    req,
    *,
    timeout: float,
    resolve_request: DouyinVideoResolveRequest,
) -> bytes:
    """Read the loopback bridge while exposing staging progress/cancellation.

    The API owns Chromium, so the worker cannot receive Playwright callbacks
    directly.  Polling the shared local staging namespace keeps the durable job
    heartbeat alive and uses a marker file to ask the API-side transfer to stop.
    """
    if resolve_request.on_progress is None:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return response.read()

    progress_path = _bridge_progress_path(resolve_request)
    cancel_path = progress_path.with_name(f".{progress_path.stem}.cancel")
    cancel_path.unlink(missing_ok=True)
    result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def request_worker() -> None:
        try:
            with urlrequest.urlopen(req, timeout=timeout) as response:
                result_queue.put(("ok", response.read()))
        except BaseException as exc:  # propagate HTTPError/URLError to caller
            result_queue.put(("error", exc))

    thread = threading.Thread(target=request_worker, name="douyin-api-bridge", daemon=True)
    thread.start()
    deadline = time.monotonic() + max(1.0, float(timeout))
    last_report = 0.0
    cancel_requested = False
    remote_finished = False
    try:
        while True:
            try:
                kind, value = result_queue.get(timeout=0.5)
            except queue.Empty:
                now = time.monotonic()
                if now >= deadline:
                    cancel_path.parent.mkdir(parents=True, exist_ok=True)
                    cancel_path.touch(exist_ok=True)
                    raise TimeoutError("Douyin API bridge timed out while transferring media")
                if now - last_report >= 0.75:
                    bytes_done = _bridge_progress_size(progress_path)
                    resolve_request.on_progress(bytes_done, None)
                    last_report = now
                continue
            if kind == "error":
                remote_finished = True
                assert isinstance(value, BaseException)
                raise value
            assert isinstance(value, (bytes, bytearray))
            remote_finished = True
            final_size = _bridge_progress_size(progress_path)
            resolve_request.on_progress(final_size, final_size or None)
            return bytes(value)
    except BaseException:
        # The API-side callback checks this marker between chunks.  The daemon
        # request thread may finish naturally; no credentials or process handles
        # are exposed to the worker.
        if not remote_finished:
            cancel_path.parent.mkdir(parents=True, exist_ok=True)
            cancel_path.touch(exist_ok=True)
            cancel_requested = True
        raise
    finally:
        if not cancel_requested:
            cancel_path.unlink(missing_ok=True)


def _bridge_progress_path(request: DouyinVideoResolveRequest) -> Path:
    exact = staging_path_for_aweme(
        request.aweme_id,
        workspace_id=request.workspace_id,
        account_connection_id=request.account_connection_id,
        transfer_id=request.transfer_id,
    )
    if request.account_connection_id is not None or exact.is_file():
        return exact
    root = download_staging_root()
    workspace_part = str(request.workspace_id or "workspace-unknown")
    transfer_part = str(request.transfer_id or "transfer-default")
    candidates = list(root.glob(f"{workspace_part}/*/{request.aweme_id}/{transfer_part}/*.mp4"))
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else exact


def _bridge_progress_size(expected: Path) -> int:
    if expected.is_file():
        try:
            return expected.stat().st_size
        except OSError:
            return 0
    if not expected.parent.is_dir():
        return 0
    sizes: list[int] = []
    for candidate in expected.parent.iterdir():
        if not candidate.is_file() or candidate.name.endswith((".json", ".cancel")):
            continue
        if candidate.suffix.lower() not in {".mp4", ".part", ".webm", ".mov", ".mkv"}:
            continue
        try:
            sizes.append(candidate.stat().st_size)
        except OSError:
            continue
    return max(sizes, default=0)
