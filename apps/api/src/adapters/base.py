from abc import ABC, abstractmethod

from src.adapters.types import NormalizedProfileIdentity, SourceFetchResult
from src.enums import SourcePlatformEnum


class SourceAdapter(ABC):
    source_platform: SourcePlatformEnum

    @abstractmethod
    def validate_profile_url(self, profile_url: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def normalize_profile_identity(self, profile_url: str) -> NormalizedProfileIdentity:
        raise NotImplementedError

    @abstractmethod
    def fetch_profile(self, profile_url: str) -> SourceFetchResult:
        raise NotImplementedError

