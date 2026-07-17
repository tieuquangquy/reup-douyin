from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DouyinVideoResolveRequest:
    aweme_id: str
    page_url: str | None
    session_cookie: str | None
    user_agent: str | None
    proxy_url: str | None = None
    playwright_cookies: tuple[dict, ...] | None = None
    cookie_source: str | None = None
    account_connection_id: object | None = None
    workspace_id: object | None = None


@dataclass(frozen=True)
class ResolvedDouyinVideo:
    content: bytes
    mime_type: str | None
    filename: str | None
    resolver_name: str
    format_id: str | None = None
    height: int | None = None
    width: int | None = None
    watermark_free: bool | None = None
    author_handle: str | None = None
    author_display_name: str | None = None
