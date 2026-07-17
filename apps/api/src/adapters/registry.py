from __future__ import annotations

from src.adapters.base import SourceAdapter
from src.adapters.douyin import DouyinProfileAdapter
from src.adapters.douyin_live_fetch import DouyinLiveFetchClient, DouyinLiveFetchConfig
from src.core.settings import Settings, get_settings
from src.enums import SourcePlatformEnum


def build_source_adapters(settings: Settings | None = None) -> dict[SourcePlatformEnum, SourceAdapter]:
    settings = settings or get_settings()
    fetch_client = None
    if settings.douyin_enable_live_fetch:
        fetch_client = DouyinLiveFetchClient(
            DouyinLiveFetchConfig(
                user_agent=settings.douyin_user_agent,
                session_cookie=settings.douyin_session_cookie,
                proxy_url=settings.douyin_proxy_url,
                timeout_seconds=settings.douyin_fetch_timeout_seconds,
                max_videos=settings.douyin_fetch_max_videos,
            )
        )
    return {SourcePlatformEnum.DOUYIN: DouyinProfileAdapter(fetch_client=fetch_client)}
