from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analytics.services.publish_health_helpers import percent, resolve_time_window
from src.enums import ExternalPublicationStatus, OperatorFeedbackQualityLabel, PublishAttemptStatus, PublishDraftStatus, RiskFlagStatus, RiskSeverity, RiskTargetType
from src.models.analytics import OperatorFeedback
from src.models.ingestion import SourceProfile, SourceVideo
from src.models.publish import PlatformAccount, PublishAttempt, PublishDraft
from src.models.review import RiskFlag, VideoCandidate
from src.schemas.analytics import (
    AccountHealthSummary,
    FailureCategorySummary,
    FailureSummaryResponse,
    OperatorActionQueue,
    PipelineFeedbackGroup,
    PipelineFeedbackResponse,
    PublicationOutcomeItem,
    PublishDayStats,
    PublishHealthDashboardResponse,
    PublishHealthOverview,
)


class PublishHealthService:
    def __init__(self, db: Session):
        self.db = db

    def dashboard_snapshot(self, *, window: str = "last_7_days", start: datetime | None = None, end: datetime | None = None) -> PublishHealthDashboardResponse:
        window_start, window_end = resolve_time_window(window, start, end)
        attempts = self._attempts_in_window(window_start, window_end)
        drafts = self._all_publish_drafts()
        feedback_by_draft = self._latest_feedback_by_draft()

        overview = self._overview(attempts, drafts)
        outcomes = self._publication_outcomes(drafts, feedback_by_draft)
        return PublishHealthDashboardResponse(
            generated_at=datetime.now(UTC),
            window=window,
            window_start=window_start,
            window_end=window_end,
            overview=overview,
            by_day=self._by_day(attempts),
            account_health=self._account_health(attempts),
            failure_categories=self._failure_categories(attempts),
            action_queue=OperatorActionQueue(
                needs_reconciliation=[item for item in outcomes if item.status == PublishDraftStatus.NEEDS_ATTENTION or item.external_status in {ExternalPublicationStatus.UNKNOWN, ExternalPublicationStatus.PARTIALLY_CONFIRMED}][:10],
                drafts_ready=[item for item in outcomes if item.status == PublishDraftStatus.READY][:10],
                blocked_by_risk_count=self._risk_blocked_count(),
                recent_successes=[item for item in outcomes if item.status == PublishDraftStatus.PUBLISHED][:10],
            ),
            pipeline_feedback=self._pipeline_feedback_groups(outcomes),
        )

    def publication_outcomes(
        self,
        *,
        account_id: UUID | None = None,
        status: PublishDraftStatus | None = None,
        limit: int = 100,
    ) -> list[PublicationOutcomeItem]:
        feedback_by_draft = self._latest_feedback_by_draft()
        outcomes = self._publication_outcomes(self._all_publish_drafts(), feedback_by_draft)
        if account_id is not None:
            outcomes = [item for item in outcomes if item.platform_account_id == account_id]
        if status is not None:
            outcomes = [item for item in outcomes if item.status == status]
        return outcomes[:limit]

    def failure_summary(self, *, window: str = "last_7_days") -> FailureSummaryResponse:
        window_start, window_end = resolve_time_window(window)
        attempts = self._attempts_in_window(window_start, window_end)
        outcomes = self._publication_outcomes(self._all_publish_drafts(), self._latest_feedback_by_draft())
        return FailureSummaryResponse(
            generated_at=datetime.now(UTC),
            window=window,
            failure_categories=self._failure_categories(attempts),
            recent_failed_attempts=[item for item in outcomes if item.status == PublishDraftStatus.FAILED][:10],
            reconciliation_needed=[item for item in outcomes if item.status == PublishDraftStatus.NEEDS_ATTENTION][:10],
        )

    def pipeline_feedback(self, *, window: str = "last_7_days") -> PipelineFeedbackResponse:
        outcomes = self._publication_outcomes(self._all_publish_drafts(), self._latest_feedback_by_draft())
        groups = self._pipeline_feedback_groups(outcomes)
        return PipelineFeedbackResponse(
            generated_at=datetime.now(UTC),
            window=window,
            by_source_profile=groups["by_source_profile"],
            by_niche=groups["by_niche"],
            by_preset=groups["by_preset"],
        )

    def _attempts_in_window(self, start: datetime, end: datetime) -> list[PublishAttempt]:
        return list(
            self.db.scalars(
                select(PublishAttempt)
                .where(PublishAttempt.created_at >= start, PublishAttempt.created_at <= end)
                .order_by(PublishAttempt.created_at.desc(), PublishAttempt.attempt_number.desc())
            )
        )

    def _all_publish_drafts(self) -> list[PublishDraft]:
        return list(self.db.scalars(select(PublishDraft).order_by(PublishDraft.updated_at.desc())))

    def _overview(self, attempts: list[PublishAttempt], drafts: list[PublishDraft]) -> PublishHealthOverview:
        succeeded = len([item for item in attempts if item.status in {PublishAttemptStatus.SUCCEEDED, PublishAttemptStatus.RECONCILED} and item.external_status == ExternalPublicationStatus.PUBLISHED])
        failed = len([item for item in attempts if item.status == PublishAttemptStatus.FAILED])
        needs_reconciliation = len([item for item in attempts if item.status == PublishAttemptStatus.NEEDS_RECONCILIATION or item.reconciliation_required])
        return PublishHealthOverview(
            total_attempts=len(attempts),
            succeeded_attempts=succeeded,
            failed_attempts=failed,
            needs_reconciliation_attempts=needs_reconciliation,
            canonical_published_count=len([draft for draft in drafts if draft.canonical_publish_attempt_id is not None and draft.status == PublishDraftStatus.PUBLISHED]),
            drafts_ready_not_published=len([draft for draft in drafts if draft.status == PublishDraftStatus.READY]),
            drafts_blocked_by_risk=self._risk_blocked_count(),
            success_rate_percent=percent(succeeded, len(attempts)),
        )

    def _by_day(self, attempts: list[PublishAttempt]) -> list[PublishDayStats]:
        grouped: dict[str, list[PublishAttempt]] = defaultdict(list)
        for attempt in attempts:
            grouped[attempt.created_at.date().isoformat()].append(attempt)
        return [
            PublishDayStats(
                day=day,
                attempts=len(items),
                succeeded=len([item for item in items if item.external_status == ExternalPublicationStatus.PUBLISHED]),
                failed=len([item for item in items if item.status == PublishAttemptStatus.FAILED]),
                needs_reconciliation=len([item for item in items if item.status == PublishAttemptStatus.NEEDS_RECONCILIATION or item.reconciliation_required]),
            )
            for day, items in sorted(grouped.items())
        ]

    def _account_health(self, attempts: list[PublishAttempt]) -> list[AccountHealthSummary]:
        accounts = {account.id: account for account in self.db.scalars(select(PlatformAccount))}
        grouped: dict[UUID, list[PublishAttempt]] = defaultdict(list)
        for attempt in attempts:
            grouped[attempt.platform_account_id].append(attempt)
        summaries: list[AccountHealthSummary] = []
        for account_id, items in grouped.items():
            account = accounts.get(account_id)
            succeeded = len([item for item in items if item.external_status == ExternalPublicationStatus.PUBLISHED])
            failed_items = [item for item in items if item.status == PublishAttemptStatus.FAILED]
            summaries.append(
                AccountHealthSummary(
                    platform_account_id=account_id,
                    display_name=account.display_name if account else "Unknown account",
                    platform=account.platform if account else "UNKNOWN",
                    attempts=len(items),
                    succeeded=succeeded,
                    failed=len(failed_items),
                    needs_reconciliation=len([item for item in items if item.status == PublishAttemptStatus.NEEDS_RECONCILIATION or item.reconciliation_required]),
                    success_rate_percent=percent(succeeded, len(items)),
                    recent_error_code=failed_items[0].error_code if failed_items else None,
                )
            )
        return sorted(summaries, key=lambda item: item.attempts, reverse=True)

    def _failure_categories(self, attempts: list[PublishAttempt]) -> list[FailureCategorySummary]:
        counts: Counter[str] = Counter()
        for attempt in attempts:
            if attempt.status == PublishAttemptStatus.FAILED or attempt.error_code:
                counts[self._failure_group(attempt.error_code)] += 1
            elif attempt.status == PublishAttemptStatus.NEEDS_RECONCILIATION:
                counts["reconciliation_uncertainty"] += 1
        return [FailureCategorySummary(error_code=key, label=key.replace("_", " "), count=count) for key, count in counts.most_common(10)]

    def _publication_outcomes(self, drafts: list[PublishDraft], feedback_by_draft: dict[UUID, OperatorFeedback]) -> list[PublicationOutcomeItem]:
        source_videos = {item.id: item for item in self.db.scalars(select(SourceVideo))}
        profiles = {item.id: item for item in self.db.scalars(select(SourceProfile))}
        candidates = {item.source_video_id: item for item in self.db.scalars(select(VideoCandidate))}
        attempts = {item.id: item for item in self.db.scalars(select(PublishAttempt))}
        items: list[PublicationOutcomeItem] = []
        for draft in drafts:
            source_video = source_videos.get(draft.source_video_id)
            profile = profiles.get(source_video.source_profile_id) if source_video else None
            candidate = candidates.get(draft.source_video_id)
            canonical_attempt = attempts.get(draft.canonical_publish_attempt_id) if draft.canonical_publish_attempt_id else None
            latest_attempt = attempts.get(draft.latest_publish_attempt_id) if draft.latest_publish_attempt_id else None
            feedback = feedback_by_draft.get(draft.id)
            items.append(
                PublicationOutcomeItem(
                    publish_draft_id=draft.id,
                    source_video_id=draft.source_video_id,
                    render_output_id=draft.render_output_id,
                    platform=draft.target_platform,
                    status=draft.status,
                    external_status=draft.current_publication_status,
                    external_publish_id=draft.current_external_publish_id,
                    external_permalink=draft.current_external_permalink,
                    canonical_publish_attempt_id=draft.canonical_publish_attempt_id,
                    platform_account_id=(canonical_attempt or latest_attempt).platform_account_id if (canonical_attempt or latest_attempt) else None,
                    source_profile_name=profile.display_name if profile else None,
                    preset_name=candidate.preset_name if candidate else None,
                    niche_label=self._niche_label(source_video, candidate),
                    score=candidate.score if candidate else None,
                    published_at=draft.published_at,
                    last_publish_synced_at=draft.last_publish_synced_at,
                    feedback_quality_label=feedback.quality_label if feedback else None,
                    feedback_confidence=feedback.publish_confidence if feedback else None,
                )
            )
        return items

    def _latest_feedback_by_draft(self) -> dict[UUID, OperatorFeedback]:
        result: dict[UUID, OperatorFeedback] = {}
        for feedback in self.db.scalars(select(OperatorFeedback).order_by(OperatorFeedback.feedback_at.desc())):
            if feedback.publish_draft_id and feedback.publish_draft_id not in result:
                result[feedback.publish_draft_id] = feedback
        return result

    def _pipeline_feedback_groups(self, outcomes: list[PublicationOutcomeItem]) -> dict[str, list[PipelineFeedbackGroup]]:
        return {
            "by_source_profile": self._group_outcomes(outcomes, lambda item: item.source_profile_name or "Unknown source"),
            "by_niche": self._group_outcomes(outcomes, lambda item: item.niche_label or "unknown"),
            "by_preset": self._group_outcomes(outcomes, lambda item: item.preset_name or "unknown"),
        }

    def _group_outcomes(self, outcomes: list[PublicationOutcomeItem], key_fn) -> list[PipelineFeedbackGroup]:
        grouped: dict[str, list[PublicationOutcomeItem]] = defaultdict(list)
        for item in outcomes:
            grouped[key_fn(item)].append(item)
        groups: list[PipelineFeedbackGroup] = []
        for key, items in grouped.items():
            scores = [item.score for item in items if item.score is not None]
            groups.append(
                PipelineFeedbackGroup(
                    group_key=key,
                    label=key,
                    published_count=len([item for item in items if item.status == PublishDraftStatus.PUBLISHED]),
                    good_feedback_count=len([item for item in items if item.feedback_quality_label == OperatorFeedbackQualityLabel.GOOD]),
                    weak_feedback_count=len([item for item in items if item.feedback_quality_label == OperatorFeedbackQualityLabel.WEAK]),
                    needs_reconciliation_count=len([item for item in items if item.status == PublishDraftStatus.NEEDS_ATTENTION]),
                    average_score=round(sum(scores) / len(scores), 2) if scores else None,
                )
            )
        return sorted(groups, key=lambda item: (item.published_count, item.good_feedback_count), reverse=True)[:10]

    def _risk_blocked_count(self) -> int:
        blocking = {RiskSeverity.HIGH, RiskSeverity.CRITICAL, RiskSeverity.BLOCKING}
        rows = self.db.scalars(
            select(RiskFlag).where(
                RiskFlag.target_type == RiskTargetType.PUBLISH_DRAFT,
                RiskFlag.status == RiskFlagStatus.OPEN,
                RiskFlag.severity.in_(blocking),
            )
        )
        return len({item.target_id for item in rows if item.target_id is not None})

    def _failure_group(self, error_code: str | None) -> str:
        if not error_code:
            return "unknown_failure"
        if "token" in error_code or "auth" in error_code or "account" in error_code:
            return "auth_or_account_config"
        if "gate" in error_code or "risk" in error_code:
            return "gate_or_policy_blocked"
        if "upload" in error_code or "network" in error_code:
            return "upload_or_transport_failure"
        if "reconciliation" in error_code or "ambiguous" in error_code:
            return "reconciliation_uncertainty"
        if "publish" in error_code:
            return "platform_publish_failure"
        return error_code

    def _niche_label(self, source_video: SourceVideo | None, candidate: VideoCandidate | None) -> str | None:
        for payload in [candidate.filter_config_json if candidate else None, source_video.metadata_json if source_video else None]:
            if isinstance(payload, dict):
                value = payload.get("niche") or payload.get("niche_tag") or payload.get("niche_label")
                if value:
                    return str(value)
        return None
