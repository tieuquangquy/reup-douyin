from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadedObject:
    content: bytes
    mime_type: str | None = None
    filename: str | None = None


class AssetDownloader(ABC):
    @abstractmethod
    def fetch(self, url: str) -> DownloadedObject:
        raise NotImplementedError

