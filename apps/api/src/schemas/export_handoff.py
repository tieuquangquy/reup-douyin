from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.enums import ExportPackageStatus, PublishHandoffStatus, PublishTargetPlatform, ReupQueueBatchAction, ReupQueueStatus


class BatchItemResultResponse(BaseModel):
    item_id: UUID
    result: str
    status: ReupQueueStatus | None = None
    reason_code: str | None = None
    message: str | None = None
    export_package_id: UUID | None = None
    publish_handoff_id: UUID | None = None


class BatchOperationResponse(BaseModel):
    requested_count: int
    succeeded_count: int
    skipped_count: int
    failed_count: int
    export_package_id: UUID | None = None
    publish_handoff_id: UUID | None = None
    results: list[BatchItemResultResponse]


class ExportPackageCreateRequest(BaseModel):
    item_ids: list[UUID] = Field(min_length=1, max_length=500)
    label: str | None = Field(default=None, max_length=180)
    operator_note: str | None = Field(default=None, max_length=1000)


class ExportPackageItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    export_package_id: UUID
    reup_queue_item_id: UUID
    source_video_id: UUID
    video_candidate_id: UUID
    render_output_id: UUID | None
    publish_draft_id: UUID | None
    item_status: str
    manifest_json: dict | None
    diagnostics_json: dict | None
    created_at: datetime
    updated_at: datetime


class ExportPackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    status: ExportPackageStatus
    label: str | None
    operator_note: str | None
    item_count: int
    manifest_json: dict | None
    diagnostics_json: dict | None
    ready_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None
    items: list[ExportPackageItemResponse] = Field(default_factory=list)
    publish_handoff_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ExportPackageListResponse(BaseModel):
    items: list[ExportPackageResponse]
    total_count: int
    limit: int
    offset: int


class PublishHandoffCreateRequest(BaseModel):
    export_package_id: UUID
    target_platform: PublishTargetPlatform = PublishTargetPlatform.FACEBOOK_REELS
    operator_note: str | None = Field(default=None, max_length=1000)


class PublishHandoffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    export_package_id: UUID
    target_platform: PublishTargetPlatform
    status: PublishHandoffStatus
    operator_note: str | None
    payload_json: dict | None
    diagnostics_json: dict | None
    ready_at: datetime | None
    accepted_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublishHandoffListResponse(BaseModel):
    items: list[PublishHandoffResponse]
    total_count: int
    limit: int
    offset: int


class ReupQueueBatchActionRequest(BaseModel):
    action: ReupQueueBatchAction
    item_ids: list[UUID] = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=1000)
    target_platform: PublishTargetPlatform | None = None
    # START_AUTO_PIPELINE batch: auto_to_tts (default) | auto_to_render
    # SET_AUTOMATION batch: manual | auto_to_tts | auto_to_render (required)
    pipeline_mode: str | None = Field(default=None, max_length=40)
