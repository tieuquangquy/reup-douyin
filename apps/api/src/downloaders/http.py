from __future__ import annotations

from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.downloaders.base import AssetDownloader, DownloadedObject
from src.downloaders.errors import DownloadError, DownloadErrorCode


class HttpAssetDownloader(AssetDownloader):
    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> DownloadedObject:
        if not url:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Missing source URL")
        try:
            request = Request(url, headers={"User-Agent": "reup-douyin-local/0.1"})
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read()
                mime_type = response.headers.get_content_type()
        except URLError as exc:
            raise DownloadError(DownloadErrorCode.DOWNLOAD_FAILED, f"Download failed: {exc}") from exc
        filename = _filename_from_url(url)
        return DownloadedObject(content=content, mime_type=mime_type, filename=filename)


def _filename_from_url(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    return path.rsplit("/", 1)[-1] or None

