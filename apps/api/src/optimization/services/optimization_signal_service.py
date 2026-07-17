from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import PublishDraftStatus, RiskFlagStatus
from src.models.artifacts import TranscriptSegment, TranslationSegment
from src.models.publish import PublishDraft
from src.models.review import RiskFlag
from src.optimization.services.outcome_score_service import OutcomeScoreService
from src.schemas.optimization import ManualTouchHotspot, ManualTouchSummaryResponse, PresetFeedbackItem, PresetFeedbackResponse


class OptimizationSignalService:
    def __init__(self, db: Session):
        self.db = db
        self.outcome_service = OutcomeScoreService(db)

    def preset_feedback(self) -> PresetFeedbackResponse:
        summaries = self.outcome_service.outcome_summaries().by_preset
        items = [
            PresetFeedbackItem(
                preset_name=item.group_key,
                item_count=item.item_count,
                average_outcome_score=item.average_outcome_score,
                strong_count=item.strong_count,
                weak_count=item.weak_count,
                tuning_hints=self._preset_hints(item.average_outcome_score, item.item_count),
            )
            for item in summaries
        ]
        return PresetFeedbackResponse(generated_at=datetime.now(UTC), items=items)

    def manual_touch_summary(self) -> ManualTouchSummaryResponse:
        hotspots: list[ManualTouchHotspot] = []
        transcript_flags = self._json_flag_count(TranscriptSegment, "difficulty_flags_json")
        translation_flags = self._json_flag_count(TranslationSegment, "quality_flags_json")
        open_risks = len(list(self.db.scalars(select(RiskFlag).where(RiskFlag.status == RiskFlagStatus.OPEN))))
        needs_attention = len(list(self.db.scalars(select(PublishDraft).where(PublishDraft.status == PublishDraftStatus.NEEDS_ATTENTION))))
        publish_failures = len(list(self.db.scalars(select(PublishDraft).where(PublishDraft.status == PublishDraftStatus.FAILED))))

        self._append_hotspot(hotspots, "transcript_review", transcript_flags, "Transcript flags are driving manual review time.")
        self._append_hotspot(hotspots, "translation_review", translation_flags, "Translation flags may slow TTS/subtitle preparation.")
        self._append_hotspot(hotspots, "risk_review", open_risks, "Open risk flags require operator decisions before scaling.")
        self._append_hotspot(hotspots, "publish_reconciliation", needs_attention, "Drafts needing attention should be reconciled before retries.")
        self._append_hotspot(hotspots, "publish_failures", publish_failures, "Publish failures should be grouped by account and error code.")
        hotspots.sort(key=lambda item: item.count, reverse=True)
        return ManualTouchSummaryResponse(generated_at=datetime.now(UTC), hotspots=hotspots)

    def _preset_hints(self, average: float | None, count: int) -> list[str]:
        if count < 3:
            return ["Low sample size; do not tune preset automatically yet."]
        if average is not None and average >= 80:
            return ["Preset is producing strong outcomes; consider using it as a default for matching niches."]
        if average is not None and average < 55:
            return ["Preset is underperforming; review thresholds and exclusion rules."]
        return ["Preset is stable; keep observing before changing weights."]

    def _append_hotspot(self, hotspots: list[ManualTouchHotspot], area: str, count: int, hint: str) -> None:
        severity = "high" if count >= 10 else "medium" if count >= 3 else "low"
        hotspots.append(ManualTouchHotspot(area=area, count=count, severity=severity, hint=hint))

    def _json_flag_count(self, model, field_name: str) -> int:
        field = getattr(model, field_name)
        total = 0
        for payload in self.db.scalars(select(field).where(model.is_current.is_(True))):
            total += self._payload_count(payload)
        return total

    def _payload_count(self, payload: dict | list | None) -> int:
        if payload is None:
            return 0
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            count = 0
            for value in payload.values():
                if isinstance(value, bool) and value:
                    count += 1
                elif isinstance(value, list):
                    count += len(value)
                elif isinstance(value, dict):
                    count += self._payload_count(value)
            return count
        return 0

