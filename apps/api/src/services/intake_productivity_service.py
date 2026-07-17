from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.bootstrap import ensure_default_workspace
from src.enums import CrawlSessionStatus
from src.models.ingestion import CrawlSession, SourceProfile
from src.models.intake import IntakeSavedPreset
from src.schemas.intake import (
    IntakeBootstrapResponse,
    IntakeLatestSuccessShortcutResponse,
    IntakeRecentProfileResponse,
    IntakeSavedPresetCreateRequest,
    IntakeSavedPresetListResponse,
    IntakeSavedPresetResponse,
    IntakeSavedPresetUpdateRequest,
)


class IntakeProductivityError(ValueError):
    pass


class IntakeProductivityService:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_workspace_id(self, workspace_id: UUID | None) -> UUID:
        if workspace_id is not None:
            return workspace_id
        return ensure_default_workspace(self.db).id

    def bootstrap(self, *, workspace_id: UUID | None) -> IntakeBootstrapResponse:
        resolved_workspace_id = self._resolve_workspace_id(workspace_id)
        return IntakeBootstrapResponse(
            workspace_id=resolved_workspace_id,
            saved_presets=self.list_saved_presets(workspace_id=resolved_workspace_id).presets,
            recent_profiles=self.list_recent_profiles(workspace_id=resolved_workspace_id),
            latest_success_shortcuts=self.list_latest_success_shortcuts(workspace_id=resolved_workspace_id),
        )

    def list_saved_presets(self, *, workspace_id: UUID | None) -> IntakeSavedPresetListResponse:
        resolved_workspace_id = self._resolve_workspace_id(workspace_id)
        presets = list(
            self.db.scalars(
                select(IntakeSavedPreset)
                .where(IntakeSavedPreset.workspace_id == resolved_workspace_id)
                .order_by(IntakeSavedPreset.updated_at.desc())
            )
        )
        return IntakeSavedPresetListResponse(presets=[self._to_saved_preset_response(item) for item in presets])

    def create_saved_preset(self, request: IntakeSavedPresetCreateRequest) -> IntakeSavedPresetResponse:
        workspace_id = self._resolve_workspace_id(request.workspace_id)
        existing = self.db.scalar(
            select(IntakeSavedPreset).where(
                IntakeSavedPreset.workspace_id == workspace_id,
                IntakeSavedPreset.name == request.name.strip(),
            )
        )
        if existing is not None:
            raise IntakeProductivityError("Saved intake preset name already exists in this workspace")

        preset = IntakeSavedPreset(
            workspace_id=workspace_id,
            name=request.name.strip(),
            profile_url=request.profile_url.strip(),
            preset_name=request.preset_name,
            filter_config_json=request.filter_config.model_dump(exclude_none=True) if request.filter_config else {},
            force_live_refresh=request.force_live_refresh,
            douyin_account_connection_id=request.douyin_account_connection_id,
            notes=request.notes,
        )
        self.db.add(preset)
        self.db.commit()
        self.db.refresh(preset)
        return self._to_saved_preset_response(preset)

    def update_saved_preset(self, preset_id: UUID, request: IntakeSavedPresetUpdateRequest) -> IntakeSavedPresetResponse:
        preset = self.db.get(IntakeSavedPreset, preset_id)
        if preset is None:
            raise IntakeProductivityError("Saved intake preset not found")

        if request.name is not None:
            next_name = request.name.strip()
            duplicate = self.db.scalar(
                select(IntakeSavedPreset).where(
                    IntakeSavedPreset.workspace_id == preset.workspace_id,
                    IntakeSavedPreset.name == next_name,
                    IntakeSavedPreset.id != preset.id,
                )
            )
            if duplicate is not None:
                raise IntakeProductivityError("Saved intake preset name already exists in this workspace")
            preset.name = next_name
        if request.profile_url is not None:
            preset.profile_url = request.profile_url.strip()
        if request.preset_name is not None:
            preset.preset_name = request.preset_name
        if request.filter_config is not None:
            preset.filter_config_json = request.filter_config.model_dump(exclude_none=True)
        if request.force_live_refresh is not None:
            preset.force_live_refresh = request.force_live_refresh
        if request.notes is not None:
            preset.notes = request.notes
        if request.douyin_account_connection_id is not None:
            preset.douyin_account_connection_id = request.douyin_account_connection_id

        self.db.commit()
        self.db.refresh(preset)
        return self._to_saved_preset_response(preset)

    def delete_saved_preset(self, preset_id: UUID) -> None:
        preset = self.db.get(IntakeSavedPreset, preset_id)
        if preset is None:
            raise IntakeProductivityError("Saved intake preset not found")
        self.db.delete(preset)
        self.db.commit()

    def list_recent_profiles(self, *, workspace_id: UUID, limit: int = 8) -> list[IntakeRecentProfileResponse]:
        profiles = list(
            self.db.scalars(
                select(SourceProfile)
                .where(SourceProfile.workspace_id == workspace_id)
                .order_by(SourceProfile.updated_at.desc())
                .limit(limit)
            )
        )
        return [
            IntakeRecentProfileResponse(
                source_profile_id=item.id,
                profile_url=item.profile_url,
                normalized_profile_identifier=item.source_profile_external_id,
                display_name=item.display_name,
                last_crawled_at=item.last_crawled_at,
            )
            for item in profiles
        ]

    def list_latest_success_shortcuts(self, *, workspace_id: UUID, limit: int = 8) -> list[IntakeLatestSuccessShortcutResponse]:
        sessions = list(
            self.db.scalars(
                select(CrawlSession)
                .where(
                    CrawlSession.workspace_id == workspace_id,
                    CrawlSession.status == CrawlSessionStatus.COMPLETED,
                )
                .order_by(CrawlSession.finished_at.desc().nullslast(), CrawlSession.updated_at.desc())
                .limit(limit)
            )
        )
        return [
            IntakeLatestSuccessShortcutResponse(
                crawl_session_id=item.id,
                source_profile_id=item.source_profile_id,
                submitted_profile_url=item.submitted_profile_url,
                normalized_profile_identifier=item.normalized_profile_identifier,
                finished_at=item.finished_at,
                videos_discovered_count=item.videos_discovered_count,
            )
            for item in sessions
        ]

    def _to_saved_preset_response(self, preset: IntakeSavedPreset) -> IntakeSavedPresetResponse:
        return IntakeSavedPresetResponse(
            id=preset.id,
            workspace_id=preset.workspace_id,
            name=preset.name,
            profile_url=preset.profile_url,
            preset_name=preset.preset_name,
            filter_config=preset.filter_config_json or {},
            force_live_refresh=preset.force_live_refresh,
            douyin_account_connection_id=preset.douyin_account_connection_id,
            notes=preset.notes,
            created_at=preset.created_at,
            updated_at=preset.updated_at,
        )
