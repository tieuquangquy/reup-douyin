from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.downloaders.douyin_browser_download_cookies import (
    BrowserDownloadCookieExport,
    account_has_browser_profile,
    browser_export_to_session_cookie,
    resolve_browser_download_cookies,
)
from src.enums import DouyinAccountConnectionStatus
from src.services.douyin_account_service import DouyinAccountError, DouyinAccountService


@dataclass(frozen=True)
class DouyinDownloadSession:
    session_cookie: str | None
    user_agent: str
    proxy_url: str | None
    playwright_cookies: tuple[dict, ...] | None = None
    cookie_source: str = "env"


def _session_from_browser_export(export: BrowserDownloadCookieExport) -> DouyinDownloadSession:
    settings = get_settings()
    return DouyinDownloadSession(
        session_cookie=browser_export_to_session_cookie(export),
        user_agent=export.user_agent or settings.douyin_user_agent,
        proxy_url=export.proxy_url or settings.douyin_proxy_url,
        playwright_cookies=export.playwright_cookies,
        cookie_source=export.cookie_source,
    )


def _default_or_active_account(db: Session, workspace_id: UUID):
    service = DouyinAccountService(db)
    account = service.default_account(workspace_id=workspace_id)
    if account is None:
        active_accounts = service.list_accounts(
            workspace_id=workspace_id,
            status=DouyinAccountConnectionStatus.ACTIVE,
        )
        account = active_accounts[0] if active_accounts else None
    return service, account


def resolve_douyin_download_session(
    db: Session,
    workspace_id: UUID,
    *,
    prefer_browser: bool | None = None,
) -> DouyinDownloadSession:
    settings = get_settings()
    use_browser_first = (
        settings.douyin_yt_dlp_prefer_browser_cookies if prefer_browser is None else prefer_browser
    )
    browser_only = prefer_browser is True

    browser_export = resolve_browser_download_cookies(db, workspace_id)
    if use_browser_first and browser_export is not None:
        return _session_from_browser_export(browser_export)

    service, account = _default_or_active_account(db, workspace_id)
    has_browser_profile = account is not None and account_has_browser_profile(account)

    # When a browser profile is configured and we prefer browser cookies, do not
    # poison yt-dlp with stale DOUYIN_SESSION_COOKIE after live/store miss.
    allow_env = (not browser_only) and not (use_browser_first and has_browser_profile)
    if allow_env and settings.douyin_session_cookie and settings.douyin_session_cookie.strip():
        return DouyinDownloadSession(
            session_cookie=settings.douyin_session_cookie.strip(),
            user_agent=settings.douyin_user_agent,
            proxy_url=settings.douyin_proxy_url,
            cookie_source="env",
        )

    if browser_export is not None:
        return _session_from_browser_export(browser_export)

    session_cookie: str | None = None
    user_agent = settings.douyin_user_agent
    proxy_url = settings.douyin_proxy_url

    if account is not None:
        try:
            runtime = service.resolve_runtime_config(account.id, require_active=False)
            session_cookie = runtime.session_cookie
            user_agent = runtime.user_agent
            proxy_url = runtime.proxy_url or proxy_url
        except DouyinAccountError:
            pass

    return DouyinDownloadSession(
        session_cookie=session_cookie,
        user_agent=user_agent,
        proxy_url=proxy_url,
        cookie_source="account_runtime",
    )
