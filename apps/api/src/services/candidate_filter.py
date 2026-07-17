from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.enums import RiskFlagType, RiskSeverity
from src.services.candidate_types import (
    CandidateEvaluation,
    CandidateSourceRecord,
    FilterConfig,
    FilterDateMode,
    FilterSortOption,
    ScoreWeights,
    TextDensity,
)
from src.services.reup_score import calculate_reup_score_v1


@dataclass(frozen=True)
class FilterResult:
    total_count: int
    matched_count: int
    rejected_count: int
    rejection_summary: dict[str, int]
    evaluations: list[CandidateEvaluation]


def apply_candidate_filter(
    records: list[CandidateSourceRecord],
    config: FilterConfig,
    *,
    weights: ScoreWeights | None = None,
    now: datetime | None = None,
) -> FilterResult:
    now = now or datetime.now(UTC)
    scoped_records = _apply_set_level_date_scope(records, config, now)
    evaluations = []
    rejection_counter: Counter[str] = Counter()

    for record in scoped_records:
        exclusion_reasons = _record_exclusions(record, config, now)
        score = calculate_reup_score_v1(record, weights=weights, now=now)
        inclusion_reasons = [] if exclusion_reasons else _inclusion_reasons(record, score.reasons)
        warnings = score.warnings + _data_warnings(record)
        for reason in exclusion_reasons:
            rejection_counter[reason] += 1
        evaluations.append(
            CandidateEvaluation(
                record=record,
                matched=not exclusion_reasons,
                score=score,
                inclusion_reasons=inclusion_reasons,
                exclusion_reasons=exclusion_reasons,
                warnings=warnings,
            )
        )

    evaluations = _sort_evaluations(evaluations, config)
    paged = evaluations[config.offset : config.offset + config.limit]
    matched_count = sum(1 for item in evaluations if item.matched)
    return FilterResult(
        total_count=len(records),
        matched_count=matched_count,
        rejected_count=len(evaluations) - matched_count,
        rejection_summary=dict(rejection_counter),
        evaluations=paged,
    )


def _apply_set_level_date_scope(
    records: list[CandidateSourceRecord],
    config: FilterConfig,
    now: datetime,
) -> list[CandidateSourceRecord]:
    if config.date_mode == FilterDateMode.LATEST_N_VIDEOS:
        sorted_records = sorted(records, key=lambda item: item.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        return sorted_records[: config.n_videos or len(sorted_records)]
    if config.date_mode == FilterDateMode.LAST_N_DAYS:
        cutoff = now - timedelta(days=config.n_days or 0)
        return [record for record in records if record.posted_at is None or record.posted_at >= cutoff]
    return records


def _record_exclusions(record: CandidateSourceRecord, config: FilterConfig, now: datetime) -> list[str]:
    reasons: list[str] = []
    metrics = record.metrics
    views = metrics.view_count or 0
    likes = metrics.like_count or 0
    comments = metrics.comment_count or 0
    shares = metrics.share_count or 0

    if config.date_mode == FilterDateMode.ABSOLUTE_RANGE and record.posted_at is not None:
        if config.start_date and record.posted_at < config.start_date:
            reasons.append("posted_before_start_date")
        if config.end_date and record.posted_at > config.end_date:
            reasons.append("posted_after_end_date")

    _threshold(reasons, "views", views, config.min_views, config.max_views)
    _threshold(reasons, "likes", likes, config.min_likes, config.max_likes)
    _threshold(reasons, "comments", comments, config.min_comments, config.max_comments)
    _threshold(reasons, "shares", shares, config.min_shares, config.max_shares)
    _threshold(reasons, "duration_seconds", record.duration_seconds, config.min_duration_seconds, config.max_duration_seconds)
    engagement_rate = (likes + comments + shares) / views if views > 0 else 0.0
    _threshold(reasons, "engagement_rate", engagement_rate, config.min_engagement_rate, config.max_engagement_rate)
    _min_ratio(reasons, "like_rate", likes, views, config.min_like_rate)
    _min_ratio(reasons, "comment_rate", comments, views, config.min_comment_rate)
    _min_ratio(reasons, "share_rate", shares, views, config.min_share_rate)

    signals = record.content_signals
    if config.has_speech is True and signals.has_speech is not True:
        reasons.append("speech_required_but_missing")
    elif config.has_speech is False and signals.has_speech is not False:
        reasons.append("speech_excluded")
    else:
        if config.require_speech and signals.has_speech is not True:
            reasons.append("speech_required_but_missing")
        if not config.allow_no_speech and signals.has_speech is False:
            reasons.append("no_speech_not_allowed")
    if config.max_text_density and _density_rank(signals.text_density) > _density_rank(config.max_text_density):
        reasons.append("text_density_too_high")
    if config.exclude_live_replay and signals.is_live_replay is True:
        reasons.append("live_replay_excluded")
    if config.exclude_slideshow and signals.is_slideshow is True:
        reasons.append("slideshow_excluded")
    if config.exclude_heavy_watermark and signals.has_heavy_watermark is True:
        reasons.append("heavy_watermark_excluded")
    if config.exclude_high_processing_complexity and signals.processing_complexity in {"high", "blocking"}:
        reasons.append("processing_complexity_too_high")
    if config.exclude_high_copyright_risk and _has_high_copyright_risk(record):
        reasons.append("high_copyright_risk")
    return reasons


def _threshold(
    reasons: list[str],
    field: str,
    value: int | float | None,
    minimum: int | float | None,
    maximum: int | float | None,
) -> None:
    if value is None:
        return
    if minimum is not None and value < minimum:
        reasons.append(f"{field}_below_min")
    if maximum is not None and value > maximum:
        reasons.append(f"{field}_above_max")


def _min_ratio(
    reasons: list[str],
    field: str,
    numerator: int,
    denominator: int,
    minimum: float | None,
) -> None:
    if minimum is None:
        return
    ratio = numerator / denominator if denominator > 0 else 0.0
    if ratio < minimum:
        reasons.append(f"{field}_below_min")


def _density_rank(value: TextDensity | None) -> int:
    if value is None:
        return 0
    return {TextDensity.LOW: 1, TextDensity.MEDIUM: 2, TextDensity.HIGH: 3}[value]


def _has_high_copyright_risk(record: CandidateSourceRecord) -> bool:
    return any(
        flag.flag_type == RiskFlagType.COPYRIGHT
        and flag.severity in {RiskSeverity.HIGH, RiskSeverity.BLOCKING}
        and flag.status == "OPEN"
        for flag in record.risk_flags
    )


def _inclusion_reasons(record: CandidateSourceRecord, score_reasons: list[str]) -> list[str]:
    reasons = list(score_reasons)
    if record.metrics.view_count and record.metrics.view_count >= 10_000:
        reasons.append("views meet practical review threshold")
    return reasons[:5]


def _data_warnings(record: CandidateSourceRecord) -> list[str]:
    warnings = []
    if record.metrics.view_count is None:
        warnings.append("missing view count")
    if record.posted_at is None:
        warnings.append("missing posted date")
    if record.content_signals.has_speech is None:
        warnings.append("speech signal not analyzed yet")
    if record.content_signals.text_density is None:
        warnings.append("text density not analyzed yet")
    return warnings


def _sort_evaluations(
    evaluations: list[CandidateEvaluation],
    config: FilterConfig,
) -> list[CandidateEvaluation]:
    if config.sort == FilterSortOption.NEWEST_FIRST:
        return sorted(evaluations, key=lambda item: item.record.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    if config.sort == FilterSortOption.VIEWS_DESC:
        return sorted(evaluations, key=lambda item: item.record.metrics.view_count or 0, reverse=True)
    if config.sort == FilterSortOption.ENGAGEMENT_DESC:
        return sorted(evaluations, key=_engagement_sort_key, reverse=True)
    return sorted(evaluations, key=lambda item: item.score.total_score, reverse=True)


def _engagement_sort_key(item: CandidateEvaluation) -> float:
    metrics = item.record.metrics
    views = metrics.view_count or 0
    if views <= 0:
        return 0.0
    return ((metrics.like_count or 0) + (metrics.comment_count or 0) * 3 + (metrics.share_count or 0) * 4) / views
