from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.enums import (
    CandidateStatus,
    CapturedItemStatus,
    ExportPackageStatus,
    PublishAttemptStatus,
    PublishDraftStatus,
    PublishHandoffStatus,
    ReupQueueMediaPrepStatus,
    ReupQueueStatus,
)
from src.models.capture_inbox import CapturedItem, CaptureSession
from src.models.export_handoff import ExportPackage, PublishHandoff
from src.models.publish import PublishAttempt, PublishDraft
from src.models.reup_queue import ReupQueueItem
from src.models.review import VideoCandidate
from src.schemas.pipeline_dashboard import (
    PipelineDashboardActivityItem,
    PipelineDashboardAttentionItem,
    PipelineDashboardMetric,
    PipelineDashboardQuickLink,
    PipelineDashboardResponse,
    PipelineDashboardSeverity,
    PipelineDashboardStage,
    PipelineDashboardStatus,
    PipelineStageKey,
)

CAPTURE_HREF = "/ops/extensions/douyin/capture-inbox"
REVIEW_HREF = "/selection/review-board"
REUP_QUEUE_HREF = "/selection/reup-queue"
EXPORT_HREF = "/publishing/export-packages"
HANDOFF_HREF = "/publishing/publish-handoffs"
PUBLISH_DRAFTS_HREF = "/publishing/drafts"
PUBLISH_HEALTH_HREF = "/ops/publish-health"
PUBLISH_ATTEMPTS_HREF = "/ops/publish-attempts"
RECONCILIATION_HREF = "/ops/reconciliation"


@dataclass(frozen=True)
class PipelineCounts:
    captures_last_24h: int
    capture_ready_items: int
    capture_failed_items: int
    review_backlog: int
    approved_candidates: int
    approved_not_queued: int
    queue_active: int
    queue_waiting_media: int
    queue_waiting_metadata: int
    queue_failed: int
    queue_ready_to_export: int
    export_ready: int
    export_failed: int
    handoff_ready: int
    handoff_failed: int
    publish_ready: int
    publish_scheduled: int
    publish_active_drafts: int
    publish_published: int
    publish_failed_drafts: int
    publish_active_attempts: int
    publish_failed_attempts: int
    publish_needs_reconciliation: int


class PipelineDashboardService:
    def __init__(self, db: Session, *, workspace_id: UUID):
        self.db = db
        self.workspace_id = workspace_id

    def snapshot(self) -> PipelineDashboardResponse:
        generated_at = datetime.now(UTC)
        counts = self._counts(generated_at)
        stages = self._stages(counts)
        attention_items = self._attention_items(counts)
        overall_status = self._overall_status(stages, attention_items)
        return PipelineDashboardResponse(
            generated_at=generated_at,
            overall_status=overall_status,
            headline=self._headline(overall_status, counts, attention_items),
            summary_metrics=self._summary_metrics(counts, attention_items),
            stages=stages,
            attention_items=attention_items,
            recent_activity=self._recent_activity(),
            quick_links=self._quick_links(),
        )

    def _counts(self, now: datetime) -> PipelineCounts:
        last_24h = now - timedelta(hours=24)
        approved_not_queued_stmt = (
            select(func.count())
            .select_from(VideoCandidate)
            .outerjoin(ReupQueueItem, ReupQueueItem.video_candidate_id == VideoCandidate.id)
            .where(VideoCandidate.workspace_id == self.workspace_id, VideoCandidate.status == CandidateStatus.APPROVED, ReupQueueItem.id.is_(None))
        )
        return PipelineCounts(
            captures_last_24h=self._count(CaptureSession, CaptureSession.created_at >= last_24h),
            capture_ready_items=self._count(CapturedItem, CapturedItem.status.in_([CapturedItemStatus.READY, CapturedItemStatus.PREVIEW_MISSING])),
            capture_failed_items=self._count(CapturedItem, CapturedItem.status == CapturedItemStatus.FAILED),
            review_backlog=self._count(VideoCandidate, VideoCandidate.status.in_([CandidateStatus.SHORTLISTED, CandidateStatus.IN_REVIEW])),
            approved_candidates=self._count(VideoCandidate, VideoCandidate.status == CandidateStatus.APPROVED),
            approved_not_queued=int(self.db.scalar(approved_not_queued_stmt) or 0),
            queue_active=self._count(ReupQueueItem, ReupQueueItem.status.in_([
                ReupQueueStatus.READY_FOR_PROCESSING,
                ReupQueueStatus.WAITING_FOR_MEDIA,
                ReupQueueStatus.WAITING_FOR_METADATA,
                ReupQueueStatus.PROCESSING,
                ReupQueueStatus.READY_TO_EXPORT,
                ReupQueueStatus.EXPORT_PACKAGE_CREATED,
                ReupQueueStatus.READY_TO_PUBLISH,
                ReupQueueStatus.PUBLISH_HANDOFF_CREATED,
                ReupQueueStatus.FAILED_NEEDS_ATTENTION,
            ])),
            queue_waiting_media=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.WAITING_FOR_MEDIA),
            queue_waiting_metadata=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.WAITING_FOR_METADATA),
            queue_failed=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.FAILED_NEEDS_ATTENTION),
            queue_ready_to_export=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.READY_TO_EXPORT, ReupQueueItem.media_prep_status == ReupQueueMediaPrepStatus.READY_FOR_EXPORT),
            export_ready=self._count(ExportPackage, ExportPackage.status == ExportPackageStatus.READY_FOR_HANDOFF),
            export_failed=self._count(ExportPackage, ExportPackage.status == ExportPackageStatus.FAILED_NEEDS_ATTENTION),
            handoff_ready=self._count(PublishHandoff, PublishHandoff.status == PublishHandoffStatus.READY_FOR_OPERATOR),
            handoff_failed=self._count(PublishHandoff, PublishHandoff.status == PublishHandoffStatus.FAILED_NEEDS_ATTENTION),
            publish_ready=self._count(PublishDraft, PublishDraft.status == PublishDraftStatus.READY),
            publish_scheduled=self._count(PublishDraft, PublishDraft.status == PublishDraftStatus.SCHEDULED),
            publish_active_drafts=self._count(PublishDraft, PublishDraft.status.in_([PublishDraftStatus.READY, PublishDraftStatus.SCHEDULED, PublishDraftStatus.PUBLISHING])),
            publish_published=self._count(PublishDraft, PublishDraft.status == PublishDraftStatus.PUBLISHED),
            publish_failed_drafts=self._count(PublishDraft, PublishDraft.status.in_([PublishDraftStatus.FAILED, PublishDraftStatus.NEEDS_ATTENTION])),
            publish_active_attempts=self._count(PublishAttempt, PublishAttempt.status.in_([
                PublishAttemptStatus.QUEUED,
                PublishAttemptStatus.RUNNING,
                PublishAttemptStatus.UPLOADING,
                PublishAttemptStatus.PUBLISHING,
                PublishAttemptStatus.AWAITING_PLATFORM_CONFIRMATION,
                PublishAttemptStatus.RECONCILING,
            ])),
            publish_failed_attempts=self._count(PublishAttempt, PublishAttempt.status == PublishAttemptStatus.FAILED),
            publish_needs_reconciliation=self._count(PublishAttempt, PublishAttempt.status == PublishAttemptStatus.NEEDS_RECONCILIATION),
        )

    def _stages(self, counts: PipelineCounts) -> list[PipelineDashboardStage]:
        return [
            PipelineDashboardStage(
                key="capture",
                label="Capture",
                description="Staged Douyin captures waiting for promotion into canonical review.",
                status=self._stage_status(blocked=counts.capture_failed_items, attention=counts.capture_ready_items, active=counts.captures_last_24h),
                primary_count=counts.capture_ready_items,
                primary_label="Ready to promote",
                secondary_count=counts.captures_last_24h,
                secondary_label="Captures in last 24h",
                metrics=[self._metric("failed", "Failed items", counts.capture_failed_items)],
                attention_count=counts.capture_failed_items + counts.capture_ready_items,
                href=CAPTURE_HREF,
                next_action="Promote ready capture items or inspect failures before review.",
            ),
            PipelineDashboardStage(
                key="review",
                label="Review",
                description="Canonical review board for shortlisted candidates and approvals.",
                status=self._stage_status(attention=counts.review_backlog + counts.approved_not_queued, active=counts.approved_candidates),
                primary_count=counts.review_backlog,
                primary_label="Review backlog",
                secondary_count=counts.approved_not_queued,
                secondary_label="Approved not queued",
                metrics=[self._metric("approved", "Approved candidates", counts.approved_candidates)],
                attention_count=counts.review_backlog + counts.approved_not_queued,
                href=REVIEW_HREF,
                next_action="Review shortlisted candidates and send approved work to Reup Queue.",
            ),
            PipelineDashboardStage(
                key="reup_queue",
                label="Reup Queue",
                description="Downstream processing workspace for approved content.",
                status=self._stage_status(blocked=counts.queue_failed, attention=counts.queue_waiting_media + counts.queue_waiting_metadata, active=counts.queue_active),
                primary_count=counts.queue_active,
                primary_label="Active queue items",
                secondary_count=counts.queue_ready_to_export,
                secondary_label="Ready to export",
                metrics=[self._metric("waiting_media", "Waiting for media", counts.queue_waiting_media), self._metric("failed", "Needs retry", counts.queue_failed)],
                attention_count=counts.queue_failed + counts.queue_waiting_media + counts.queue_waiting_metadata,
                href=REUP_QUEUE_HREF,
                next_action="Clear failed or waiting items, then package ready-to-export work.",
            ),
            PipelineDashboardStage(
                key="export_package",
                label="Export Package",
                description="Operator-created packages ready to become publish handoffs.",
                status=self._stage_status(blocked=counts.export_failed, attention=counts.export_ready),
                primary_count=counts.queue_ready_to_export,
                primary_label="Queue ready to package",
                secondary_count=counts.export_ready,
                secondary_label="Packages ready for handoff",
                metrics=[self._metric("failed", "Failed packages", counts.export_failed)],
                attention_count=counts.export_failed + counts.export_ready,
                href=EXPORT_HREF,
                next_action="Create or inspect export packages and prepare handoff payloads.",
            ),
            PipelineDashboardStage(
                key="publish_handoff",
                label="Publish Handoff",
                description="Manual downstream handoff artifacts for external publishing.",
                status=self._stage_status(blocked=counts.handoff_failed, attention=counts.handoff_ready),
                primary_count=counts.handoff_ready,
                primary_label="Ready for operator",
                secondary_count=counts.handoff_failed,
                secondary_label="Failed handoffs",
                metrics=[],
                attention_count=counts.handoff_ready + counts.handoff_failed,
                href=HANDOFF_HREF,
                next_action="Accept ready handoffs and continue manual platform-safe publishing.",
            ),
            PipelineDashboardStage(
                key="publish_progress",
                label="Publish progress",
                description="Draft, attempt, publication, and reconciliation state after handoff.",
                status=self._stage_status(blocked=counts.publish_failed_drafts + counts.publish_failed_attempts + counts.publish_needs_reconciliation, attention=counts.publish_ready, active=counts.publish_active_drafts + counts.publish_active_attempts),
                primary_count=counts.publish_active_drafts,
                primary_label="Active drafts",
                secondary_count=counts.publish_published,
                secondary_label="Published drafts",
                metrics=[self._metric("active_attempts", "Active attempts", counts.publish_active_attempts), self._metric("needs_reconciliation", "Needs reconciliation", counts.publish_needs_reconciliation)],
                attention_count=counts.publish_failed_drafts + counts.publish_failed_attempts + counts.publish_needs_reconciliation,
                href=PUBLISH_DRAFTS_HREF,
                next_action="Monitor active drafts, resolve failed attempts, and reconcile uncertain publications.",
            ),
        ]

    def _attention_items(self, counts: PipelineCounts) -> list[PipelineDashboardAttentionItem]:
        items: list[PipelineDashboardAttentionItem] = []
        self._add_attention(items, counts.capture_failed_items, "critical", "capture", "Capture failures", "Captured items failed normalization or enrichment.", CAPTURE_HREF, "Open Capture Inbox and inspect failed item reasons.")
        self._add_attention(items, counts.capture_ready_items, "warning", "capture", "Capture items ready", "Captured items are staged and ready to promote to Review Board.", CAPTURE_HREF, "Promote ready items when they are suitable for review.")
        self._add_attention(items, counts.review_backlog, "warning", "review", "Review backlog", "Shortlisted or in-review candidates need operator decisions.", REVIEW_HREF, "Approve, reject, or archive candidates on Review Board.")
        self._add_attention(items, counts.approved_not_queued, "warning", "review", "Approved candidates not queued", "Approved candidates have not been sent to Reup Queue yet.", REVIEW_HREF, "Send approved candidates to Reup Queue.")
        self._add_attention(items, counts.queue_failed, "critical", "reup_queue", "Queue failures", "Reup Queue items are failed or blocked and need retry, resume, or cancellation.", REUP_QUEUE_HREF, "Inspect blocked reasons and retry safe items.")
        self._add_attention(items, counts.queue_waiting_media + counts.queue_waiting_metadata, "warning", "reup_queue", "Queue waiting work", "Queue items are waiting for media or metadata preparation.", REUP_QUEUE_HREF, "Confirm media and metadata readiness.")
        self._add_attention(items, counts.queue_ready_to_export, "info", "export_package", "Ready to export", "Queue items are ready to be grouped into an Export Package.", REUP_QUEUE_HREF, "Create an Export Package for ready items.")
        self._add_attention(items, counts.export_ready, "warning", "export_package", "Packages ready for handoff", "Export Packages are ready to become Publish Handoffs.", EXPORT_HREF, "Create Publish Handoffs for ready packages.")
        self._add_attention(items, counts.handoff_ready, "warning", "publish_handoff", "Handoffs ready for operator", "Publish Handoffs are waiting for manual downstream handling.", HANDOFF_HREF, "Open handoffs and continue platform-safe publishing.")
        self._add_attention(items, counts.publish_failed_drafts + counts.publish_failed_attempts + counts.publish_needs_reconciliation, "critical", "publish_progress", "Publish issues", "Publish drafts or attempts failed or need reconciliation.", PUBLISH_ATTEMPTS_HREF, "Inspect failed attempts and run reconciliation where needed.")
        return items

    def _recent_activity(self) -> list[PipelineDashboardActivityItem]:
        activity: list[PipelineDashboardActivityItem] = []
        for session in self.db.scalars(select(CaptureSession).where(CaptureSession.workspace_id == self.workspace_id).order_by(CaptureSession.updated_at.desc()).limit(3)):
            activity.append(self._activity(f"capture-{session.id}", "capture", "Capture session updated", f"Status {session.status}; {session.ready_item_count} ready item(s).", session.updated_at, CAPTURE_HREF))
        for item in self.db.scalars(select(ReupQueueItem).where(ReupQueueItem.workspace_id == self.workspace_id).order_by(ReupQueueItem.updated_at.desc()).limit(3)):
            activity.append(self._activity(f"queue-{item.id}", "reup_queue", "Queue item updated", f"Status {item.status}; media prep {item.media_prep_status}.", item.updated_at, REUP_QUEUE_HREF))
        for package in self.db.scalars(select(ExportPackage).where(ExportPackage.workspace_id == self.workspace_id).order_by(ExportPackage.updated_at.desc()).limit(2)):
            activity.append(self._activity(f"export-{package.id}", "export_package", "Export Package updated", f"Status {package.status}; {package.item_count} item(s).", package.updated_at, f"{EXPORT_HREF}/{package.id}"))
        for handoff in self.db.scalars(select(PublishHandoff).where(PublishHandoff.workspace_id == self.workspace_id).order_by(PublishHandoff.updated_at.desc()).limit(2)):
            activity.append(self._activity(f"handoff-{handoff.id}", "publish_handoff", "Publish Handoff updated", f"Status {handoff.status}; target {handoff.target_platform}.", handoff.updated_at, f"{HANDOFF_HREF}/{handoff.id}"))
        for draft in self.db.scalars(select(PublishDraft).where(PublishDraft.workspace_id == self.workspace_id).order_by(PublishDraft.updated_at.desc()).limit(3)):
            activity.append(self._activity(f"publish-{draft.id}", "publish_progress", "Publish draft updated", f"Status {draft.status}; platform {draft.target_platform}.", draft.updated_at, f"{PUBLISH_DRAFTS_HREF}/{draft.id}"))
        return sorted(activity, key=lambda item: item.occurred_at, reverse=True)[:10]

    def _count(self, model: Any, *criteria: Any) -> int:
        stmt = select(func.count()).select_from(model)
        if hasattr(model, "workspace_id"):
            stmt = stmt.where(model.workspace_id == self.workspace_id)
        for criterion in criteria:
            stmt = stmt.where(criterion)
        return int(self.db.scalar(stmt) or 0)

    def _stage_status(self, *, blocked: int = 0, attention: int = 0, active: int = 0) -> PipelineDashboardStatus:
        if blocked > 0:
            return "blocked"
        if attention > 0:
            return "needs_attention"
        if active > 0:
            return "in_progress"
        return "quiet"

    def _overall_status(self, stages: list[PipelineDashboardStage], attention_items: list[PipelineDashboardAttentionItem]) -> PipelineDashboardStatus:
        if any(item.severity == "critical" for item in attention_items):
            return "blocked"
        if any(stage.status == "needs_attention" for stage in stages):
            return "needs_attention"
        if any(stage.status == "in_progress" for stage in stages):
            return "in_progress"
        if all(stage.status == "quiet" for stage in stages):
            return "quiet"
        return "healthy"

    def _headline(self, status: PipelineDashboardStatus, counts: PipelineCounts, attention_items: list[PipelineDashboardAttentionItem]) -> str:
        if status == "blocked":
            return f"{len([item for item in attention_items if item.severity == 'critical'])} critical pipeline issue(s) need operator attention."
        if status == "needs_attention":
            return f"{len(attention_items)} attention item(s) are shaping today’s operator queue."
        if status == "in_progress":
            return f"Pipeline is moving with {counts.queue_active + counts.publish_active_drafts} active downstream item(s)."
        if status == "quiet":
            return "Pipeline is quiet; start with Capture Inbox when new source content is ready."
        return "Pipeline is healthy."

    def _summary_metrics(self, counts: PipelineCounts, attention_items: list[PipelineDashboardAttentionItem]) -> list[PipelineDashboardMetric]:
        return [
            self._metric("captures_last_24h", "Captures 24h", counts.captures_last_24h),
            self._metric("active_backlog", "Active backlog", counts.review_backlog + counts.queue_active + counts.publish_active_drafts),
            self._metric("attention_items", "Attention items", len(attention_items)),
            self._metric("export_ready", "Export ready", counts.queue_ready_to_export + counts.export_ready),
            self._metric("handoff_ready", "Handoff ready", counts.handoff_ready),
            self._metric("published", "Published", counts.publish_published),
        ]

    def _quick_links(self) -> list[PipelineDashboardQuickLink]:
        return [
            PipelineDashboardQuickLink(label="Capture Inbox", href=CAPTURE_HREF, description="Stage and promote captured Douyin items.", stage_key="capture"),
            PipelineDashboardQuickLink(label="Review Board", href=REVIEW_HREF, description="Approve or reject candidates.", stage_key="review"),
            PipelineDashboardQuickLink(label="Reup Queue", href=REUP_QUEUE_HREF, description="Prepare approved content for export.", stage_key="reup_queue"),
            PipelineDashboardQuickLink(label="Export Packages", href=EXPORT_HREF, description="Inspect package readiness.", stage_key="export_package"),
            PipelineDashboardQuickLink(label="Publish Handoffs", href=HANDOFF_HREF, description="Continue manual publish handoff.", stage_key="publish_handoff"),
            PipelineDashboardQuickLink(label="Publish Drafts", href=PUBLISH_DRAFTS_HREF, description="Track draft readiness and publishing.", stage_key="publish_progress"),
            PipelineDashboardQuickLink(label="Publish Health", href=PUBLISH_HEALTH_HREF, description="Review downstream publish health.", stage_key="publish_progress"),
            PipelineDashboardQuickLink(label="Publish Attempts", href=PUBLISH_ATTEMPTS_HREF, description="Inspect attempt failures and progress.", stage_key="publish_progress"),
            PipelineDashboardQuickLink(label="Reconciliation", href=RECONCILIATION_HREF, description="Resolve uncertain publication outcomes.", stage_key="publish_progress"),
        ]

    def _add_attention(
        self,
        items: list[PipelineDashboardAttentionItem],
        count: int,
        severity: PipelineDashboardSeverity,
        stage_key: PipelineStageKey,
        title: str,
        detail: str,
        href: str,
        recommended_action: str,
    ) -> None:
        if count <= 0:
            return
        items.append(PipelineDashboardAttentionItem(id=f"{stage_key}-{title.lower().replace(' ', '-')}", severity=severity, stage_key=stage_key, title=title, detail=detail, count=count, href=href, recommended_action=recommended_action))

    def _activity(self, item_id: str, stage_key: PipelineStageKey, title: str, detail: str, occurred_at: datetime, href: str) -> PipelineDashboardActivityItem:
        return PipelineDashboardActivityItem(id=item_id, stage_key=stage_key, title=title, detail=detail, occurred_at=occurred_at, href=href)

    def _metric(self, key: str, label: str, value: int, detail: str | None = None) -> PipelineDashboardMetric:
        return PipelineDashboardMetric(key=key, label=label, value=value, detail=detail)
