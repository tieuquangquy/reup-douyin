from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import (
    ExternalPublicationStatus,
    PlatformAccountStatus,
    PublishAccountAssignmentStatus,
    PublishAttemptStatus,
    PublishDraftStatus,
    PublishReconciliationStatus,
    PublishRoutingRuleStatus,
    PublishTargetPlatform,
)


class PlatformAccount(BaseModel):
    __tablename__ = "platform_accounts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "platform",
            "external_account_id",
            name="uq_platform_accounts_workspace_platform_external",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform: Mapped[PublishTargetPlatform] = mapped_column(
        Enum(PublishTargetPlatform, name="publish_target_platform"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    token_reference: Mapped[str | None] = mapped_column(String(240))
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    is_on_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    hold_reason: Mapped[str | None] = mapped_column(Text)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    allowed_niches_json: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[PlatformAccountStatus] = mapped_column(
        Enum(PlatformAccountStatus, name="platform_account_status"),
        default=PlatformAccountStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    routing_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    publish_attempts: Mapped[list["PublishAttempt"]] = relationship(back_populates="platform_account")
    platform_publications: Mapped[list["PlatformPublication"]] = relationship(back_populates="platform_account")


class PlatformCredential(BaseModel):
    """Encrypted provider credential referenced by a platform account.

    The ciphertext is never exposed through the public account schema. Keeping
    this boundary separate from ``PlatformAccount`` allows a future vault/KMS
    adapter to replace local database envelopes without changing publish flows.
    """

    __tablename__ = "platform_credentials"
    __table_args__ = (
        UniqueConstraint(
            "platform_account_id",
            "provider",
            "credential_kind",
            name="uq_platform_credentials_account_provider_kind",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform_account_id: Mapped[UUID] = mapped_column(ForeignKey("platform_accounts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    credential_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(40), default="envelope-v1", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)


class PlatformIntegrationConfiguration(BaseModel):
    """Workspace-scoped provider application configuration.

    Provider secrets stay envelope-encrypted and are never included in public
    schemas. This boundary can later be backed by KMS without changing OAuth
    or web contracts.
    """

    __tablename__ = "platform_integration_configurations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider",
            name="uq_platform_integration_configs_workspace_provider",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    app_id: Mapped[str] = mapped_column(String(240), nullable=False)
    encrypted_app_secret: Mapped[str] = mapped_column(Text, nullable=False)
    oauth_redirect_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    graph_api_version: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_scopes_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    configured_by_subject: Mapped[str] = mapped_column(String(240), nullable=False)
    key_version: Mapped[str] = mapped_column(String(40), default="envelope-v1", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class PlatformOAuthSession(BaseModel):
    """Short-lived durable OAuth state; provider tokens remain encrypted."""

    __tablename__ = "platform_oauth_sessions"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_by_subject: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    requested_scopes_json: Mapped[list | None] = mapped_column(JSONB)
    granted_scopes_json: Mapped[list | None] = mapped_column(JSONB)
    encrypted_payload: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(120), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)


class PublishDraft(BaseModel):
    __tablename__ = "publish_drafts"
    __table_args__ = (
        UniqueConstraint(
            "source_video_id",
            "target_platform",
            "version",
            name="uq_publish_drafts_video_platform_version",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    render_output_id: Mapped[UUID | None] = mapped_column(ForeignKey("render_outputs.id"), index=True)
    target_platform: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    platform_account_ref: Mapped[str | None] = mapped_column(String(180), index=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[PublishDraftStatus] = mapped_column(
        Enum(PublishDraftStatus, name="publish_draft_status"),
        default=PublishDraftStatus.DRAFT,
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(240))
    caption: Mapped[str | None] = mapped_column(Text)
    cta_text: Mapped[str | None] = mapped_column(Text)
    language_code: Mapped[str | None] = mapped_column(String(16), default="vi")
    hashtags_json: Mapped[list | None] = mapped_column(JSONB)
    caption_draft_json: Mapped[dict | None] = mapped_column(JSONB)
    cta_draft_json: Mapped[dict | None] = mapped_column(JSONB)
    schedule_json: Mapped[dict | None] = mapped_column(JSONB)
    planned_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str | None] = mapped_column(String(80))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_source: Mapped[str | None] = mapped_column(String(120))
    platform_payload_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    platform_notes: Mapped[str | None] = mapped_column(Text)
    scheduling_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    canonical_publish_attempt_id: Mapped[UUID | None] = mapped_column(ForeignKey("publish_attempts.id"), index=True)
    latest_publish_attempt_id: Mapped[UUID | None] = mapped_column(ForeignKey("publish_attempts.id"), index=True)
    current_publication_status: Mapped[ExternalPublicationStatus] = mapped_column(
        Enum(ExternalPublicationStatus, name="external_publication_status"),
        default=ExternalPublicationStatus.UNKNOWN,
        nullable=False,
        index=True,
    )
    current_external_publish_id: Mapped[str | None] = mapped_column(String(240), index=True)
    current_external_permalink: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_publish_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publication_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    assigned_platform_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("platform_accounts.id"), index=True)
    assignment_status: Mapped[PublishAccountAssignmentStatus] = mapped_column(
        Enum(PublishAccountAssignmentStatus, name="publish_account_assignment_status"),
        default=PublishAccountAssignmentStatus.UNASSIGNED,
        nullable=False,
        index=True,
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    assigned_reason: Mapped[str | None] = mapped_column(Text)
    assigned_by: Mapped[str | None] = mapped_column(String(120))
    assignment_metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="publish_drafts")
    render_output: Mapped["RenderOutput | None"] = relationship(back_populates="publish_drafts")
    assigned_platform_account: Mapped["PlatformAccount | None"] = relationship(foreign_keys=[assigned_platform_account_id])
    publish_attempts: Mapped[list["PublishAttempt"]] = relationship(
        back_populates="publish_draft",
        foreign_keys="PublishAttempt.publish_draft_id",
    )
    platform_publications: Mapped[list["PlatformPublication"]] = relationship(back_populates="publish_draft")
    canonical_publish_attempt: Mapped["PublishAttempt | None"] = relationship(
        foreign_keys=[canonical_publish_attempt_id],
        post_update=True,
    )
    latest_publish_attempt: Mapped["PublishAttempt | None"] = relationship(
        foreign_keys=[latest_publish_attempt_id],
        post_update=True,
    )


class PublishAttempt(BaseModel):
    __tablename__ = "publish_attempts"
    __table_args__ = (
        UniqueConstraint(
            "publish_draft_id",
            "attempt_number",
            name="uq_publish_attempts_draft_attempt_number",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    publish_draft_id: Mapped[UUID] = mapped_column(ForeignKey("publish_drafts.id"), index=True)
    platform: Mapped[PublishTargetPlatform] = mapped_column(
        Enum(PublishTargetPlatform, name="publish_target_platform"),
        nullable=False,
        index=True,
    )
    platform_account_id: Mapped[UUID] = mapped_column(ForeignKey("platform_accounts.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PublishAttemptStatus] = mapped_column(
        Enum(PublishAttemptStatus, name="publish_attempt_status"),
        default=PublishAttemptStatus.QUEUED,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_publish_id: Mapped[str | None] = mapped_column(String(240), index=True)
    external_media_id: Mapped[str | None] = mapped_column(String(240), index=True)
    external_reel_id: Mapped[str | None] = mapped_column(String(240), index=True)
    external_permalink: Mapped[str | None] = mapped_column(Text)
    external_status: Mapped[ExternalPublicationStatus] = mapped_column(
        Enum(ExternalPublicationStatus, name="external_publication_status"),
        default=ExternalPublicationStatus.UNKNOWN,
        nullable=False,
        index=True,
    )
    reconciliation_status: Mapped[PublishReconciliationStatus] = mapped_column(
        Enum(PublishReconciliationStatus, name="publish_reconciliation_status"),
        default=PublishReconciliationStatus.NOT_REQUIRED,
        nullable=False,
        index=True,
    )
    reconciliation_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    request_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    response_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    warning_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(120), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    last_status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_sync_result_json: Mapped[dict | None] = mapped_column(JSONB)
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    publish_draft: Mapped[PublishDraft] = relationship(back_populates="publish_attempts", foreign_keys=[publish_draft_id])
    platform_account: Mapped[PlatformAccount] = relationship(back_populates="publish_attempts")
    platform_publications: Mapped[list["PlatformPublication"]] = relationship(
        back_populates="publish_attempt"
    )


class PlatformPublication(BaseModel):
    """One externally observable post, independent from the attempt that created it.

    A draft can accidentally produce more than one real post after retries. Every external
    post is retained here; ``is_canonical`` identifies the publication selected by the
    draft lifecycle without erasing duplicate-publication evidence.
    """

    __tablename__ = "platform_publications"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "platform",
            "platform_account_id",
            "external_publish_id",
            name="uq_platform_publications_external_identity",
        ),
        UniqueConstraint(
            "publish_attempt_id",
            name="uq_platform_publications_publish_attempt",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    publish_draft_id: Mapped[UUID | None] = mapped_column(ForeignKey("publish_drafts.id"), index=True)
    source_video_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_videos.id"), index=True)
    render_output_id: Mapped[UUID | None] = mapped_column(ForeignKey("render_outputs.id"), index=True)
    platform: Mapped[PublishTargetPlatform] = mapped_column(
        Enum(PublishTargetPlatform, name="publish_target_platform"),
        nullable=False,
        index=True,
    )
    platform_account_id: Mapped[UUID] = mapped_column(ForeignKey("platform_accounts.id"), index=True)
    publish_attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("publish_attempts.id"),
        index=True,
    )
    external_publish_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    external_media_id: Mapped[str | None] = mapped_column(String(240), index=True)
    external_reel_id: Mapped[str | None] = mapped_column(String(240), index=True)
    external_permalink: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ExternalPublicationStatus] = mapped_column(
        Enum(ExternalPublicationStatus, name="external_publication_status"),
        default=ExternalPublicationStatus.UNKNOWN,
        nullable=False,
        index=True,
    )
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    content_fingerprint_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    origin: Mapped[str] = mapped_column(
        String(40), default="CONNECTOR_PUBLISH", nullable=False, index=True
    )
    native_product_placement_status: Mapped[str] = mapped_column(
        String(80), default="NOT_EVALUATED", nullable=False, index=True
    )
    affiliate_comment_status: Mapped[str] = mapped_column(
        String(80), default="NOT_PLANNED", nullable=False, index=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    publish_draft: Mapped[PublishDraft | None] = relationship(back_populates="platform_publications")
    platform_account: Mapped[PlatformAccount] = relationship(back_populates="platform_publications")
    publish_attempt: Mapped[PublishAttempt | None] = relationship(back_populates="platform_publications")
    metric_snapshots: Mapped[list["PublicationMetricSnapshot"]] = relationship(
        back_populates="platform_publication"
    )
    content_classifications: Mapped[list["ContentClassification"]] = relationship(
        back_populates="platform_publication",
        cascade="all, delete-orphan",
    )


class PublishRoutingRule(BaseModel):
    __tablename__ = "publish_routing_rules"
    __table_args__ = (
        UniqueConstraint("workspace_id", "rule_name", name="uq_publish_routing_rules_workspace_name"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform: Mapped[PublishTargetPlatform] = mapped_column(
        Enum(PublishTargetPlatform, name="publish_target_platform"),
        nullable=False,
        index=True,
    )
    rule_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[PublishRoutingRuleStatus] = mapped_column(
        Enum(PublishRoutingRuleStatus, name="publish_routing_rule_status"),
        default=PublishRoutingRuleStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    match_json: Mapped[dict | None] = mapped_column(JSONB)
    action_json: Mapped[dict | None] = mapped_column(JSONB)
    fallback_behavior: Mapped[str | None] = mapped_column(String(80))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
