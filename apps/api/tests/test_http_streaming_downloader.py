from __future__ import annotations

from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

import pytest

from src.downloaders.errors import DownloadError
from src.downloaders.http import (
    HttpAssetDownloader,
    _CredentialSafeRedirectHandler,
    _resource_fingerprint,
    _url_fingerprint,
)


class FakeResponse:
    def __init__(self, payload: bytes, *, status: int, headers: dict[str, str]):
        self.payload = payload
        self.offset = 0
        self.status = status
        self.headers = Message()
        for key, value in headers.items():
            self.headers[key] = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def getcode(self) -> int:
        return self.status

    def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.payload):
            return b""
        if size < 0:
            size = len(self.payload) - self.offset
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_fetch_to_file_streams_without_returning_content(tmp_path: Path) -> None:
    response = FakeResponse(
        b"abcdef",
        status=200,
        headers={"Content-Type": "video/mp4", "Content-Length": "6"},
    )
    progress: list[tuple[int, int | None]] = []
    target = tmp_path / "video.part"

    with patch("src.downloaders.http.urlopen", return_value=response):
        result = HttpAssetDownloader(chunk_size_bytes=2).fetch_to_file(
            "https://cdn.test/video.mp4",
            target,
            on_progress=lambda done, total: progress.append((done, total)),
        )

    assert result.content is None
    assert result.local_path == str(target.resolve())
    assert target.read_bytes() == b"abcdef"
    assert progress[-1] == (6, 6)


def test_fetch_to_file_resumes_with_http_range(tmp_path: Path) -> None:
    url = "https://cdn.test/video.mp4"
    target = tmp_path / "video.part"
    target.write_bytes(b"abc")
    target.with_name(f"{target.name}.resume.json").write_text(
        '{"url_fingerprint":"' + _url_fingerprint(url) + '"}',
        encoding="utf-8",
    )
    response = FakeResponse(
        b"def",
        status=206,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": "3",
            "Content-Range": "bytes 3-5/6",
        },
    )

    def opener(request, timeout):
        assert timeout == 30
        assert request.get_header("Range") == "bytes=3-"
        return response

    with patch("src.downloaders.http.urlopen", side_effect=opener):
        result = HttpAssetDownloader().fetch_to_file(url, target)

    assert result.size_bytes == 6
    assert target.read_bytes() == b"abcdef"


def test_fetch_to_file_restarts_when_server_ignores_range(tmp_path: Path) -> None:
    url = "https://cdn.test/video.mp4"
    target = tmp_path / "video.part"
    target.write_bytes(b"stale-partial")
    target.with_name(f"{target.name}.resume.json").write_text(
        '{"url_fingerprint":"' + _url_fingerprint(url) + '"}',
        encoding="utf-8",
    )
    response = FakeResponse(
        b"fresh",
        status=200,
        headers={"Content-Type": "video/mp4", "Content-Length": "5"},
    )

    with patch("src.downloaders.http.urlopen", return_value=response):
        HttpAssetDownloader().fetch_to_file(url, target)

    assert target.read_bytes() == b"fresh"


def test_fetch_to_file_does_not_append_wrong_range_offset(tmp_path: Path) -> None:
    url = "https://cdn.test/video.mp4"
    target = tmp_path / "video.part"
    target.write_bytes(b"old")
    target.with_name(f"{target.name}.resume.json").write_text(
        '{"url_fingerprint":"' + _url_fingerprint(url) + '"}',
        encoding="utf-8",
    )
    responses = [
        FakeResponse(
            b"fresh",
            status=206,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": "5",
                "Content-Range": "bytes 9-13/14",
            },
        ),
        FakeResponse(
            b"abcdef",
            status=200,
            headers={"Content-Type": "video/mp4", "Content-Length": "6"},
        ),
    ]

    with patch("src.downloaders.http.urlopen", side_effect=responses):
        result = HttpAssetDownloader().fetch_to_file(url, target)

    assert result.size_bytes == 6
    assert target.read_bytes() == b"abcdef"


def test_fetch_to_file_restarts_orphan_partial_without_resume_identity(tmp_path: Path) -> None:
    target = tmp_path / "video.part"
    target.write_bytes(b"untrusted-old")
    response = FakeResponse(
        b"fresh",
        status=200,
        headers={"Content-Type": "video/mp4", "Content-Length": "5"},
    )

    def opener(request, timeout):
        assert request.get_header("Range") is None
        return response

    with patch("src.downloaders.http.urlopen", side_effect=opener):
        HttpAssetDownloader().fetch_to_file("https://cdn.test/video.mp4", target)

    assert target.read_bytes() == b"fresh"


def test_fetch_to_file_resumes_rotated_signed_url_with_validator(tmp_path: Path) -> None:
    old_url = "https://cdn.test/video.mp4?expire=100&signature=old&quality=1080"
    new_url = "https://cdn.test/video.mp4?expire=200&signature=new&quality=1080"
    target = tmp_path / "video.part"
    target.write_bytes(b"abc")
    target.with_name(f"{target.name}.resume.json").write_text(
        '{"url_fingerprint":"'
        + _url_fingerprint(old_url)
        + '","resource_fingerprint":"'
        + _resource_fingerprint(old_url)
        + '","etag":"\\"media-v1\\""}',
        encoding="utf-8",
    )
    response = FakeResponse(
        b"def",
        status=206,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": "3",
            "Content-Range": "bytes 3-5/6",
            "ETag": '"media-v1"',
        },
    )

    def opener(request, timeout):
        assert request.get_header("Range") == "bytes=3-"
        assert request.get_header("If-range") == '"media-v1"'
        return response

    with patch("src.downloaders.http.urlopen", side_effect=opener):
        result = HttpAssetDownloader().fetch_to_file(new_url, target)

    assert result.size_bytes == 6
    assert target.read_bytes() == b"abcdef"


def test_fetch_to_file_restarts_rotated_signed_url_without_validator(tmp_path: Path) -> None:
    old_url = "https://cdn.test/video.mp4?expire=100&signature=old"
    new_url = "https://cdn.test/video.mp4?expire=200&signature=new"
    target = tmp_path / "video.part"
    target.write_bytes(b"stale")
    target.with_name(f"{target.name}.resume.json").write_text(
        '{"url_fingerprint":"'
        + _url_fingerprint(old_url)
        + '","resource_fingerprint":"'
        + _resource_fingerprint(old_url)
        + '"}',
        encoding="utf-8",
    )
    response = FakeResponse(
        b"fresh",
        status=200,
        headers={"Content-Type": "video/mp4", "Content-Length": "5"},
    )

    def opener(request, timeout):
        assert request.get_header("Range") is None
        return response

    with patch("src.downloaders.http.urlopen", side_effect=opener):
        result = HttpAssetDownloader().fetch_to_file(new_url, target)

    assert result.size_bytes == 5
    assert target.read_bytes() == b"fresh"


def test_redirect_handler_strips_cookie_on_cross_host_and_https_downgrade() -> None:
    handler = _CredentialSafeRedirectHandler()
    original = Request(
        "https://cdn.test/video.mp4",
        headers={"Cookie": "sessionid=secret", "If-Range": '"etag"'},
    )

    cross_host = handler.redirect_request(
        original,
        None,
        302,
        "Found",
        {},
        "https://other.test/video.mp4",
    )
    assert cross_host is not None
    assert cross_host.get_header("Cookie") is None
    assert cross_host.get_header("If-Range") is None

    downgrade = handler.redirect_request(
        original,
        None,
        302,
        "Found",
        {},
        "http://cdn.test/video.mp4",
    )
    assert downgrade is not None
    assert downgrade.get_header("Cookie") is None


@pytest.mark.parametrize(
    ("url", "content_type"),
    [
        ("https://cdn.test/challenge.mp4", "text/html"),
        ("https://cdn.test/master.m3u8", "application/vnd.apple.mpegurl"),
        ("https://cdn.test/manifest.mpd", "application/dash+xml"),
    ],
)
def test_fetch_to_file_rejects_non_video_and_playlist_payloads(
    tmp_path: Path,
    url: str,
    content_type: str,
) -> None:
    response = FakeResponse(
        b"not-video",
        status=200,
        headers={"Content-Type": content_type, "Content-Length": "9"},
    )

    with patch("src.downloaders.http.urlopen", return_value=response):
        with pytest.raises(DownloadError, match="non-video|playlist|manifest"):
            HttpAssetDownloader().fetch_to_file(url, tmp_path / "video.part")
