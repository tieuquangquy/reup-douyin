from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from src.core.settings import get_settings
from src.downloaders.yt_dlp_douyin_resolver import (
    playwright_cookies_to_netscape_lines,
    write_netscape_cookie_file_from_playwright,
)
from src.services.douyin_browser_context_registry import has_authenticated_douyin_cookies

logger = logging.getLogger(__name__)

_META_FILENAME = "download_cookies.meta.json"
_COOKIE_FILENAME = "download_cookies.txt"
# apps/api/src/downloaders/this_file -> repo root is parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class DownloadCookieStorePayload:
    playwright_cookies: tuple[dict, ...]
    user_agent: str
    cookie_file: Path


def download_cookie_store_root(settings=None) -> Path:
    """Shared cookie store readable by both API and worker.

    Must be repo-anchored. Relative LOCAL_STORAGE_ROOT differs by process cwd
    (apps/api vs apps/worker) and previously caused silent store misses.
    """
    settings = settings or get_settings()
    override = getattr(settings, "douyin_download_cookie_store_dir", None)
    if isinstance(override, str) and override.strip():
        return Path(override).expanduser().resolve()
    return (_REPO_ROOT / ".douyin_profiles" / "download_cookies").resolve()


def _account_dir(store_root: Path, account_id: UUID) -> Path:
    return store_root / str(account_id)


def write_download_cookie_store(
    *,
    store_root: Path,
    account_id: UUID,
    playwright_cookies: tuple[dict, ...] | list[dict],
    user_agent: str,
) -> DownloadCookieStorePayload:
    cookies = list(playwright_cookies)
    if not has_authenticated_douyin_cookies(cookies):
        raise ValueError("Refusing to write download cookie store without authenticated Douyin cookies")

    account_dir = _account_dir(store_root, account_id)
    account_dir.mkdir(parents=True, exist_ok=True)
    cookie_file = account_dir / _COOKIE_FILENAME
    meta_file = account_dir / _META_FILENAME

    write_netscape_cookie_file_from_playwright(cookies, cookie_file)
    meta_file.write_text(
        json.dumps(
            {
                "account_id": str(account_id),
                "user_agent": user_agent,
                "cookie_count": len(cookies),
                "playwright_cookies": cookies,
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    logger.info(
        "download_cookie_store_written",
        extra={"account_id": str(account_id), "cookie_count": len(cookies)},
    )
    return DownloadCookieStorePayload(
        playwright_cookies=tuple(cookies),
        user_agent=user_agent,
        cookie_file=cookie_file,
    )


def read_download_cookie_store(*, store_root: Path, account_id: UUID) -> DownloadCookieStorePayload | None:
    account_dir = _account_dir(store_root, account_id)
    cookie_file = account_dir / _COOKIE_FILENAME
    meta_file = account_dir / _META_FILENAME
    if not cookie_file.exists() or not meta_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("download_cookie_store_meta_unreadable", extra={"account_id": str(account_id)})
        return None

    raw_cookies = meta.get("playwright_cookies")
    if not isinstance(raw_cookies, list) or not raw_cookies:
        return None
    cookies = [c for c in raw_cookies if isinstance(c, dict)]
    if not has_authenticated_douyin_cookies(cookies):
        return None

    user_agent = meta.get("user_agent")
    if not isinstance(user_agent, str) or not user_agent.strip():
        user_agent = get_settings().douyin_user_agent

    # Ensure netscape file still matches meta for yt-dlp direct use.
    lines = playwright_cookies_to_netscape_lines(cookies)
    if len(lines) <= 3:
        return None

    return DownloadCookieStorePayload(
        playwright_cookies=tuple(cookies),
        user_agent=user_agent,
        cookie_file=cookie_file,
    )


def write_download_cookie_store_for_account(
    *,
    account_id: UUID,
    playwright_cookies: tuple[dict, ...] | list[dict],
    user_agent: str,
) -> DownloadCookieStorePayload | None:
    try:
        return write_download_cookie_store(
            store_root=download_cookie_store_root(),
            account_id=account_id,
            playwright_cookies=playwright_cookies,
            user_agent=user_agent,
        )
    except Exception:
        logger.exception("download_cookie_store_write_failed", extra={"account_id": str(account_id)})
        return None


def read_download_cookie_store_for_account(*, account_id: UUID) -> DownloadCookieStorePayload | None:
    return read_download_cookie_store(store_root=download_cookie_store_root(), account_id=account_id)
