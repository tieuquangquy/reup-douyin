from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.downloaders.base import DownloadedObject
from src.downloaders.playwright_douyin_video_resolver import RankedPlayUrl
from src.services.douyin_browser_context_registry import DouyinBrowserContextRegistry, cookie_header_for_url


def test_playwright_candidate_prefers_streamed_file_without_response_body(tmp_path: Path) -> None:
    page = SimpleNamespace(context=SimpleNamespace(cookies=lambda: [], request=MagicMock()))
    candidate = RankedPlayUrl(
        url="https://cdn.example/video.mp4",
        source="bit_rate",
        height=1920,
        width=1080,
        bitrate=5_000_000,
        watermark_free=True,
        codec="h264",
    )
    destination = tmp_path / "video.mp4"

    seen_kwargs: dict = {}

    def stream_to_file(_url, target, **kwargs):
        seen_kwargs.update(kwargs)
        path = Path(target)
        path.write_bytes(b"streamed-video")
        return DownloadedObject(
            content=None,
            mime_type="video/mp4",
            filename=path.name,
            local_path=str(path),
            size_bytes=path.stat().st_size,
        )

    with patch(
        "src.downloaders.http.HttpAssetDownloader.fetch_to_file",
        side_effect=stream_to_file,
    ), patch(
        "src.services.douyin_browser_context_registry._file_has_video_stream",
        return_value=True,
    ):
        path, size, url, format_id, clean = DouyinBrowserContextRegistry()._download_ranked_media_to_file(
            page=page,
            candidates=[candidate],
            user_agent="ua",
            proxy_url="http://127.0.0.1:7890",
            timeout_ms=30_000,
            destination_path=destination,
        )

    assert Path(path).read_bytes() == b"streamed-video"
    assert size == len(b"streamed-video")
    assert url == candidate.url
    assert "h264" in format_id
    assert clean is True
    assert seen_kwargs["proxy_url"] == "http://127.0.0.1:7890"
    page.context.request.get.assert_not_called()


def test_media_cookie_header_matches_domain_path_and_secure_flag() -> None:
    cookies = [
        {"name": "sessionid", "value": "secret", "domain": ".douyin.com", "path": "/", "secure": True},
        {"name": "cdn", "value": "ok", "domain": ".douyinvod.com", "path": "/video", "secure": True},
    ]

    assert cookie_header_for_url(cookies, "https://v1.douyinvod.com/video/a.mp4") == "cdn=ok"
    assert cookie_header_for_url(cookies, "https://v1.douyinvod.com/videography/a.mp4") == ""
    assert cookie_header_for_url(cookies, "http://v1.douyinvod.com/video/a.mp4") == ""
    assert cookie_header_for_url(cookies, "https://attacker.example/video/a.mp4") == ""
