from __future__ import annotations

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
    JobStatus,
    JobType,
)
from src.models.capture_inbox import CapturedItem, CaptureSession
from src.models.export_handoff import ExportPackage, PublishHandoff
from src.models.publish import PublishAttempt, PublishDraft
from src.models.jobs import Job
from src.models.media import RenderOutput
from src.models.reup_queue import ReupQueueItem
from src.models.review import VideoCandidate
from src.schemas.pipeline_dashboard import (
    PipelineDashboardActivityItem,
    PipelineDashboardAttentionItem,
    PipelineDashboardMetric,
    PipelineDashboardOutputQaSummary,
    PipelineDashboardQuickLink,
    PipelineDashboardResponse,
    PipelineDashboardSeverity,
    PipelineDashboardStage,
    PipelineDashboardStatus,
    PipelineStageKey,
)
from src.services.pipeline_stage_snapshot import (
    CAPTURE_HREF,
    EXPORT_HREF,
    HANDOFF_HREF,
    JOB_STAGE_BY_TYPE,
    OUTPUT_REVIEW_HREF,
    PUBLISH_DRAFTS_HREF,
    REVIEW_HREF,
    REUP_QUEUE_HREF,
    OutputQaCounts,
    PipelineCounts,
    build_pipeline_stage_snapshots,
)


class PipelineDashboardService:
    def __init__(self, db: Session, *, workspace_id: UUID):
        self.db = db
        self.workspace_id = workspace_id

    def snapshot(self) -> PipelineDashboardResponse:
        generated_at = datetime.now(UTC)
        counts = self._counts(generated_at)
        job_matrix = self._job_matrix()
        output_qa = self._output_qa_counts()
        stages = self._stages(counts, job_matrix=job_matrix, output_qa=output_qa)
        attention_items = self._attention_items(counts, stages=stages)
        overall_status = self._overall_status(stages, attention_items)
        return PipelineDashboardResponse(
            generated_at=generated_at,
            overall_status=overall_status,
            headline=self._headline(overall_status, counts, attention_items),
            summary_metrics=self._summary_metrics(counts, attention_items, stages=stages),
            stages=stages,
            attention_items=attention_items,
            output_qa_summary=PipelineDashboardOutputQaSummary(
                passed=output_qa.passed,
                warned=output_qa.warned,
                failed=output_qa.failed,
                ungraded=output_qa.ungraded,
                total=output_qa.total,
            ),
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
            captures_last_24h=self._count(CapturedItem, CapturedItem.created_at >= last_24h),
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
            queue_waiting_processing=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.READY_FOR_PROCESSING),
            queue_processing=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.PROCESSING),
            queue_waiting_media=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.WAITING_FOR_MEDIA),
            queue_waiting_metadata=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.WAITING_FOR_METADATA),
            queue_failed=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.FAILED_NEEDS_ATTENTION),
            queue_ready_to_export=self._count(ReupQueueItem, ReupQueueItem.status == ReupQueueStatus.READY_TO_EXPORT, ReupQueueItem.media_prep_status == ReupQueueMediaPrepStatus.READY_FOR_EXPORT),
            export_draft=self._count(ExportPackage, ExportPackage.status == ExportPackageStatus.DRAFT),
            export_ready=self._count(ExportPackage, ExportPackage.status == ExportPackageStatus.READY_FOR_HANDOFF),
            export_failed=self._count(ExportPackage, ExportPackage.status == ExportPackageStatus.FAILED_NEEDS_ATTENTION),
            handoff_draft=self._count(PublishHandoff, PublishHandoff.status == PublishHandoffStatus.DRAFT),
            handoff_ready=self._count(PublishHandoff, PublishHandoff.status == PublishHandoffStatus.READY_FOR_OPERATOR),
            handoff_failed=self._count(PublishHandoff, PublishHandoff.status == PublishHandoffStatus.FAILED_NEEDS_ATTENTION),
            publish_draft=self._count(PublishDraft, PublishDraft.status == PublishDraftStatus.DRAFT),
            publish_ready=self._count(PublishDraft, PublishDraft.status == PublishDraftStatus.READY),
            publish_scheduled=self._count(PublishDraft, PublishDraft.status == PublishDraftStatus.SCHEDULED),
            publish_publishing=self._count(PublishDraft, PublishDraft.status == PublishDraftStatus.PUBLISHING),
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

    def _stages(
        self,
        counts: PipelineCounts,
        *,
        job_matrix: dict[tuple[JobType, JobStatus], int] | None = None,
        output_qa: OutputQaCounts | None = None,
    ) -> list[PipelineDashboardStage]:
        return build_pipeline_stage_snapshots(counts, job_matrix=job_matrix, output_qa=output_qa)

    def _attention_items(
        self,
        counts: PipelineCounts,
        *,
        stages: list[PipelineDashboardStage] | None = None,
    ) -> list[PipelineDashboardAttentionItem]:
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
        self._add_attention(items, counts.publish_failed_drafts + counts.publish_failed_attempts + counts.publish_needs_reconciliation, "critical", "draft", "Publish issues", "Publish drafts or attempts failed or need reconciliation.", PUBLISH_DRAFTS_HREF, "Inspect failed drafts and reconcile uncertain attempts where needed.")
        if stages:
            for stage in stages:
                if stage.key not in {spec.key for spec in JOB_STAGE_BY_TYPE.values()}:
                    continue
                self._add_attention(items, stage.failed_count, "critical", stage.key, f"{stage.label} failures", f"{stage.failed_count} durable job(s) failed or can be retried.", stage.href, f"Inspect and retry safe {stage.label.lower()} work.")
                self._add_attention(items, stage.review_count, "warning", stage.key, f"{stage.label} review waiting", f"{stage.review_count} durable job(s) reached a manual checkpoint.", stage.href, f"Review {stage.label.lower()} results.")
            output_stage = next((stage for stage in stages if stage.key == "output_review"), None)
            if output_stage:
                self._add_attention(items, output_stage.failed_count, "critical", "output_review", "Output QA failures", "Automated render QA found defects that need correction.", OUTPUT_REVIEW_HREF, "Open Output Review and fix failed renders.")
                self._add_attention(items, output_stage.review_count, "warning", "output_review", "Outputs need review", "Warnings or ungraded renders need operator eyes.", OUTPUT_REVIEW_HREF, "Review flagged outputs.")
        return items

    def _recent_activity(self) -> list[PipelineDashboardActivityItem]:
        activity: list[PipelineDashboardActivityItem] = []
        for session in self.db.scalars(select(CaptureSession).where(CaptureSession.workspace_id == self.workspace_id).order_by(CaptureSession.updated_at.desc()).limit(3)):
            activity.append(self._activity(f"capture-{session.id}", "capture", "Capture session updated", f"Status {session.status}; {session.ready_item_count} ready item(s).", session.updated_at, CAPTURE_HREF))
        for item in self.db.scalars(select(ReupQueueItem).where(ReupQueueItem.workspace_id == self.workspace_id).order_by(ReupQueueItem.updated_at.desc()).limit(3)):
            activity.append(self._activity(f"queue-{item.id}", "reup_queue", "Queue item updated", f"Status {item.status}; media prep {item.media_prep_status}.", item.updated_at, REUP_QUEUE_HREF))
        for job in self.db.scalars(select(Job).where(Job.workspace_id == self.workspace_id, Job.job_type.in_(list(JOB_STAGE_BY_TYPE))).order_by(Job.updated_at.desc()).limit(6)):
            spec = JOB_STAGE_BY_TYPE.get(job.job_type)
            if spec is None:
                continue
            activity.append(self._activity(f"job-{job.id}", spec.key, f"{spec.label} job updated", f"Status {job.status}; progress {job.progress_percent}%.", job.updated_at, spec.href))
        for output in self.db.scalars(select(RenderOutput).where(RenderOutput.workspace_id == self.workspace_id).order_by(RenderOutput.updated_at.desc()).limit(3)):
            activity.append(self._activity(f"output-{output.id}", "output_review", "Render output updated", f"Status {output.status}.", output.updated_at, OUTPUT_REVIEW_HREF))
        for package in self.db.scalars(select(ExportPackage).where(ExportPackage.workspace_id == self.workspace_id).order_by(ExportPackage.updated_at.desc()).limit(2)):
            activity.append(self._activity(f"export-{package.id}", "export_package", "Export Package updated", f"Status {package.status}; {package.item_count} item(s).", package.updated_at, f"{EXPORT_HREF}/{package.id}"))
        for handoff in self.db.scalars(select(PublishHandoff).where(PublishHandoff.workspace_id == self.workspace_id).order_by(PublishHandoff.updated_at.desc()).limit(2)):
            activity.append(self._activity(f"handoff-{handoff.id}", "publish_handoff", "Publish Handoff updated", f"Status {handoff.status}; target {handoff.target_platform}.", handoff.updated_at, f"{HANDOFF_HREF}/{handoff.id}"))
        for draft in self.db.scalars(select(PublishDraft).where(PublishDraft.workspace_id == self.workspace_id).order_by(PublishDraft.updated_at.desc()).limit(3)):
            activity.append(self._activity(f"publish-{draft.id}", "draft", "Publish draft updated", f"Status {draft.status}; platform {draft.target_platform}.", draft.updated_at, f"{PUBLISH_DRAFTS_HREF}/{draft.id}"))
        return sorted(activity, key=lambda item: item.occurred_at, reverse=True)[:10]

    def _job_matrix(self) -> dict[tuple[JobType, JobStatus], int]:
        rows = self.db.execute(
            select(Job.job_type, Job.status, func.count())
            .where(Job.workspace_id == self.workspace_id, Job.job_type.in_(list(JOB_STAGE_BY_TYPE)))
            .group_by(Job.job_type, Job.status)
        ).all()
        return {(job_type, status): int(count) for job_type, status, count in rows}

    def _output_qa_counts(self) -> OutputQaCounts:
        counts = {"fail": 0, "warn": 0, "pass": 0, "ungraded": 0}
        oldest_failed_at: datetime | None = None
        oldest_review_at: datetime | None = None
        for item in self.db.scalars(
            select(ReupQueueItem).where(
                ReupQueueItem.workspace_id == self.workspace_id,
                ReupQueueItem.render_output_id.is_not(None),
            )
        ):
            status = self._render_qa_status(item.metadata_json)
            counts[status] += 1
            if status == "fail" and (oldest_failed_at is None or item.updated_at < oldest_failed_at):
                oldest_failed_at = item.updated_at
            elif status in {"warn", "ungraded"} and (oldest_review_at is None or item.updated_at < oldest_review_at):
                oldest_review_at = item.updated_at
        return OutputQaCounts(
            failed=counts["fail"],
            warned=counts["warn"],
            passed=counts["pass"],
            ungraded=counts["ungraded"],
            oldest_failed_at=oldest_failed_at,
            oldest_review_at=oldest_review_at,
        )

    def _count(self, model: Any, *criteria: Any) -> int:
        stmt = select(func.count()).select_from(model)
        if hasattr(model, "workspace_id"):
            stmt = stmt.where(model.workspace_id == self.workspace_id)
        for criterion in criteria:
            stmt = stmt.where(criterion)
        return int(self.db.scalar(stmt) or 0)

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
            affected = sum(item.count for item in attention_items if item.severity == "critical")
            return f"{affected} affected record(s) are blocked and need operator attention."
        if status == "needs_attention":
            affected = sum(item.count for item in attention_items)
            return f"{affected} affected record(s) are shaping today's operator queue."
        if status == "in_progress":
            return f"Pipeline is moving with {counts.queue_active + counts.publish_active_drafts} active downstream item(s)."
        if status == "quiet":
            return "Pipeline is quiet; start with Capture Inbox when new source content is ready."
        return "Pipeline is healthy."

    def _summary_metrics(
        self,
        counts: PipelineCounts,
        attention_items: list[PipelineDashboardAttentionItem],
        *,
        stages: list[PipelineDashboardStage] | None = None,
    ) -> list[PipelineDashboardMetric]:
        stage_rows = stages or self._stages(counts)
        active_backlog = sum(
            stage.waiting_count + stage.running_count + stage.review_count + stage.failed_count
            for stage in stage_rows
        )
        running = sum(stage.running_count for stage in stage_rows)
        ready_downstream = sum(
            stage.ready_count
            for stage in stage_rows
            if stage.key in {"output_review", "export_package", "publish_handoff"}
        )
        return [
            self._metric("captures_last_24h", "Captured items 24h", counts.captures_last_24h),
            self._metric("active_backlog", "Active backlog", active_backlog, "Waiting, running, manual-review, or failed records across the stage map."),
            self._metric("attention_items", "Attention workload", sum(item.count for item in attention_items), "Affected records represented by attention categories."),
            self._metric("running", "Running", running, "Durable records currently running."),
            self._metric("ready_downstream", "Ready downstream", ready_downstream, "QA-passed outputs, export packages, or handoffs ready to continue."),
            self._metric("export_ready", "Export ready", counts.queue_ready_to_export + counts.export_ready),
            self._metric("handoff_ready", "Handoff ready", counts.handoff_ready),
        ]

    def _quick_links(self) -> list[PipelineDashboardQuickLink]:
        return [
            PipelineDashboardQuickLink(label="Capture Inbox", href=CAPTURE_HREF, description="Stage and promote captured Douyin items.", stage_key="capture"),
            PipelineDashboardQuickLink(label="Review Board", href=REVIEW_HREF, description="Approve or reject candidates.", stage_key="review"),
            PipelineDashboardQuickLink(label="Reup Queue", href=REUP_QUEUE_HREF, description="Prepare approved content for export.", stage_key="reup_queue"),
            PipelineDashboardQuickLink(label="Output Review", href=OUTPUT_REVIEW_HREF, description="Review final render QA.", stage_key="output_review"),
            PipelineDashboardQuickLink(label="Export Packages", href=EXPORT_HREF, description="Inspect package readiness.", stage_key="export_package"),
            PipelineDashboardQuickLink(label="Publish Handoffs", href=HANDOFF_HREF, description="Continue manual publish handoff.", stage_key="publish_handoff"),
            PipelineDashboardQuickLink(label="Publish Drafts", href=PUBLISH_DRAFTS_HREF, description="Track draft readiness and publishing.", stage_key="draft"),
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

    @staticmethod
    def _render_qa_status(metadata: dict | None) -> str:
        render_qa = (metadata or {}).get("render_qa")
        if not isinstance(render_qa, dict):
            return "ungraded"
        status = render_qa.get("status")
        return status if status in {"pass", "warn", "fail"} else "ungraded"
