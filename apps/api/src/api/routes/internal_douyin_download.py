from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.db.session import get_db_session
from src.downloaders.douyin_browser_download_cookies import _account_for_workspace
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.playwright_douyin_video_resolver import (
    PlaywrightDouyinVideoResolver,
    staging_path_for_aweme,
)
from src.downloaders.download_staging import is_managed_staging_path
from src.services.douyin_browser_context_registry import douyin_browser_context_registry
from src.services.douyin_playwright_orphan_release import (
    should_retry_playwright_open_after_orphan_release,
    terminate_orphaned_chromium_for_profile,
)

_REFRESH_SESSION_HINT = (
    "Refresh download session: open the app-managed Douyin Chromium once, log in so cookies sync, "
    "then retry Start processing (browser can stay closed; fallback runs headless when enabled)."
)

router = APIRouter(tags=["internal-douyin-download"])


class AwemeDownloadRequest(BaseModel):
    aweme_id: str = Field(min_length=1)
    page_url: str | None = None
    workspace_id: UUID | None = None
    account_connection_id: UUID | None = None
    transfer_id: str | None = Field(default=None, max_length=128)
    timeout_seconds: int | None = Field(default=None, ge=5, le=300)
    quality_profile: str = "balanced_processing"
    target_long_edge: int = Field(default=1920, ge=1, le=8_000)
    discovery_only: bool = False
    preferred_format_id: str | None = Field(default=None, max_length=512)


class AwemeDiscoveryCandidate(BaseModel):
    format_id: str | None = None
    watermark_free: bool | None = None
    watermark_authority: str | None = None
    height: int | None = None
    width: int | None = None
    bitrate: int | None = None
    codec: str | None = None
    fps: float | None = None
    hdr: bool | None = None


class AwemeDownloadResponse(BaseModel):
    aweme_id: str
    staging_path: str | None = None
    size_bytes: int = 0
    candidates: list[AwemeDiscoveryCandidate] = Field(default_factory=list)
    format_id: str | None = None
    watermark_free: bool | None = None
    watermark_authority: str | None = None
    resolver_name: str = "playwright_browser"
    height: int | None = None
    width: int | None = None
    bitrate: int | None = None
    codec: str | None = None
    fps: float | None = None
    hdr: bool | None = None
    account_connection_id: UUID | None = None
    author_handle: str | None = None
    author_display_name: str | None = None


def _ensure_loopback(request: Request) -> None:
    client = request.client
    host = (client.host if client else "") or ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="internal endpoint is loopback-only")


def _should_retry_playwright_open(reason: str | None) -> bool:
    return should_retry_playwright_open_after_orphan_release(reason)


def _ensure_live_playwright_context(*, db: Session, workspace_id: UUID | None, account_id: UUID | None) -> UUID | None:
    if workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="resolve_failed: workspace_id is required for Playwright Douyin download",
        )
    account = _account_for_workspace(db, workspace_id, account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="resolve_failed: No Douyin account with browser profile. Connect Douyin account first.",
        )
    resolved_account_id = account.id
    if douyin_browser_context_registry.has_active_context_for_account(resolved_account_id):
        return resolved_account_id

    settings = get_settings()
    if not bool(getattr(settings, "douyin_playwright_download_auto_open", True)):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"resolve_failed: Playwright auto-open disabled. {_REFRESH_SESSION_HINT}",
        )

    metadata = dict(getattr(account, "metadata_json", None) or {})
    browser_profile_path = metadata.get("browser_profile_path") if isinstance(metadata.get("browser_profile_path"), str) else None
    browser_profile_id = metadata.get("browser_profile_id") if isinstance(metadata.get("browser_profile_id"), str) else None
    headless = bool(getattr(settings, "douyin_playwright_download_headless", True))

    # Sticky warm browser: try open/attach first. Kill orphans only after a lock-style failure.
    # Download auto-open defaults to headless so Start processing does not flash a Chromium window.
    summary = douyin_browser_context_registry.open_profile_for_account(
        workspace_id=workspace_id,
        account_connection_id=resolved_account_id,
        browser_profile_id=browser_profile_id,
        browser_profile_path=browser_profile_path,
        user_agent=account.user_agent,
        proxy_url=account.proxy_url,
        allow_orphan_release=True,
        headless=headless,
    )
    if summary.status != "active" and _should_retry_playwright_open(summary.reason) and browser_profile_path:
        terminate_orphaned_chromium_for_profile(browser_profile_path)
        import time

        time.sleep(2.5)
        summary = douyin_browser_context_registry.open_profile_for_account(
            workspace_id=workspace_id,
            account_connection_id=resolved_account_id,
            browser_profile_id=browser_profile_id,
            browser_profile_path=browser_profile_path,
            user_agent=account.user_agent,
            proxy_url=account.proxy_url,
            allow_orphan_release=False,
            headless=headless,
        )

    if summary.status != "active":
        reason = summary.reason or "open_failed"
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "resolve_failed: Could not attach Playwright profile "
                f"({reason}). {_REFRESH_SESSION_HINT}"
            ),
        )
    return resolved_account_id


@router.post("/internal/douyin/aweme-download", response_model=AwemeDownloadResponse)
def download_aweme_via_playwright(
    body: AwemeDownloadRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AwemeDownloadResponse:
    _ensure_loopback(request)

    account_id = body.account_connection_id
    if account_id is None and body.workspace_id is not None:
        account = _account_for_workspace(db, body.workspace_id)
        if account is not None:
            account_id = account.id

    if body.workspace_id is not None:
        from src.downloaders.douyin_browser_download_cookies import sync_download_cookie_store_from_live_browser

        sync_download_cookie_store_from_live_browser(db, body.workspace_id, account_id)

    account_id = _ensure_live_playwright_context(db=db, workspace_id=body.workspace_id, account_id=account_id)

    resolver = PlaywrightDouyinVideoResolver()
    if body.discovery_only:
        try:
            candidates = resolver.discover(
                DouyinVideoResolveRequest(
                    aweme_id=body.aweme_id,
                    page_url=body.page_url,
                    session_cookie=None,
                    user_agent=None,
                    account_connection_id=account_id,
                    workspace_id=body.workspace_id,
                    transfer_id=body.transfer_id,
                    timeout_seconds=body.timeout_seconds,
                    quality_profile=body.quality_profile,
                    target_long_edge=body.target_long_edge,
                )
            )
        except DownloadError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{exc.code}: {exc.message}") from exc
        return AwemeDownloadResponse(
            aweme_id=body.aweme_id,
            account_connection_id=account_id,
            candidates=[
                AwemeDiscoveryCandidate(
                    format_id=item.format_id,
                    watermark_free=item.watermark_free,
                    watermark_authority=item.watermark_authority,
                    height=item.height,
                    width=item.width,
                    bitrate=item.bitrate,
                    codec=item.codec,
                    fps=item.fps,
                    hdr=item.hdr,
                )
                for item in candidates
            ],
        )

    expected_staging = staging_path_for_aweme(
        body.aweme_id,
        workspace_id=body.workspace_id,
        account_connection_id=account_id,
        transfer_id=body.transfer_id,
    )
    cancel_marker = expected_staging.with_name(f".{expected_staging.stem}.cancel")
    cancel_marker.unlink(missing_ok=True)

    def bridge_progress(_bytes_done: int, _bytes_total: int | None) -> None:
        if cancel_marker.exists():
            raise DownloadError(
                DownloadErrorCode.CANCELLED,
                "Playwright API bridge transfer was cancelled by the worker",
            )

    try:
        resolved = PlaywrightDouyinVideoResolver().resolve(
            DouyinVideoResolveRequest(
                aweme_id=body.aweme_id,
                page_url=body.page_url,
                session_cookie=None,
                user_agent=None,
                account_connection_id=account_id,
                workspace_id=body.workspace_id,
                transfer_id=body.transfer_id,
                timeout_seconds=body.timeout_seconds,
                quality_profile=body.quality_profile,
                target_long_edge=body.target_long_edge,
                preferred_format_id=body.preferred_format_id,
                on_progress=bridge_progress,
            )
        )
    except DownloadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{exc.code}: {exc.message}") from exc
    finally:
        cancel_marker.unlink(missing_ok=True)

    staging = Path(resolved.local_path) if resolved.local_path else staging_path_for_aweme(
        body.aweme_id,
        workspace_id=body.workspace_id,
        account_connection_id=account_id,
        transfer_id=body.transfer_id,
    )
    if not is_managed_staging_path(staging):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="resolve_failed: resolver returned an unmanaged staging path",
        )
    if not staging.exists() and resolved.content:
        staging.write_bytes(resolved.content)
    if not staging.is_file() or staging.stat().st_size <= 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="validation_failed: Playwright produced no usable staging file",
        )

    return AwemeDownloadResponse(
        aweme_id=body.aweme_id,
        staging_path=str(staging.resolve()),
        size_bytes=staging.stat().st_size,
        format_id=resolved.format_id,
        watermark_free=resolved.watermark_free,
        watermark_authority=getattr(resolved, "watermark_authority", None),
        resolver_name=resolved.resolver_name,
        height=resolved.height,
        width=resolved.width,
        bitrate=resolved.bitrate,
        codec=resolved.codec,
        fps=resolved.fps,
        hdr=resolved.hdr,
        account_connection_id=account_id,
        author_handle=resolved.author_handle,
        author_display_name=resolved.author_display_name,
    )
