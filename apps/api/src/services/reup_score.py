from __future__ import annotations

from datetime import UTC, datetime
import math

from src.enums import RiskFlagType, RiskSeverity
from src.services.candidate_types import (
    CandidateSourceRecord,
    ScoreComponent,
    ScoreResult,
    ScoreWeights,
    TextDensity,
)

REUP_SCORE_V1 = "REUP_SCORE_V1"


def calculate_reup_score_v1(
    record: CandidateSourceRecord,
    *,
    weights: ScoreWeights | None = None,
    now: datetime | None = None,
) -> ScoreResult:
    weights = weights or ScoreWeights()
    now = now or datetime.now(UTC)
    metrics = record.metrics
    views = metrics.view_count or 0
    likes = metrics.like_count or 0
    comments = metrics.comment_count or 0
    shares = metrics.share_count or 0
    like_rate = _ratio(likes, views)
    comment_rate = _ratio(comments, views)
    share_rate = _ratio(shares, views)

    components = {
        "engagement_quality": _component(
            {"likes": likes, "comments": comments, "shares": shares, "views": views},
            min(100.0, (like_rate * 900) + (comment_rate * 2200) + (share_rate * 2600)),
            weights.engagement_quality,
        ),
        "freshness": _component(
            {"posted_at": record.posted_at.isoformat() if record.posted_at else None},
            _freshness_score(record.posted_at, now),
            weights.freshness,
        ),
        "views_normalized": _component(
            {"views": views},
            _log_score(views, target=100_000),
            weights.views_normalized,
        ),
        "like_rate": _component(
            {"like_rate": like_rate},
            min(100.0, like_rate * 1600),
            weights.like_rate,
        ),
        "comment_share_quality": _component(
            {"comment_rate": comment_rate, "share_rate": share_rate},
            min(100.0, (comment_rate * 1800) + (share_rate * 2600)),
            weights.comment_share_quality,
        ),
        "duration_fit": _component(
            {"duration_seconds": record.duration_seconds},
            _duration_score(record.duration_seconds),
            weights.duration_fit,
        ),
        "speech_bonus": _component(
            {"has_speech": record.content_signals.has_speech},
            100.0 if record.content_signals.has_speech is True else 50.0 if record.content_signals.has_speech is None else 25.0,
            weights.speech_bonus,
        ),
        "text_complexity_penalty": _component(
            {"text_density": record.content_signals.text_density},
            _text_density_score(record.content_signals.text_density),
            weights.text_complexity_penalty,
        ),
        "watermark_penalty": _component(
            {"has_heavy_watermark": record.content_signals.has_heavy_watermark},
            30.0 if record.content_signals.has_heavy_watermark else 90.0,
            weights.watermark_penalty,
        ),
        "copyright_risk_penalty": _component(
            {"risk_flags": [flag.severity for flag in record.risk_flags if flag.flag_type == RiskFlagType.COPYRIGHT]},
            _copyright_score(record),
            weights.copyright_risk_penalty,
        ),
    }
    total = round(sum(component.weighted_contribution for component in components.values()), 2)
    label = "hot" if total >= 75 else "usable" if total >= 55 else "skip"
    reasons = _reason_summary(record, total, like_rate, share_rate)
    warnings = _warnings(record)
    return ScoreResult(
        score_version=REUP_SCORE_V1,
        total_score=total,
        score_label=label,
        breakdown=components,
        reasons=reasons,
        warnings=warnings,
    )


def _component(raw_input: dict, normalized_subscore: float, weight: float) -> ScoreComponent:
    subscore = round(max(0.0, min(100.0, normalized_subscore)), 2)
    return ScoreComponent(
        raw_input=raw_input,
        normalized_subscore=subscore,
        weight=weight,
        weighted_contribution=round(subscore * weight, 2),
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _log_score(value: int, *, target: int) -> float:
    if value <= 0:
        return 0.0
    return min(100.0, (math.log10(value + 1) / math.log10(target + 1)) * 100)


def _freshness_score(posted_at: datetime | None, now: datetime) -> float:
    if posted_at is None:
        return 45.0
    age_days = max(0.0, (now - posted_at).total_seconds() / 86400)
    if age_days <= 7:
        return 100.0
    if age_days <= 30:
        return 80.0
    if age_days <= 90:
        return 55.0
    return 25.0


def _duration_score(duration_seconds: float | None) -> float:
    if duration_seconds is None:
        return 50.0
    if 12 <= duration_seconds <= 55:
        return 100.0
    if 6 <= duration_seconds < 12 or 55 < duration_seconds <= 90:
        return 70.0
    if 90 < duration_seconds <= 150:
        return 35.0
    return 20.0


def _text_density_score(text_density: TextDensity | None) -> float:
    if text_density is None:
        return 70.0
    if text_density == TextDensity.LOW:
        return 100.0
    if text_density == TextDensity.MEDIUM:
        return 70.0
    return 25.0


def _copyright_score(record: CandidateSourceRecord) -> float:
    severities = [flag.severity for flag in record.risk_flags if flag.flag_type == RiskFlagType.COPYRIGHT and flag.status == "OPEN"]
    if RiskSeverity.BLOCKING in severities or RiskSeverity.HIGH in severities:
        return 10.0
    if RiskSeverity.MEDIUM in severities:
        return 45.0
    return 95.0


def _reason_summary(record: CandidateSourceRecord, total: float, like_rate: float, share_rate: float) -> list[str]:
    reasons = []
    if total >= 75:
        reasons.append("strong overall reup score")
    if like_rate >= 0.05:
        reasons.append("strong like rate")
    if share_rate >= 0.01:
        reasons.append("strong share rate")
    if record.content_signals.has_speech is True:
        reasons.append("speech signal available")
    if record.duration_seconds is not None and 12 <= record.duration_seconds <= 55:
        reasons.append("duration fits short-form reup workflow")
    return reasons[:4]


def _warnings(record: CandidateSourceRecord) -> list[str]:
    warnings = []
    if record.content_signals.text_density == TextDensity.HIGH:
        warnings.append("high text density may require more editing")
    if record.content_signals.has_heavy_watermark is True:
        warnings.append("heavy watermark signal present")
    if any(flag.severity in {RiskSeverity.HIGH, RiskSeverity.BLOCKING} for flag in record.risk_flags):
        warnings.append("high or blocking risk flag present")
    return warnings

