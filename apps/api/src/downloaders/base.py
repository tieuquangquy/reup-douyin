from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


@dataclass(frozen=True)
class DownloadedObject:
    content: bytes | None = None
    mime_type: str | None = None
    filename: str | None = None
    local_path: str | None = None
    size_bytes: int | None = None
    cleanup_local_path: bool = False

    @property
    def has_payload(self) -> bool:
        if self.content:
            return True
        if self.local_path:
            path = Path(self.local_path)
            return path.is_file() and path.stat().st_size > 0
        return False


class AssetDownloader(ABC):
    @abstractmethod
    def fetch(self, url: str) -> DownloadedObject:
        raise NotImplementedError

    def fetch_to_file(
        self,
        url: str,
        destination: str | Path,
        *,
        resume: bool = True,
        on_progress: Callable[[int, int | None], None] | None = None,
        headers: Mapping[str, str] | None = None,
        proxy_url: str | None = None,
    ) -> DownloadedObject:
        """Optional bounded-memory transfer API used by large media downloads."""
        raise NotImplementedError
