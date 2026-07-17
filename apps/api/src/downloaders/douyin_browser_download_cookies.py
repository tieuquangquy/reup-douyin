from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.downloaders.douyin_download_cookie_store import (
    read_download_cookie_store_for_account,
    write_download_cookie_store_for_account,
)
from src.enums import DouyinAccountConnectionStatus
from src.services.douyin_account_service import DouyinAccountService
from src.services.douyin_browser_context_registry import (
    cookie_header_from_playwright_cookies,
    douyin_browser_context_registry,
    has_authenticated_douyin_cookies,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrowserDownloadCookieExport:
    playwright_cookies: tuple[dict, ...]
    user_agent: str
    proxy_url: str | None
    account_id: UUID
    cookie_source: str = "browser_live"


def _account_for_workspace(db: Session, workspace_id: UUID):
    service = DouyinAccountService(db)
    account = service.default_account(workspace_id=workspace_id)
    if account is None:
        active_accounts = service.list_accounts(
            workspace_id=workspace_id,
            status=DouyinAccountConnectionStatus.ACTIVE,
        )
        account = active_accounts[0] if active_accounts else None
    return account


def sync_download_cookie_store_from_live_browser(db: Session, workspace_id: UUID) -> BrowserDownloadCookieExport | None:
    """Flush live Playwright cookies to shared store (API process owns the browser)."""
    settings = get_settings()
    if not settings.douyin_persistent_browser_profile_enabled:
        return None

    account = _account_for_workspace(db, workspace_id)
    if account is None:
        return None

    metadata = dict(getattr(account, "metadata_json", None) or {})
    browser_profile_id = metadata.get("browser_profile_id")
    browser_profile_path = metadata.get("browser_profile_path")
    if not isinstance(browser_profile_id, str):
        browser_profile_id = None
    if not isinstance(browser_profile_path, str):
        browser_profile_path = None
    if not browser_profile_id and not browser_profile_path:
        return None

    exported = douyin_browser_context_registry.export_playwright_cookies_for_download(
        workspace_id=workspace_id,
        account_connection_id=account.id,
        browser_profile_id=browser_profile_id,
        browser_profile_path=browser_profile_path,
        user_agent=account.user_agent,
        proxy_url=account.proxy_url,
        allow_open_browser=False,
    )
    if exported is None:
        logger.warning(
            "download_cookie_store_sync_skipped",
            extra={"workspace_id": str(workspace_id), "account_id": str(account.id), "reason": "live_export_unavailable"},
        )
        return None

    cookies, user_agent = exported
    written = write_download_cookie_store_for_account(
        account_id=account.id,
        playwright_cookies=cookies,
        user_agent=user_agent,
    )
    if written is None:
        return None

    return BrowserDownloadCookieExport(
        playwright_cookies=tuple(cookies),
        user_agent=user_agent,
        proxy_url=account.proxy_url,
        account_id=account.id,
        cookie_source="browser_live",
    )


def resolve_browser_download_cookies(db: Session, workspace_id: UUID) -> BrowserDownloadCookieExport | None:
    settings = get_settings()
    if not settings.douyin_persistent_browser_profile_enabled:
        return None

    account = _account_for_workspace(db, workspace_id)
    if account is None:
        return None

    metadata = dict(getattr(account, "metadata_json", None) or {})
    browser_profile_id = metadata.get("browser_profile_id")
    browser_profile_path = metadata.get("browser_profile_path")
    if not isinstance(browser_profile_id, str):
        browser_profile_id = None
    if not isinstance(browser_profile_path, str):
        browser_profile_path = None
    if not browser_profile_id and not browser_profile_path:
        return None

    exported = douyin_browser_context_registry.export_playwright_cookies_for_download(
        workspace_id=workspace_id,
        account_connection_id=account.id,
        browser_profile_id=browser_profile_id,
        browser_profile_path=browser_profile_path,
        user_agent=account.user_agent,
        proxy_url=account.proxy_url,
        allow_open_browser=False,
    )
    if exported is not None:
        cookies, user_agent = exported
        if cookies:
            write_download_cookie_store_for_account(
                account_id=account.id,
                playwright_cookies=cookies,
                user_agent=user_agent,
            )
            return BrowserDownloadCookieExport(
                playwright_cookies=tuple(cookies),
                user_agent=user_agent,
                proxy_url=account.proxy_url,
                account_id=account.id,
                cookie_source="browser_live",
            )

    store = read_download_cookie_store_for_account(account_id=account.id)
    if store is None:
        return None
    if not store.playwright_cookies:
        return None

    if not has_authenticated_douyin_cookies(list(store.playwright_cookies)):
        logger.warning(
            "download_cookie_store_not_authenticated",
            extra={"account_id": str(account.id)},
        )
        return None

    logger.info(
        "download_cookies_loaded_from_store",
        extra={"account_id": str(account.id), "cookie_count": len(store.playwright_cookies)},
    )
    return BrowserDownloadCookieExport(
        playwright_cookies=store.playwright_cookies,
        user_agent=store.user_agent,
        proxy_url=account.proxy_url,
        account_id=account.id,
        cookie_source="browser_store",
    )


def browser_export_to_session_cookie(export: BrowserDownloadCookieExport) -> str | None:
    header = cookie_header_from_playwright_cookies(list(export.playwright_cookies))
    return header or None


def account_has_browser_profile(account) -> bool:
    metadata = dict(getattr(account, "metadata_json", None) or {})
    profile_id = metadata.get("browser_profile_id")
    profile_path = metadata.get("browser_profile_path")
    return (isinstance(profile_id, str) and bool(profile_id.strip())) or (
        isinstance(profile_path, str) and bool(profile_path.strip())
    )
