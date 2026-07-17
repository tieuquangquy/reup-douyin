from src.downloaders.base import AssetDownloader, DownloadedObject
from src.downloaders.errors import DownloadError, DownloadErrorCode


class MappingAssetDownloader(AssetDownloader):
    def __init__(self, objects: dict[str, DownloadedObject]):
        self.objects = objects

    def fetch(self, url: str) -> DownloadedObject:
        try:
            return self.objects[url]
        except KeyError as exc:
            raise DownloadError(DownloadErrorCode.DOWNLOAD_FAILED, f"No mock object for URL: {url}") from exc

