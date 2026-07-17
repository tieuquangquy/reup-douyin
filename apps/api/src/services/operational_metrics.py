from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.enums import JobStatus, RiskFlagStatus, SourcePlatformEnum
from src.models.ingestion import CrawlSession
from src.models.jobs import Job, JobStep
from src.models.media import MediaAsset, RenderOutput
from src.models.publish import PublishDraft
from src.models.review import RiskFlag
from src.schemas.operations import (
    AssetReuseSummary,
    BacklogSummary,
    FailureCategory,
    FetchHealthAccountSummary,
    FetchHealthReasonCount,
    FetchHealthSummary,
    OperationalMetricsResponse,
)
from src.services.operational_metrics_helpers import (
    DurationSample,
    calculate_failure_rate,
    safe_average,
    summarize_counts,
    summarize_duration_samples,
)


class OperationalMetricsService:
    def __init__(self, db: Session, *, workspace_id: UUID) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def get_metrics(self) -> OperationalMetricsResponse:
        job_counts = self._job_counts_by_type_status()
        return OperationalMetricsResponse(
            generated_at=datetime.now(UTC),
            job_counts_by_type_status=job_counts,
            job_failure_rate_percent_by_type={
                job_type: calculate_failure_rate(status_counts)
                for job_type, status_counts in job_counts.items()
            },
            queue_backlog=self._queue_backlog(),
            retryable_jobs=self._count_retryable_jobs(),
            total_retry_attempts=self._total_retry_attempts(),
            step_duration_by_job_type=self._step_duration_by_job_type(),
            average_processing_seconds_per_source_video=self._average_processing_seconds_per_source_video(),
            common_failure_categories=self._common_failure_categories(),
            asset_reuse_by_type=self._asset_reuse_by_type(),
            render_counts_by_status=self._status_counts(RenderOutput.status),
            publish_draft_counts_by_status=self._status_counts(PublishDraft.status),
            open_risk_counts_by_severity=self._open_risk_counts_by_severity(),
            douyin_fetch_health=self._douyin_fetch_health(),
        )

    def _job_counts_by_type_status(self) -> dict[str, dict[str, int]]:
        rows = self.db.execute(
            select(Job.job_type, Job.status, func.count(Job.id))
            .where(Job.workspace_id == self.workspace_id)
            .group_by(Job.job_type, Job.status)
        ).all()
        return summarize_counts((row[0].value, row[1].value, row[2]) for row in rows)

    def _queue_backlog(self) -> BacklogSummary:
        counts = self._status_counts(Job.status)
        return BacklogSummary(
            queued=counts.get(JobStatus.QUEUED.value, 0),
            retryable=counts.get(JobStatus.RETRYABLE.value, 0),
            running=counts.get(JobStatus.RUNNING.value, 0),
        )

    def _count_retryable_jobs(self) -> int:
        return int(
            self.db.scalar(
                select(func.count(Job.id)).where(Job.workspace_id == self.workspace_id, Job.status == JobStatus.RETRYABLE)
            )
            or 0
        )

    def _total_retry_attempts(self) -> int:
        return int(self.db.scalar(select(func.coalesce(func.sum(Job.attempts), 0)).where(Job.workspace_id == self.workspace_id)) or 0)

    def _step_duration_by_job_type(self) -> dict[str, dict[str, float | int]]:
        rows = self.db.execute(
            select(Job.job_type, JobStep.started_at, JobStep.finished_at)
            .join(Job, Job.id == JobStep.job_id)
            .where(Job.workspace_id == self.workspace_id, JobStep.started_at.is_not(None), JobStep.finished_at.is_not(None))
            .limit(1000)
        ).all()
        samples = [
            DurationSample(
                group_key=row[0].value,
                duration_seconds=(row[2] - row[1]).total_seconds(),
            )
            for row in rows
        ]
        return summarize_duration_samples(samples)

    def _average_processing_seconds_per_source_video(self) -> float:
        rows = self.db.execute(
            select(Job.source_video_id, Job.started_at, Job.finished_at)
            .where(
                Job.workspace_id == self.workspace_id,
                Job.source_video_id.is_not(None),
                Job.started_at.is_not(None),
                Job.finished_at.is_not(None),
            )
            .limit(1000)
        ).all()
        durations_by_video: dict[str, list[float]] = defaultdict(list)
        for source_video_id, started_at, finished_at in rows:
            durations_by_video[str(source_video_id)].append((finished_at - started_at).total_seconds())
        return safe_average(sum(values) for values in durations_by_video.values())

    def _common_failure_categories(self) -> list[FailureCategory]:
        rows = self.db.execute(
            select(Job.error_code, func.count(Job.id))
            .where(Job.workspace_id == self.workspace_id, Job.error_code.is_not(None), Job.status.in_([JobStatus.FAILED, JobStatus.RETRYABLE]))
            .group_by(Job.error_code)
            .order_by(func.count(Job.id).desc())
            .limit(10)
        ).all()
        return [FailureCategory(error_code=str(error_code), count=int(count)) for error_code, count in rows]

    def _asset_reuse_by_type(self) -> list[AssetReuseSummary]:
        rows = self.db.execute(
            select(MediaAsset.asset_type, MediaAsset.is_current, func.count(MediaAsset.id))
            .where(MediaAsset.workspace_id == self.workspace_id)
            .group_by(
                MediaAsset.asset_type,
                MediaAsset.is_current,
            )
        ).all()
        grouped: dict[str, AssetReuseSummary] = {}
        for asset_type, is_current, count in rows:
            key = asset_type.value
            summary = grouped.setdefault(key, AssetReuseSummary(asset_type=key))
            if is_current:
                summary.current_count += int(count)
            else:
                summary.historical_count += int(count)
        return sorted(grouped.values(), key=lambda item: item.asset_type)

    def _open_risk_counts_by_severity(self) -> dict[str, int]:
        rows = self.db.execute(
            select(RiskFlag.severity, func.count(RiskFlag.id))
            .where(RiskFlag.workspace_id == self.workspace_id, RiskFlag.status == RiskFlagStatus.OPEN)
            .group_by(RiskFlag.severity)
        ).all()
        return {severity.value: int(count) for severity, count in rows}

    def _status_counts(self, column: object) -> dict[str, int]:
        model = getattr(column, "class_", None)
        stmt = select(column, func.count()).group_by(column)
        if model is not None and hasattr(model, "workspace_id"):
            stmt = stmt.where(model.workspace_id == self.workspace_id)
        rows = self.db.execute(stmt).all()
        return {row[0].value: int(row[1]) for row in rows}

    def _douyin_fetch_health(self) -> FetchHealthSummary:
        rows = self.db.execute(
            select(
                CrawlSession.metadata_json,
                CrawlSession.status,
            )
            .where(CrawlSession.workspace_id == self.workspace_id, CrawlSession.source_platform == SourcePlatformEnum.DOUYIN)
            .order_by(CrawlSession.created_at.desc())
            .limit(200)
        ).all()

        total = len(rows)
        blocked_runs = 0
        parse_warning_runs = 0
        failed_runs = 0
        reason_counts: dict[str, int] = defaultdict(int)
        by_account: dict[str, FetchHealthAccountSummary] = {}

        for metadata_raw, status in rows:
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
            observability = metadata.get("fetch_observability") if isinstance(metadata.get("fetch_observability"), dict) else {}
            blocked_reason = observability.get("blocked_reason") if isinstance(observability.get("blocked_reason"), str) else None
            stages = observability.get("stages") if isinstance(observability.get("stages"), dict) else {}
            normalize_stage = stages.get("normalize_payload") if isinstance(stages.get("normalize_payload"), dict) else {}
            normalize_result = normalize_stage.get("result") if isinstance(normalize_stage.get("result"), str) else None
            account_id = metadata.get("resolved_douyin_account_connection_id")
            account_key = str(account_id) if account_id is not None else "none"
            account = by_account.setdefault(
                account_key,
                FetchHealthAccountSummary(douyin_account_connection_id=None if account_id is None else str(account_id)),
            )
            account.runs_total += 1

            if blocked_reason:
                blocked_runs += 1
                reason_counts[blocked_reason] += 1
                account.blocked_runs += 1
            if normalize_result in {"warning", "failed"}:
                parse_warning_runs += 1
                account.parse_warning_runs += 1
            if str(status) == "FAILED":
                failed_runs += 1
                account.failed_runs += 1

        blocked_ratio = round((blocked_runs / total) * 100, 2) if total else 0.0
        ranked_reasons = sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        account_rows = sorted(by_account.values(), key=lambda item: item.runs_total, reverse=True)

        return FetchHealthSummary(
            window_runs=total,
            blocked_runs=blocked_runs,
            parse_warning_runs=parse_warning_runs,
            failed_runs=failed_runs,
            blocked_ratio_percent=blocked_ratio,
            top_blocked_reasons=[FetchHealthReasonCount(reason=reason, count=count) for reason, count in ranked_reasons],
            by_account=account_rows,
        )

