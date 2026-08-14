from __future__ import annotations

from src.downloaders.source_video_primary_fetcher import (
    extract_aweme_id_from_url,
    is_direct_media_url,
    is_dash_media_url,
    is_douyin_page_url,
    is_hls_media_url,
    is_segmented_media_url,
)


def test_extracts_aweme_id_from_canonical_share_and_query_urls() -> None:
    assert extract_aweme_id_from_url("https://www.douyin.com/video/1234567890123456789") == "1234567890123456789"
    assert extract_aweme_id_from_url("https://www.douyin.com/share/video/1234567890123456789") == "1234567890123456789"
    assert extract_aweme_id_from_url("https://www.douyin.com/?modal_id=1234567890123456789") == "1234567890123456789"


def test_recognizes_short_and_note_pages_but_not_cdn_hls_as_page() -> None:
    assert is_douyin_page_url("https://v.douyin.com/abc123/")
    assert is_douyin_page_url("https://www.douyin.com/note/1234567890123456789")
    assert not is_douyin_page_url("https://cdn.example/master.m3u8")
    assert is_hls_media_url("https://cdn.example/master.m3u8?token=abc")
    assert is_dash_media_url("https://cdn.example/manifest.mpd?token=abc")
    assert is_segmented_media_url("https://cdn.example/manifest.mpd?token=abc")


def test_page_and_media_host_matching_uses_dns_boundaries() -> None:
    assert not is_douyin_page_url("https://evildouyin.com/video/1234567890123456789")
    assert is_douyin_page_url("https://www.douyin.com:443/video/1234567890123456789")
    assert not is_direct_media_url("https://evil-tiktokcdn.com/video.mp4")
    assert is_direct_media_url("https://v3-dy.ixigua.com/video.mp4")
