from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.db.session import get_db_session
from src.downloaders.douyin_browser_download_cookies import _account_for_workspace
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest
from src.downloaders.errors import DownloadError
from src.downloaders.playwright_douyin_video_resolver import (
    PlaywrightDouyinVideoResolver,
    staging_path_for_aweme,
)
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


class AwemeDownloadResponse(BaseModel):
    aweme_id: str
    staging_path: str
    size_bytes: int
    format_id: str | None = None
    watermark_free: bool | None = None
    resolver_name: str = "playwright_browser"
    height: int | None = None
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
    account = _account_for_workspace(db, workspace_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="resolve_failed: No Douyin account with browser profile. Connect Douyin account first.",
        )
    resolved_account_id = account_id or account.id
    if douyin_browser_context_registry.has_any_active_context():
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
        account_connection_id=account.id,
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
            account_connection_id=account.id,
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

        sync_download_cookie_store_from_live_browser(db, body.workspace_id)

    account_id = _ensure_live_playwright_context(db=db, workspace_id=body.workspace_id, account_id=account_id)

    try:
        resolved = PlaywrightDouyinVideoResolver().resolve(
            DouyinVideoResolveRequest(
                aweme_id=body.aweme_id,
                page_url=body.page_url,
                session_cookie=None,
                user_agent=None,
                account_connection_id=account_id,
                workspace_id=body.workspace_id,
            )
        )
    except DownloadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{exc.code}: {exc.message}") from exc

    staging = staging_path_for_aweme(body.aweme_id)
    if not staging.exists():
        staging.write_bytes(resolved.content)

    return AwemeDownloadResponse(
        aweme_id=body.aweme_id,
        staging_path=str(staging.resolve()),
        size_bytes=len(resolved.content),
        format_id=resolved.format_id,
        watermark_free=resolved.watermark_free,
        resolver_name=resolved.resolver_name,
        height=resolved.height,
        author_handle=resolved.author_handle,
        author_display_name=resolved.author_display_name,
    )
