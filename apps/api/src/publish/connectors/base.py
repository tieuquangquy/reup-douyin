from __future__ import annotations

from abc import ABC, abstractmethod

from src.publish.types import PlatformAccountConfig, PublishRequest, PublishResult, PublishStatusSyncResult


class PublishConnectorError(RuntimeError):
    def __init__(self, code: str, message: str, response_summary: dict | None = None):
        super().__init__(message)
        self.code = code
        self.response_summary = response_summary or {}


class PublishConnector(ABC):
    @abstractmethod
    def validate_account(self, account: PlatformAccountConfig) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def publish(self, request: PublishRequest) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    def refresh_status(
        self,
        *,
        account: PlatformAccountConfig,
        external_publish_id: str | None,
        external_media_id: str | None = None,
        external_reel_id: str | None = None,
    ) -> PublishStatusSyncResult:
        raise NotImplementedError

