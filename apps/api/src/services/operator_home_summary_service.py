from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.enums import CandidateStatus, JobStatus, JobType, OcrObjectStatus, RenderOutputStatus
from src.models.artifacts import OcrTextObject
from src.models.ingestion import SourceVideo
from src.models.jobs import Job
from src.models.media import RenderOutput
from src.models.reup_queue import ReupQueueItem
from src.models.review import VideoCandidate
from src.schemas.douyin_extension import DouyinExtensionStatusResponse
from src.schemas.operator_home import (
    OperatorHomeActiveWork,
    OperatorHomeAttentionBreakdown,
    OperatorHomeCheckpoint,
    OperatorHomeMetric,
    OperatorHomeOverall,
    OperatorHomeOutputQaSummary,
    OperatorHomePriorityItem,
    OperatorHomeReadinessItem,
    OperatorHomeRecentOutput,
    OperatorHomeStage,
    OperatorHomeStageKey,
    OperatorHomeSummaryResponse,
)
from src.schemas.pipeline_dashboard import PipelineDashboardAttentionItem, PipelineDashboardStage, PipelineDashboardStatus
from src.services.pipeline_dashboard_service import PipelineDashboardService
from src.services.pipeline_stage_snapshot import JOB_STAGE_BY_TYPE, PRODUCTION_STAGE_SPECS, OutputQaCounts


@dataclass(frozen=True)
class OperatorHomeAggregate:
    needs_attention: int = 0
    in_progress: int = 0
    awaiting_review: int = 0
    ready_downstream: int = 0
    critical_count: int = 0


MANUAL_REVIEW_STAGE_KEYS: frozenset[OperatorHomeStageKey] = frozenset(
    {"review", "translate", "ocr", "output_review"}
)


def oldest_known_at(*values: datetime | None) -> datetime | None:
    known = [value for value in values if value is not None]
    return min(known) if known else None


def operator_home_status(aggregate: OperatorHomeAggregate) -> PipelineDashboardStatus:
    if aggregate.critical_count > 0:
        return "blocked"
    if aggregate.needs_attention > 0:
        return "needs_attention"
    if aggregate.in_progress > 0:
        return "in_progress"
    if aggregate.ready_downstream > 0:
        return "healthy"
    return "quiet"


def build_decision_metrics(aggregate: OperatorHomeAggregate) -> list[OperatorHomeMetric]:
    return [
        OperatorHomeMetric(
            key="needs_attention",
            label="Needs attention",
            value=aggregate.needs_attention,
            detail="Critical and warning items that need an operator decision.",
            tone="critical" if aggregate.critical_count > 0 else "warning" if aggregate.needs_attention > 0 else "good",
        ),
        OperatorHomeMetric(
            key="in_progress",
            label="In progress",
            value=aggregate.in_progress,
            detail="Durable production jobs currently running.",
            tone="good" if aggregate.in_progress > 0 else "neutral",
            href="/selection/reup-queue",
        ),
        OperatorHomeMetric(
            key="awaiting_review",
            label="Awaiting review",
            value=aggregate.awaiting_review,
            detail="Manual checkpoints across review, OCR, output QA, and publishing.",
            tone="warning" if aggregate.awaiting_review > 0 else "good",
        ),
        OperatorHomeMetric(
            key="ready_downstream",
            label="Ready downstream",
            value=aggregate.ready_downstream,
            detail="Passed outputs, export packages, and handoffs ready to continue.",
            tone="good" if aggregate.ready_downstream > 0 else "neutral",
            href="/production/output-review",
        ),
    ]


def build_output_qa_summary(counts: OutputQaCounts) -> OperatorHomeOutputQaSummary:
    return OperatorHomeOutputQaSummary(
        passed=counts.passed,
        warned=counts.warned,
        failed=counts.failed,
        ungraded=counts.ungraded,
        total=counts.total,
    )


def build_attention_breakdown(
    priorities: Iterable[OperatorHomePriorityItem],
    *,
    manual_review_count: int,
) -> OperatorHomeAttentionBreakdown:
    items = tuple(priorities)
    critical = sum(item.count for item in items if item.severity == "critical")
    warning = sum(
        item.count
        for item in items
        if item.severity == "warning" and item.stage_key not in MANUAL_REVIEW_STAGE_KEYS
    )
    manual_review = max(0, manual_review_count)
    return OperatorHomeAttentionBreakdown(
        critical=critical,
        warning=warning,
        manual_review=manual_review,
        total=critical + warning + manual_review,
    )


class OperatorHomeSummaryService:
    def __init__(self, db: Session, *, workspace_id: UUID):
        self.db = db
        self.workspace_id = workspace_id

    def snapshot(self, *, extension: DouyinExtensionStatusResponse | None = None) -> OperatorHomeSummaryResponse:
        generated_at = datetime.now(UTC)
        pipeline = PipelineDashboardService(self.db, workspace_id=self.workspace_id).snapshot()
        job_matrix = self._job_matrix()
        job_oldest_matrix = self._job_oldest_matrix()
        output_qa = self._output_qa_counts()
        stages = self._home_stages(pipeline.stages)
        priorities = self._priority_items(pipeline.attention_items)
        checkpoints = self._manual_checkpoints(pipeline.stages, job_matrix, output_qa, job_oldest_matrix)
        manual_review_count = (
            sum(item.count for item in checkpoints if item.key != "output_review")
            + output_qa.warned
            + output_qa.ungraded
        )

        critical_count = sum(item.count for item in priorities if item.severity == "critical")
        aggregate = OperatorHomeAggregate(
            needs_attention=sum(item.count for item in priorities),
            in_progress=sum(
                self._job_count(job_matrix, spec.job_type, {JobStatus.RUNNING})
                for spec in PRODUCTION_STAGE_SPECS
            ),
            awaiting_review=sum(item.count for item in checkpoints),
            ready_downstream=output_qa.passed
            + self._stage_ready(stages, "export_package")
            + self._stage_ready(stages, "publish_handoff"),
            critical_count=critical_count,
        )
        status = operator_home_status(aggregate)

        return OperatorHomeSummaryResponse(
            overall=OperatorHomeOverall(
                status=status,
                headline=self._headline(status, aggregate),
                critical_count=critical_count,
                running_count=aggregate.in_progress,
                generated_at=generated_at,
            ),
            decision_metrics=build_decision_metrics(aggregate),
            priority_items=priorities[:5],
            stages=stages,
            active_work=self._active_work(),
            manual_checkpoints=checkpoints,
            output_qa_summary=build_output_qa_summary(output_qa),
            attention_breakdown=build_attention_breakdown(
                priorities,
                manual_review_count=manual_review_count,
            ),
            recent_outputs=self._recent_outputs(),
            system_readiness=self._system_readiness(job_matrix, extension),
            partial_errors=[],
        )

    def _job_matrix(self) -> dict[tuple[JobType, JobStatus], int]:
        rows = self.db.execute(
            select(Job.job_type, Job.status, func.count())
            .where(Job.workspace_id == self.workspace_id)
            .group_by(Job.job_type, Job.status)
        ).all()
        return {(job_type, status): int(count) for job_type, status, count in rows}

    def _job_oldest_matrix(self) -> dict[tuple[JobType, JobStatus], datetime]:
        rows = self.db.execute(
            select(Job.job_type, Job.status, func.min(Job.updated_at))
            .where(Job.workspace_id == self.workspace_id)
            .group_by(Job.job_type, Job.status)
        ).all()
        return {(job_type, status): oldest_at for job_type, status, oldest_at in rows if oldest_at is not None}

    def _job_count(
        self,
        matrix: dict[tuple[JobType, JobStatus], int],
        job_type: JobType,
        statuses: Iterable[JobStatus],
    ) -> int:
        return sum(matrix.get((job_type, status), 0) for status in statuses)

    def _job_oldest(
        self,
        matrix: dict[tuple[JobType, JobStatus], datetime],
        job_type: JobType,
        statuses: Iterable[JobStatus],
    ) -> datetime | None:
        return oldest_known_at(*(matrix.get((job_type, status)) for status in statuses))

    def _home_stages(
        self,
        pipeline_stages: list[PipelineDashboardStage],
    ) -> list[OperatorHomeStage]:
        return [
            OperatorHomeStage(
                key=cast(OperatorHomeStageKey, stage.key),
                label=stage.label,
                status=stage.status,
                waiting_count=stage.waiting_count,
                running_count=stage.running_count,
                failed_count=stage.failed_count,
                review_count=stage.review_count,
                ready_count=stage.ready_count,
                href=stage.href,
            )
            for stage in pipeline_stages
        ]

    def _output_qa_counts(self) -> OutputQaCounts:
        items = list(
            self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.workspace_id == self.workspace_id,
                    ReupQueueItem.render_output_id.is_not(None),
                )
            )
        )
        counts = {"fail": 0, "warn": 0, "pass": 0, "ungraded": 0}
        oldest_failed_at: datetime | None = None
        oldest_review_at: datetime | None = None
        for item in items:
            status = self._render_qa_status(item.metadata_json)
            counts[status] += 1
            if status == "fail":
                oldest_failed_at = oldest_known_at(oldest_failed_at, item.updated_at)
            elif status in {"warn", "ungraded"}:
                oldest_review_at = oldest_known_at(oldest_review_at, item.updated_at)
        return OutputQaCounts(
            failed=counts["fail"],
            warned=counts["warn"],
            passed=counts["pass"],
            ungraded=counts["ungraded"],
            oldest_failed_at=oldest_failed_at,
            oldest_review_at=oldest_review_at,
        )

    def _priority_items(
        self,
        pipeline_items: list[PipelineDashboardAttentionItem],
    ) -> list[OperatorHomePriorityItem]:
        priorities = [
            OperatorHomePriorityItem(
                id=item.id,
                severity=item.severity,
                stage_key=self._home_key_for_pipeline(item.stage_key),
                title=item.title,
                detail=item.detail,
                count=item.count,
                href=self._safe_href(self._home_key_for_pipeline(item.stage_key), item.href),
                recommended_action=item.recommended_action,
            )
            for item in pipeline_items
            if item.severity in {"critical", "warning"}
        ]
        return sorted(priorities, key=lambda item: (0 if item.severity == "critical" else 1, -item.count))

    def _manual_checkpoints(
        self,
        pipeline_stages: list[PipelineDashboardStage],
        matrix: dict[tuple[JobType, JobStatus], int],
        output_qa: OutputQaCounts,
        job_oldest_matrix: dict[tuple[JobType, JobStatus], datetime],
    ) -> list[OperatorHomeCheckpoint]:
        review_stage = next(stage for stage in pipeline_stages if stage.key == "review")
        translate_review = self._job_count(matrix, JobType.BUILD_TRANSLATION_DRAFT, {JobStatus.WAITING_FOR_REVIEW})
        ocr_review = self._count(OcrTextObject, OcrTextObject.status == OcrObjectStatus.NEEDS_REVIEW)
        output_review = output_qa.failed + output_qa.warned + output_qa.ungraded
        candidate_oldest = self.db.scalar(
            select(func.min(VideoCandidate.updated_at)).where(
                VideoCandidate.workspace_id == self.workspace_id,
                VideoCandidate.status.in_([CandidateStatus.SHORTLISTED, CandidateStatus.IN_REVIEW]),
            )
        )
        translate_oldest = self._job_oldest(
            job_oldest_matrix,
            JobType.BUILD_TRANSLATION_DRAFT,
            {JobStatus.WAITING_FOR_REVIEW},
        )
        ocr_oldest = self.db.scalar(
            select(func.min(OcrTextObject.updated_at)).where(
                OcrTextObject.workspace_id == self.workspace_id,
                OcrTextObject.status == OcrObjectStatus.NEEDS_REVIEW,
            )
        )
        checkpoints = [
            OperatorHomeCheckpoint(key="candidate_review", label="Candidate review", count=review_stage.review_count, detail="Shortlisted candidates waiting for a decision.", tone="warning" if review_stage.review_count else "good", href="/selection/review-board", oldest_at=candidate_oldest),
            OperatorHomeCheckpoint(key="translation_review", label="Translation review", count=translate_review, detail="Translation jobs paused for operator input.", tone="warning" if translate_review else "good", href="/selection/reup-queue", oldest_at=translate_oldest),
            OperatorHomeCheckpoint(key="ocr_review", label="OCR review", count=ocr_review, detail="Canonical OCR objects marked needs review.", tone="warning" if ocr_review else "good", href="/selection/reup-queue", oldest_at=ocr_oldest),
            OperatorHomeCheckpoint(key="output_review", label="Output QA", count=output_review, detail="Failed, warning, or ungraded final renders.", tone="critical" if output_qa.failed else "warning" if output_review else "good", href="/production/output-review", oldest_at=output_qa.oldest_attention_at),
        ]
        return checkpoints

    def _active_work(self) -> OperatorHomeActiveWork | None:
        row = self.db.execute(
            select(Job, SourceVideo)
            .outerjoin(SourceVideo, SourceVideo.id == Job.source_video_id)
            .where(
                Job.workspace_id == self.workspace_id,
                Job.job_type.in_(list(JOB_STAGE_BY_TYPE)),
                Job.status.in_([JobStatus.RUNNING, JobStatus.WAITING_FOR_REVIEW, JobStatus.QUEUED]),
            )
            .order_by(Job.updated_at.desc())
            .limit(1)
        ).first()
        if not row:
            return None
        job, source = row
        spec = JOB_STAGE_BY_TYPE.get(job.job_type)
        if spec is None:
            return None
        title = source.caption if source and source.caption else f"Source video {str(job.source_video_id)[:8]}"
        return OperatorHomeActiveWork(
            job_id=job.id,
            source_video_id=job.source_video_id,
            title=title,
            stage_key=spec.key,
            status=job.status.value,
            progress_percent=job.progress_percent,
            current_step=job.current_step_key,
            started_at=job.started_at,
            updated_at=job.updated_at,
            next_action="Open the owning stage and continue this durable job.",
            href=self._work_href(spec.key, job.source_video_id),
        )

    def _recent_outputs(self) -> list[OperatorHomeRecentOutput]:
        rows = self.db.execute(
            select(RenderOutput, SourceVideo)
            .join(SourceVideo, SourceVideo.id == RenderOutput.source_video_id)
            .where(RenderOutput.workspace_id == self.workspace_id)
            .order_by(RenderOutput.finished_at.desc().nullslast(), RenderOutput.updated_at.desc())
            .limit(4)
        ).all()
        render_ids = [render.id for render, _source in rows]
        qa_by_render: dict[UUID, str] = {}
        if render_ids:
            queue_items = self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.workspace_id == self.workspace_id,
                    ReupQueueItem.render_output_id.in_(render_ids),
                )
            )
            qa_by_render = {
                item.render_output_id: self._render_qa_status(item.metadata_json)
                for item in queue_items
                if item.render_output_id is not None
            }
        return [
            OperatorHomeRecentOutput(
                render_output_id=render.id,
                source_video_id=source.id,
                title=source.caption or f"Source video {str(source.id)[:8]}",
                render_status=render.status.value,
                qa_status=cast(str, qa_by_render.get(render.id, "ungraded")),
                duration_seconds=render.duration_seconds,
                finished_at=render.finished_at,
                href="/production/output-review",
            )
            for render, source in rows
        ]

    def _system_readiness(
        self,
        matrix: dict[tuple[JobType, JobStatus], int],
        extension: DouyinExtensionStatusResponse | None,
    ) -> list[OperatorHomeReadinessItem]:
        running = sum(self._job_count(matrix, spec.job_type, {JobStatus.RUNNING}) for spec in PRODUCTION_STAGE_SPECS)
        locked = self._count(Job, Job.status == JobStatus.RUNNING, Job.locked_by.is_not(None))
        worker_status = "ready" if running == 0 or locked > 0 else "warning"
        worker_detail = "Durable worker claims look healthy." if worker_status == "ready" else "Running jobs have no visible worker claim."
        extension_ready = bool(extension and extension.status == "connected" and extension.compatible)
        return [
            OperatorHomeReadinessItem(key="api", label="API", status="ready", detail="Home summary generated successfully."),
            OperatorHomeReadinessItem(key="worker", label="Worker", status=worker_status, detail=worker_detail, href="/ops/pipeline"),
            self._provider_readiness("ocr", "OCR runtime", JobType.ANALYZE_OCR),
            self._provider_readiness("tts", "TTS runtime", JobType.SYNTHESIZE_TTS),
            OperatorHomeReadinessItem(
                key="extension",
                label="Douyin extension",
                status="ready" if extension_ready else "warning" if extension else "unknown",
                detail=(extension.operator_message if extension else "Extension status was unavailable."),
                href="/setup/douyin-extension",
            ),
        ]

    def _provider_readiness(self, key: str, label: str, job_type: JobType) -> OperatorHomeReadinessItem:
        job = self.db.scalar(
            select(Job)
            .where(Job.workspace_id == self.workspace_id, Job.job_type == job_type)
            .order_by(Job.updated_at.desc())
            .limit(1)
        )
        if job is None:
            return OperatorHomeReadinessItem(key=key, label=label, status="unknown", detail="No canonical job history yet.", href="/selection/reup-queue")
        if job.status in {JobStatus.FAILED, JobStatus.RETRYABLE}:
            return OperatorHomeReadinessItem(key=key, label=label, status="blocked", detail=job.error_code or "Latest job failed.", href="/selection/reup-queue")
        if job.status in {JobStatus.RUNNING, JobStatus.COMPLETED}:
            return OperatorHomeReadinessItem(key=key, label=label, status="ready", detail=f"Latest job is {job.status.value.lower()}.", href="/selection/reup-queue")
        return OperatorHomeReadinessItem(key=key, label=label, status="warning", detail=f"Latest job is {job.status.value.lower()}.", href="/selection/reup-queue")

    def _count(self, model: object, *criteria: object) -> int:
        stmt = select(func.count()).select_from(model)
        if hasattr(model, "workspace_id"):
            stmt = stmt.where(model.workspace_id == self.workspace_id)
        for criterion in criteria:
            stmt = stmt.where(criterion)
        return int(self.db.scalar(stmt) or 0)

    @staticmethod
    def _render_qa_status(metadata: dict | None) -> str:
        render_qa = (metadata or {}).get("render_qa")
        if not isinstance(render_qa, dict):
            return "ungraded"
        status = render_qa.get("status")
        return status if status in {"pass", "warn", "fail"} else "ungraded"

    @staticmethod
    def _stage_status(*, failed: int = 0, review: int = 0, waiting: int = 0, running: int = 0, ready: int = 0) -> PipelineDashboardStatus:
        if failed > 0:
            return "blocked"
        if review > 0 or waiting > 0:
            return "needs_attention"
        if running > 0:
            return "in_progress"
        if ready > 0:
            return "healthy"
        return "quiet"

    @staticmethod
    def _headline(status: PipelineDashboardStatus, aggregate: OperatorHomeAggregate) -> str:
        if status == "blocked":
            return f"{aggregate.critical_count} critical item(s) need operator attention."
        if status == "needs_attention":
            return f"{aggregate.needs_attention} item(s) are shaping the next operator pass."
        if status == "in_progress":
            return f"{aggregate.in_progress} production job(s) are moving now."
        return "Workspace is quiet; start with Capture or Review when new work is ready."

    @staticmethod
    def _home_key_for_pipeline(key: str) -> OperatorHomeStageKey:
        return cast(OperatorHomeStageKey, key)

    @staticmethod
    def _safe_href(key: OperatorHomeStageKey, href: str) -> str:
        if not href.startswith("/ops/"):
            return href
        if key == "capture":
            return "/selection/capture-inbox"
        if key == "review":
            return "/selection/review-board"
        if key == "reup_queue":
            return "/selection/reup-queue"
        return "/publishing/drafts"

    @staticmethod
    def _work_href(key: OperatorHomeStageKey, source_video_id: UUID | None) -> str:
        if source_video_id and key in {"translate", "tts"}:
            return f"/production/transcript-editor/{source_video_id}"
        if key in {"render", "output_review"}:
            return "/production/output-review"
        return "/selection/reup-queue"

    @staticmethod
    def _stage_ready(stages: list[OperatorHomeStage], key: OperatorHomeStageKey) -> int:
        return next((stage.ready_count for stage in stages if stage.key == key), 0)
