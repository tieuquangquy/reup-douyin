from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from statistics import mean
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import (
    ExternalPublicationStatus,
    OperatorFeedbackQualityLabel,
    PublishDraftStatus,
    RiskFlagStatus,
    RiskSeverity,
    RiskTargetType,
)
from src.models.analytics import OperatorFeedback
from src.models.artifacts import TranscriptSegment, TranslationSegment
from src.models.ingestion import SourceProfile, SourceVideo
from src.models.media import RenderOutput
from src.models.publish import PlatformAccount, PublishAttempt, PublishDraft
from src.models.review import RiskFlag, VideoCandidate
from src.optimization.services.outcome_score_helpers import OUTCOME_SCORE_VERSION, ScoreComponent, outcome_label, weighted_component
from src.schemas.optimization import OutcomeGroupSummary, OutcomeScoreComponentResponse, OutcomeScoreResponse, OutcomeSummariesResponse


class OutcomeScoreError(ValueError):
    pass


class OutcomeScoreService:
    def __init__(self, db: Session):
        self.db = db

    def score_for_draft(self, publish_draft_id: UUID) -> OutcomeScoreResponse:
        draft = self.db.get(PublishDraft, publish_draft_id)
        if draft is None:
            raise OutcomeScoreError("Publish draft not found")
        return self._score_draft(draft)

    def outcome_summaries(self) -> OutcomeSummariesResponse:
        drafts = self._scorable_drafts()
        scored = [self._score_draft(draft) for draft in drafts]
        metadata = self._metadata()
        return OutcomeSummariesResponse(
            generated_at=datetime.now(UTC),
            score_version=OUTCOME_SCORE_VERSION,
            by_source_profile=self._group(scored, lambda score: metadata["profile_by_video"].get(score.source_video_id) or "Unknown source"),
            by_niche=self._group(scored, lambda score: metadata["niche_by_video"].get(score.source_video_id) or "unknown"),
            by_preset=self._group(scored, lambda score: metadata["preset_by_video"].get(score.source_video_id) or "unknown"),
            by_account=self._group(scored, lambda score: metadata["account_by_draft"].get(score.publish_draft_id) or "unassigned"),
            by_score_bucket=self._group(scored, lambda score: self._score_bucket(metadata["candidate_score_by_video"].get(score.source_video_id))),
        )

    def latest_scores(self, limit: int = 100) -> list[OutcomeScoreResponse]:
        return [self._score_draft(draft) for draft in self._scorable_drafts()[:limit]]

    def _score_draft(self, draft: PublishDraft) -> OutcomeScoreResponse:
        feedback = self._latest_feedback(draft.id)
        risk_flags = self._risk_flags(draft)
        render = self.db.get(RenderOutput, draft.render_output_id) if draft.render_output_id else None
        canonical_attempt = self.db.get(PublishAttempt, draft.canonical_publish_attempt_id) if draft.canonical_publish_attempt_id else None
        latest_attempt = self.db.get(PublishAttempt, draft.latest_publish_attempt_id) if draft.latest_publish_attempt_id else None
        attempt = canonical_attempt or latest_attempt
        transcript_flags = self._transcript_flag_count(draft.source_video_id)
        translation_flags = self._translation_flag_count(draft.source_video_id)

        components = [
            self._publish_success_component(draft, attempt),
            self._processing_stability_component(render, latest_attempt),
            self._risk_component(risk_flags),
            self._routing_component(draft, attempt),
            self._manual_intervention_component(transcript_flags, translation_flags),
            self._feedback_component(feedback),
        ]
        total = round(sum(item.weighted_contribution for item in components), 2)
        label = outcome_label(total)
        hints = self._hints(label, components)
        warnings = self._warnings(draft, risk_flags, latest_attempt)
        return OutcomeScoreResponse(
            target_id=draft.id,
            target_type="PUBLISH_DRAFT",
            publish_draft_id=draft.id,
            source_video_id=draft.source_video_id,
            score_version=OUTCOME_SCORE_VERSION,
            total_outcome_score=total,
            outcome_label=label,
            breakdown=[OutcomeScoreComponentResponse(**component.__dict__) for component in components],
            improvement_hints=hints,
            warnings=warnings,
        )

    def _publish_success_component(self, draft: PublishDraft, attempt: PublishAttempt | None) -> ScoreComponent:
        external_status = draft.current_publication_status
        subscore = 100 if external_status == ExternalPublicationStatus.PUBLISHED else 70 if external_status == ExternalPublicationStatus.PROCESSING else 45
        if draft.status == PublishDraftStatus.FAILED:
            subscore = 20
        if draft.status == PublishDraftStatus.NEEDS_ATTENTION:
            subscore = 35
        return weighted_component(
            "publish_success_quality",
            "Publish success quality",
            {"draft_status": draft.status.value, "external_status": external_status.value, "attempt_id": str(attempt.id) if attempt else None},
            subscore,
            30,
        )

    def _processing_stability_component(self, render: RenderOutput | None, attempt: PublishAttempt | None) -> ScoreComponent:
        render_warnings = self._warning_count(render.warning_summary_json if render else None)
        attempt_warnings = self._warning_count(attempt.warning_summary_json if attempt else None)
        error_penalty = 30 if (render and render.error_message) or (attempt and attempt.error_code) else 0
        subscore = 100 - (render_warnings * 8) - (attempt_warnings * 8) - error_penalty
        return weighted_component(
            "processing_stability",
            "Processing stability",
            {"render_warnings": render_warnings, "attempt_warnings": attempt_warnings, "has_error": error_penalty > 0},
            subscore,
            20,
        )

    def _risk_component(self, flags: list[RiskFlag]) -> ScoreComponent:
        open_flags = [flag for flag in flags if flag.status == RiskFlagStatus.OPEN]
        high_count = len([flag for flag in open_flags if flag.severity in {RiskSeverity.HIGH, RiskSeverity.CRITICAL, RiskSeverity.BLOCKING}])
        subscore = 100 - (high_count * 25) - (len(open_flags) * 5)
        return weighted_component(
            "risk_noise_penalty",
            "Risk noise penalty",
            {"open_flags": len(open_flags), "high_or_blocking_flags": high_count},
            subscore,
            15,
        )

    def _routing_component(self, draft: PublishDraft, attempt: PublishAttempt | None) -> ScoreComponent:
        assigned = draft.assigned_platform_account_id
        used = attempt.platform_account_id if attempt else None
        if assigned and used and assigned == used:
            subscore = 100
        elif assigned and not used:
            subscore = 70
        elif not assigned:
            subscore = 55
        else:
            subscore = 45
        if draft.assignment_status and draft.assignment_status.value == "OVERRIDDEN":
            subscore -= 10
        return weighted_component(
            "routing_fit_bonus",
            "Routing fit bonus",
            {"assigned_account_id": str(assigned) if assigned else None, "used_account_id": str(used) if used else None, "assignment_status": draft.assignment_status.value},
            subscore,
            15,
        )

    def _manual_intervention_component(self, transcript_flags: int, translation_flags: int) -> ScoreComponent:
        subscore = 100 - (transcript_flags * 4) - (translation_flags * 5)
        return weighted_component(
            "manual_intervention_penalty",
            "Manual intervention penalty",
            {"transcript_flag_count": transcript_flags, "translation_flag_count": translation_flags},
            subscore,
            10,
        )

    def _feedback_component(self, feedback: OperatorFeedback | None) -> ScoreComponent:
        if feedback is None:
            subscore = 60
            raw = {"quality_label": None, "publish_confidence": None}
        else:
            subscore = {
                OperatorFeedbackQualityLabel.GOOD: 100,
                OperatorFeedbackQualityLabel.ACCEPTABLE: 72,
                OperatorFeedbackQualityLabel.WEAK: 25,
            }[feedback.quality_label]
            raw = {"quality_label": feedback.quality_label.value, "publish_confidence": feedback.publish_confidence.value}
        return weighted_component("operator_feedback", "Operator feedback", raw, subscore, 10)

    def _hints(self, label: str, components: list[ScoreComponent]) -> list[str]:
        hints: list[str] = []
        weak = [item for item in components if item.subscore < 60]
        for item in weak:
            if item.key == "publish_success_quality":
                hints.append("Review publish/reconciliation failures before trusting this pattern.")
            elif item.key == "processing_stability":
                hints.append("Inspect render/TTS/publish warnings before scaling this source.")
            elif item.key == "risk_noise_penalty":
                hints.append("Resolve or tune recurring high-risk warnings before automation.")
            elif item.key == "manual_intervention_penalty":
                hints.append("Prioritize sources/presets with fewer transcript and translation flags.")
            elif item.key == "operator_feedback":
                hints.append("Operator feedback says this output pattern needs improvement.")
        if not hints and label == "strong":
            hints.append("Candidate pattern is suitable for higher confidence routing suggestions.")
        return hints

    def _warnings(self, draft: PublishDraft, risk_flags: list[RiskFlag], attempt: PublishAttempt | None) -> list[str]:
        warnings: list[str] = []
        if draft.status == PublishDraftStatus.NEEDS_ATTENTION:
            warnings.append("Publish draft needs operator attention.")
        if attempt and attempt.reconciliation_required:
            warnings.append("Latest publish attempt still needs reconciliation.")
        if any(flag.status == RiskFlagStatus.OPEN and flag.severity in {RiskSeverity.HIGH, RiskSeverity.CRITICAL, RiskSeverity.BLOCKING} for flag in risk_flags):
            warnings.append("High or blocking risk flags are still open.")
        return warnings

    def _group(self, scores: list[OutcomeScoreResponse], key_fn) -> list[OutcomeGroupSummary]:
        grouped: dict[str, list[OutcomeScoreResponse]] = defaultdict(list)
        for score in scores:
            grouped[str(key_fn(score))].append(score)
        rows: list[OutcomeGroupSummary] = []
        for key, items in grouped.items():
            avg = round(mean([item.total_outcome_score for item in items]), 2) if items else None
            rows.append(
                OutcomeGroupSummary(
                    group_key=key,
                    label=key,
                    item_count=len(items),
                    average_outcome_score=avg,
                    strong_count=len([item for item in items if item.outcome_label == "strong"]),
                    weak_count=len([item for item in items if item.outcome_label == "weak"]),
                    published_count=len([item for item in items if not item.warnings and item.total_outcome_score >= 65]),
                    needs_attention_count=len([item for item in items if item.warnings]),
                    hints=self._group_hints(avg, len(items)),
                )
            )
        return sorted(rows, key=lambda item: (item.average_outcome_score or 0, item.item_count), reverse=True)[:20]

    def _group_hints(self, average: float | None, count: int) -> list[str]:
        if count < 3:
            return ["Low sample size; use as a directional signal only."]
        if average is not None and average >= 80:
            return ["Strong recent outcomes; consider boost or higher routing confidence."]
        if average is not None and average < 55:
            return ["Weak recent outcomes; inspect sources, presets, or processing warnings."]
        return ["Stable enough for manual-guided recommendations."]

    def _metadata(self) -> dict[str, dict[UUID, str | float]]:
        videos = {item.id: item for item in self.db.scalars(select(SourceVideo))}
        profiles = {item.id: item for item in self.db.scalars(select(SourceProfile))}
        candidates = {item.source_video_id: item for item in self.db.scalars(select(VideoCandidate))}
        accounts = {item.id: item.display_name for item in self.db.scalars(select(PlatformAccount))}
        drafts = self._all_drafts()
        profile_by_video: dict[UUID, str] = {}
        niche_by_video: dict[UUID, str] = {}
        preset_by_video: dict[UUID, str] = {}
        score_by_video: dict[UUID, float] = {}
        account_by_draft: dict[UUID, str] = {}
        for video_id, video in videos.items():
            profile = profiles.get(video.source_profile_id)
            candidate = candidates.get(video_id)
            profile_by_video[video_id] = profile.display_name if profile and profile.display_name else "Unknown source"
            niche_by_video[video_id] = self._niche_label(video, candidate) or "unknown"
            preset_by_video[video_id] = candidate.preset_name if candidate and candidate.preset_name else "unknown"
            if candidate and candidate.score is not None:
                score_by_video[video_id] = candidate.score
        for draft in drafts:
            if draft.assigned_platform_account_id and draft.assigned_platform_account_id in accounts:
                account_by_draft[draft.id] = accounts[draft.assigned_platform_account_id]
            else:
                account_by_draft[draft.id] = "unassigned"
        return {
            "profile_by_video": profile_by_video,
            "niche_by_video": niche_by_video,
            "preset_by_video": preset_by_video,
            "candidate_score_by_video": score_by_video,
            "account_by_draft": account_by_draft,
        }

    def _all_drafts(self) -> list[PublishDraft]:
        return list(self.db.scalars(select(PublishDraft).order_by(PublishDraft.updated_at.desc())))

    def _scorable_drafts(self) -> list[PublishDraft]:
        """Only aggregate drafts with real post-publish or operator feedback signal.

        READY drafts can still get an individual score for inspection, but they should
        not distort outcome trends before an attempt or feedback exists.
        """
        feedback_draft_ids = {
            item.publish_draft_id
            for item in self.db.scalars(select(OperatorFeedback).where(OperatorFeedback.publish_draft_id.is_not(None)))
            if item.publish_draft_id is not None
        }
        return [
            draft
            for draft in self._all_drafts()
            if draft.latest_publish_attempt_id
            or draft.canonical_publish_attempt_id
            or draft.status in {PublishDraftStatus.PUBLISHED, PublishDraftStatus.FAILED, PublishDraftStatus.NEEDS_ATTENTION}
            or draft.id in feedback_draft_ids
        ]

    def _latest_feedback(self, draft_id: UUID) -> OperatorFeedback | None:
        return self.db.scalar(select(OperatorFeedback).where(OperatorFeedback.publish_draft_id == draft_id).order_by(OperatorFeedback.feedback_at.desc()).limit(1))

    def _risk_flags(self, draft: PublishDraft) -> list[RiskFlag]:
        return list(
            self.db.scalars(
                select(RiskFlag).where(
                    (RiskFlag.target_type == RiskTargetType.PUBLISH_DRAFT) & (RiskFlag.target_id == draft.id)
                    | (RiskFlag.source_video_id == draft.source_video_id)
                )
            )
        )

    def _transcript_flag_count(self, source_video_id: UUID) -> int:
        count = 0
        for segment in self.db.scalars(select(TranscriptSegment).where(TranscriptSegment.source_video_id == source_video_id, TranscriptSegment.is_current.is_(True))):
            count += self._warning_count(segment.difficulty_flags_json)
        return count

    def _translation_flag_count(self, source_video_id: UUID) -> int:
        count = 0
        for segment in self.db.scalars(select(TranslationSegment).where(TranslationSegment.source_video_id == source_video_id, TranslationSegment.is_current.is_(True))):
            count += self._warning_count(segment.quality_flags_json)
        return count

    def _warning_count(self, payload: dict | list | None) -> int:
        if payload is None:
            return 0
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            total = 0
            for value in payload.values():
                if isinstance(value, bool) and value:
                    total += 1
                elif isinstance(value, list):
                    total += len(value)
                elif isinstance(value, dict):
                    total += self._warning_count(value)
            return total
        return 0

    def _score_bucket(self, score: str | float | None) -> str:
        if score is None:
            return "unknown_score"
        value = float(score)
        if value >= 80:
            return "score_80_100"
        if value >= 60:
            return "score_60_79"
        if value >= 40:
            return "score_40_59"
        return "score_0_39"

    def _niche_label(self, source_video: SourceVideo | None, candidate: VideoCandidate | None) -> str | None:
        for payload in [candidate.filter_config_json if candidate else None, source_video.metadata_json if source_video else None]:
            if isinstance(payload, dict):
                value = payload.get("niche") or payload.get("niche_tag") or payload.get("niche_label")
                if value:
                    return str(value)
        return None
