from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Protocol

from src.enums import JobStatus, JobType
from src.schemas.pipeline_dashboard import (
    PipelineDashboardMetric,
    PipelineDashboardStage,
    PipelineDashboardStatus,
    PipelineStageKey,
)

CAPTURE_HREF = "/selection/capture-inbox"
REVIEW_HREF = "/selection/review-board"
REUP_QUEUE_HREF = "/selection/reup-queue"
OUTPUT_REVIEW_HREF = "/production/output-review"
PUBLISH_DRAFTS_HREF = "/publishing/drafts"
EXPORT_HREF = "/publishing/export-packages"
HANDOFF_HREF = "/publishing/publish-handoffs"


@dataclass(frozen=True)
class PipelineCounts:
    captures_last_24h: int = 0
    capture_ready_items: int = 0
    capture_failed_items: int = 0
    review_backlog: int = 0
    approved_candidates: int = 0
    approved_not_queued: int = 0
    queue_active: int = 0
    queue_waiting_processing: int = 0
    queue_processing: int = 0
    queue_waiting_media: int = 0
    queue_waiting_metadata: int = 0
    queue_failed: int = 0
    queue_ready_to_export: int = 0
    export_draft: int = 0
    export_ready: int = 0
    export_failed: int = 0
    handoff_draft: int = 0
    handoff_ready: int = 0
    handoff_failed: int = 0
    publish_draft: int = 0
    publish_ready: int = 0
    publish_scheduled: int = 0
    publish_publishing: int = 0
    publish_active_drafts: int = 0
    publish_published: int = 0
    publish_failed_drafts: int = 0
    publish_active_attempts: int = 0
    publish_failed_attempts: int = 0
    publish_needs_reconciliation: int = 0


class OutputQaLike(Protocol):
    failed: int
    warned: int
    passed: int
    ungraded: int
    total: int


@dataclass(frozen=True)
class OutputQaCounts:
    failed: int = 0
    warned: int = 0
    passed: int = 0
    ungraded: int = 0
    oldest_failed_at: datetime | None = None
    oldest_review_at: datetime | None = None

    @property
    def total(self) -> int:
        return self.failed + self.warned + self.passed + self.ungraded

    @property
    def oldest_attention_at(self) -> datetime | None:
        known = [value for value in (self.oldest_failed_at, self.oldest_review_at) if value is not None]
        return min(known) if known else None


@dataclass(frozen=True)
class ProductionStageSpec:
    key: PipelineStageKey
    label: str
    description: str
    job_type: JobType
    href: str
    next_action: str


PRODUCTION_STAGE_SPECS: tuple[ProductionStageSpec, ...] = (
    ProductionStageSpec("download", "Download", "Durable source download jobs.", JobType.DOWNLOAD_VIDEO, REUP_QUEUE_HREF, "Inspect queued, running, or failed download jobs."),
    ProductionStageSpec("audio_analysis", "Audio", "Audio separation and analysis jobs.", JobType.ANALYZE_AUDIO, REUP_QUEUE_HREF, "Inspect audio analysis progress and retry safe failures."),
    ProductionStageSpec("translate", "Translate", "Translation draft jobs and manual language checkpoints.", JobType.BUILD_TRANSLATION_DRAFT, REUP_QUEUE_HREF, "Review translation checkpoints or retry failed jobs."),
    ProductionStageSpec("tts", "TTS", "Vietnamese narration synthesis jobs.", JobType.SYNTHESIZE_TTS, REUP_QUEUE_HREF, "Inspect TTS progress and resolve provider failures."),
    ProductionStageSpec("ocr", "OCR", "On-screen text detection and OCR review jobs.", JobType.ANALYZE_OCR, REUP_QUEUE_HREF, "Review OCR checkpoints or retry failed analysis."),
    ProductionStageSpec("render", "Render", "Final localized video render jobs.", JobType.RENDER_FINAL, OUTPUT_REVIEW_HREF, "Inspect render progress and open completed outputs for QA."),
)

JOB_STAGE_BY_TYPE = {spec.job_type: spec for spec in PRODUCTION_STAGE_SPECS}


def stage_status(*, failed: int = 0, review: int = 0, waiting: int = 0, running: int = 0, ready: int = 0) -> PipelineDashboardStatus:
    if failed > 0:
        return "blocked"
    if review > 0 or waiting > 0:
        return "needs_attention"
    if running > 0:
        return "in_progress"
    if ready > 0:
        return "healthy"
    return "quiet"


def _metric(key: str, label: str, value: int, detail: str | None = None) -> PipelineDashboardMetric:
    return PipelineDashboardMetric(key=key, label=label, value=value, detail=detail)


def _stage(
    *,
    key: PipelineStageKey,
    label: str,
    description: str,
    href: str,
    next_action: str,
    waiting: int = 0,
    running: int = 0,
    review: int = 0,
    failed: int = 0,
    ready: int = 0,
    attention: int | None = None,
    primary_count: int | None = None,
    primary_label: str = "Workload",
    secondary_count: int | None = None,
    secondary_label: str = "Ready",
    metrics: Iterable[PipelineDashboardMetric] = (),
) -> PipelineDashboardStage:
    total = waiting + running + review + failed + ready
    return PipelineDashboardStage(
        key=key,
        label=label,
        description=description,
        status=stage_status(failed=failed, review=review, waiting=waiting, running=running, ready=ready),
        primary_count=total if primary_count is None else primary_count,
        primary_label=primary_label,
        secondary_count=ready if secondary_count is None else secondary_count,
        secondary_label=secondary_label,
        metrics=list(metrics),
        attention_count=failed + review + waiting if attention is None else attention,
        waiting_count=waiting,
        running_count=running,
        review_count=review,
        failed_count=failed,
        ready_count=ready,
        total_count=total,
        href=href,
        next_action=next_action,
    )


def build_pipeline_stage_snapshots(
    counts: PipelineCounts,
    *,
    job_matrix: Mapping[tuple[JobType, JobStatus], int] | None = None,
    output_qa: OutputQaLike | None = None,
) -> list[PipelineDashboardStage]:
    matrix = job_matrix or {}
    qa = output_qa or OutputQaCounts()
    queue_waiting = counts.queue_waiting_processing + counts.queue_waiting_media + counts.queue_waiting_metadata
    queue_running = counts.queue_processing
    if counts.queue_waiting_processing == 0 and counts.queue_processing == 0:
        queue_running = max(
            0,
            counts.queue_active
            - counts.queue_waiting_media
            - counts.queue_waiting_metadata
            - counts.queue_failed
            - counts.queue_ready_to_export,
        )

    stages = [
        _stage(
            key="capture",
            label="Capture",
            description="Staged Douyin items waiting for promotion into canonical review.",
            href=CAPTURE_HREF,
            next_action="Promote ready capture items or inspect failed normalization.",
            waiting=counts.capture_ready_items,
            failed=counts.capture_failed_items,
            primary_count=counts.capture_ready_items,
            primary_label="Ready to promote",
            secondary_count=counts.captures_last_24h,
            secondary_label="Captured items in 24h",
            metrics=[_metric("failed", "Failed items", counts.capture_failed_items)],
        ),
        _stage(
            key="review",
            label="Review",
            description="Candidate decisions before admission into Reup Queue.",
            href=REVIEW_HREF,
            next_action="Review candidates and send approved work to Reup Queue.",
            review=counts.review_backlog,
            ready=counts.approved_not_queued,
            attention=counts.review_backlog + counts.approved_not_queued,
            primary_count=counts.review_backlog,
            primary_label="Review backlog",
            secondary_count=counts.approved_not_queued,
            secondary_label="Approved not queued",
            metrics=[_metric("approved", "Approved candidates", counts.approved_candidates)],
        ),
        _stage(
            key="reup_queue",
            label="Reup Queue",
            description="Stage-owned queue statuses before production and export.",
            href=REUP_QUEUE_HREF,
            next_action="Clear failed or waiting items and continue ready work.",
            waiting=queue_waiting,
            running=queue_running,
            failed=counts.queue_failed,
            ready=counts.queue_ready_to_export,
            primary_count=counts.queue_active,
            primary_label="Active queue items",
            secondary_count=counts.queue_ready_to_export,
            secondary_label="Ready to export",
            metrics=[
                _metric("waiting_media", "Waiting for media", counts.queue_waiting_media),
                _metric("failed", "Needs retry", counts.queue_failed),
            ],
        ),
    ]

    for spec in PRODUCTION_STAGE_SPECS:
        waiting = sum(matrix.get((spec.job_type, status), 0) for status in {JobStatus.QUEUED})
        running = sum(matrix.get((spec.job_type, status), 0) for status in {JobStatus.RUNNING})
        review = sum(matrix.get((spec.job_type, status), 0) for status in {JobStatus.WAITING_FOR_REVIEW})
        failed = sum(matrix.get((spec.job_type, status), 0) for status in {JobStatus.FAILED, JobStatus.RETRYABLE})
        ready = sum(matrix.get((spec.job_type, status), 0) for status in {JobStatus.COMPLETED})
        stages.append(
            _stage(
                key=spec.key,
                label=spec.label,
                description=spec.description,
                href=spec.href,
                next_action=spec.next_action,
                waiting=waiting,
                running=running,
                review=review,
                failed=failed,
                ready=ready,
            )
        )

    stages.extend(
        [
            _stage(
                key="output_review",
                label="Output Review",
                description="Final render QA results grouped by canonical QA status.",
                href=OUTPUT_REVIEW_HREF,
                next_action="Fix failed outputs and review warnings or ungraded renders.",
                review=qa.warned + qa.ungraded,
                failed=qa.failed,
                ready=qa.passed,
                primary_count=qa.failed + qa.warned + qa.ungraded,
                primary_label="Need review",
                secondary_count=qa.passed,
                secondary_label="Passed QA",
            ),
            _stage(
                key="draft",
                label="Draft",
                description="Current publish draft workload; published lifetime totals are excluded.",
                href=PUBLISH_DRAFTS_HREF,
                next_action="Review ready drafts and resolve failed publishing work.",
                waiting=counts.publish_draft,
                running=counts.publish_scheduled + counts.publish_publishing,
                review=counts.publish_ready,
                failed=counts.publish_failed_drafts,
                primary_count=counts.publish_active_drafts,
                primary_label="Active drafts",
                secondary_count=counts.publish_published,
                secondary_label="Published lifetime",
                metrics=[
                    _metric("active_attempts", "Active attempts", counts.publish_active_attempts),
                    _metric("needs_reconciliation", "Needs reconciliation", counts.publish_needs_reconciliation),
                ],
            ),
            _stage(
                key="export_package",
                label="Export Package",
                description="Stage-owned Export Package records.",
                href=EXPORT_HREF,
                next_action="Inspect draft packages and prepare ready packages for handoff.",
                waiting=counts.export_draft,
                failed=counts.export_failed,
                ready=counts.export_ready,
                attention=counts.export_draft + counts.export_failed + counts.export_ready,
                primary_count=counts.queue_ready_to_export,
                primary_label="Queue ready to package",
                secondary_count=counts.export_ready,
                secondary_label="Packages ready for handoff",
                metrics=[_metric("failed", "Failed packages", counts.export_failed)],
            ),
            _stage(
                key="publish_handoff",
                label="Publish Handoff",
                description="Stage-owned manual publish handoff records.",
                href=HANDOFF_HREF,
                next_action="Accept ready handoffs and continue platform-safe publishing.",
                waiting=counts.handoff_draft,
                failed=counts.handoff_failed,
                ready=counts.handoff_ready,
                attention=counts.handoff_draft + counts.handoff_failed + counts.handoff_ready,
                primary_count=counts.handoff_ready,
                primary_label="Ready for operator",
                secondary_count=counts.handoff_failed,
                secondary_label="Failed handoffs",
            ),
        ]
    )
    return stages
