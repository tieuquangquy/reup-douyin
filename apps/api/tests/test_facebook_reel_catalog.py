from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.core.settings import Settings
from src.enums import PlatformAccountStatus, PublishTargetPlatform
from src.models.publish import PlatformAccount, PlatformPublication
from src.publish.services.facebook_reel_catalog_service import FacebookReelCatalogService
from src.publish.services.platform_publication_service import PlatformPublicationService
from src.schemas.publish import FacebookReelDiscoveryImportRequest


class _CatalogSession:
    def __init__(self, account: PlatformAccount):
        self.account = account

    def get(self, model, object_id):
        return self.account if object_id == self.account.id else None

    def scalars(self, _statement):
        return []


class _ImportSession:
    def __init__(self, account: PlatformAccount):
        self.account = account
        self.publications: list[PlatformPublication] = []

    def get(self, model, object_id):
        if model is PlatformAccount and object_id == self.account.id:
            return self.account
        if model is PlatformPublication:
            return next((item for item in self.publications if item.id == object_id), None)
        return None

    def scalar(self, _statement):
        return self.publications[0] if self.publications else None

    def add(self, row):
        if isinstance(row, PlatformPublication):
            self.publications.append(row)

    def commit(self):
        return None

    def rollback(self):
        return None

    def refresh(self, _row):
        return None


class _RacingImportSession(_ImportSession):
    def __init__(self, account: PlatformAccount):
        super().__init__(account)
        self.raise_duplicate_once = True

    def commit(self):
        if self.raise_duplicate_once:
            self.raise_duplicate_once = False
            raise IntegrityError("insert platform_publications", {}, Exception("duplicate"))
        return None


class _Transport:
    def fetch_reels(self, **kwargs):
        assert kwargs["page_id"] == "page-123"
        assert kwargs["limit"] == 25
        assert kwargs["after"] is None
        return {
            "data": [
                {
                    "id": "reel-1",
                    "description": "A discovered Reel",
                    "created_time": "2026-07-31T03:00:00+0000",
                    "permalink_url": "/reel/reel-1",
                    "thumbnails": {"data": [{"uri": "https://cdn.example/reel-1.jpg"}]},
                }
            ],
            "paging": {"cursors": {"after": "cursor-2"}, "next": "https://graph.example/next"},
        }


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused",
        facebook_graph_api_version="v26.0",
    )


def test_discovery_normalizes_reels_without_exposing_token(monkeypatch):
    account = PlatformAccount(
        id=uuid4(),
        workspace_id=uuid4(),
        platform=PublishTargetPlatform.FACEBOOK_REELS,
        display_name="Page",
        external_account_id="page-123",
        token_reference="FACEBOOK_PAGE_TOKEN",
        status=PlatformAccountStatus.ACTIVE,
        metadata_json={"graph_api_version": "v26.0"},
    )
    monkeypatch.setenv("FACEBOOK_PAGE_TOKEN", "server-only-token")
    result = FacebookReelCatalogService(
        _CatalogSession(account),  # type: ignore[arg-type]
        settings=_settings(),
        transport=_Transport(),
    ).discover(account.id, workspace_id=account.workspace_id)

    assert result["next_cursor"] == "cursor-2"
    assert result["items"] == [
        {
            "reel_id": "reel-1",
            "description": "A discovered Reel",
            "created_time": datetime(2026, 7, 31, 3, 0, tzinfo=UTC),
            "permalink_url": "https://www.facebook.com/reel/reel-1",
            "thumbnail_url": "https://cdn.example/reel-1.jpg",
            "already_imported": False,
            "platform_publication_id": None,
        }
    ]
    assert "server-only-token" not in repr(result)


def test_discovered_reel_can_exist_without_publish_draft_or_attempt():
    account = PlatformAccount(
        id=uuid4(),
        workspace_id=uuid4(),
        platform=PublishTargetPlatform.FACEBOOK_REELS,
        display_name="Page",
        external_account_id="page-123",
        status=PlatformAccountStatus.ACTIVE,
    )
    db = _ImportSession(account)
    publication = PlatformPublicationService(db).import_discovered_facebook_reel(  # type: ignore[arg-type]
        FacebookReelDiscoveryImportRequest(
            platform_account_id=account.id,
            reel_id="reel-1",
            description="Historical Reel",
            created_time=datetime(2026, 7, 31, 3, 0, tzinfo=UTC),
            permalink_url="/reel/reel-1",
            thumbnail_url="https://cdn.example/reel-1.jpg",
        ),
        workspace_id=account.workspace_id,
    )

    assert publication.publish_draft_id is None
    assert publication.publish_attempt_id is None
    assert publication.origin == "FACEBOOK_DISCOVERY"
    assert publication.external_reel_id == "reel-1"
    assert publication.external_permalink == "https://www.facebook.com/reel/reel-1"


def test_discovered_reel_import_is_idempotent_for_operator_retry():
    account = PlatformAccount(
        id=uuid4(),
        workspace_id=uuid4(),
        platform=PublishTargetPlatform.FACEBOOK_REELS,
        display_name="Page",
        external_account_id="page-123",
        status=PlatformAccountStatus.ACTIVE,
    )
    db = _ImportSession(account)
    request = FacebookReelDiscoveryImportRequest(
        platform_account_id=account.id,
        reel_id="reel-1",
        permalink_url="/reel/reel-1",
    )
    service = PlatformPublicationService(db)  # type: ignore[arg-type]

    first = service.import_discovered_facebook_reel(request, workspace_id=account.workspace_id)
    second = service.import_discovered_facebook_reel(request, workspace_id=account.workspace_id)

    assert first is second
    assert len(db.publications) == 1


def test_discovered_reel_import_recovers_duplicate_insert_race():
    account = PlatformAccount(
        id=uuid4(),
        workspace_id=uuid4(),
        platform=PublishTargetPlatform.FACEBOOK_REELS,
        display_name="Page",
        external_account_id="page-123",
        status=PlatformAccountStatus.ACTIVE,
    )
    db = _RacingImportSession(account)
    publication = PlatformPublicationService(db).import_discovered_facebook_reel(  # type: ignore[arg-type]
        FacebookReelDiscoveryImportRequest(
            platform_account_id=account.id,
            reel_id="reel-1",
            permalink_url="/reel/reel-1",
        ),
        workspace_id=account.workspace_id,
    )

    assert publication.external_reel_id == "reel-1"
    assert len(db.publications) == 1


def test_discovered_reel_import_rejects_protocol_relative_external_url():
    with pytest.raises(ValidationError, match="permalink_url must belong to facebook.com or fb.watch"):
        FacebookReelDiscoveryImportRequest(
            platform_account_id=uuid4(),
            reel_id="reel-1",
            permalink_url="//example.com/reel/reel-1",
        )
