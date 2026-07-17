from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any, Literal

from src.services.douyin_metadata_normalization import normalize_douyin_count, normalize_douyin_engagement_count

MetadataStatus = Literal["pending_hydration", "complete", "partial", "missing", "failed"]
MetadataGroupStatus = Literal["captured", "missing", "failed", "pending"]
MetadataSource = Literal[
    "network_json",
    "detail_hydrate",
    "dom_detail_modal",
    "dom_zero_sentinel",
    "video_element_modal",
    "calibrated_point_dom",
    "calibrated_point_ocr",
    "mixed_calibrated_point",
    "dom_profile_card_fallback",
    "dom_snapshot",
    "existing_canonical",
    "missing",
]


@dataclass(frozen=True)
class CaptureMetadataNormalizeInput:
    raw_network_aweme: dict[str, Any] | None
    raw_detail_aweme: dict[str, Any] | None
    raw_dom_snapshot: dict[str, Any] | None
    raw_dom_detail_metrics: dict[str, Any] | None = None
    raw_evidence_summary: dict[str, Any] | None = None
    existing_posted_at: datetime | None = None
    existing_posted_text: str | None = None
    existing_duration_seconds: float | None = None
    existing_duration_text: str | None = None
    existing_view_count: int | None = None
    existing_like_count: int | None = None
    existing_comment_count: int | None = None
    existing_share_count: int | None = None
    existing_engagement_rate: float | None = None


@dataclass(frozen=True)
class CaptureMetadataNormalizeResult:
    posted_at: datetime | None
    posted_text: str | None
    duration_seconds: float | None
    duration_text: str | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    share_count: int | None
    engagement_rate: float | None
    posted_source: MetadataSource
    duration_source: MetadataSource
    view_count_source: MetadataSource
    like_count_source: MetadataSource
    comment_count_source: MetadataSource
    share_count_source: MetadataSource
    engagement_rate_source: MetadataSource
    metadata_status: MetadataStatus
    time_status: MetadataGroupStatus
    performance_status: MetadataGroupStatus
    processing_fit_status: MetadataGroupStatus
    metadata_missing_reason: str | None
    time_missing_reason: str | None
    performance_missing_reason: str | None
    processing_fit_missing_reason: str | None
    metadata_source_summary: str


class CaptureMetadataNormalizer:
    def normalize(self, payload: CaptureMetadataNormalizeInput) -> CaptureMetadataNormalizeResult:
        try:
            posted_at, posted_text, posted_source, time_reason = self._normalize_time(payload)
            duration_seconds, duration_text, duration_source, duration_reason = self._normalize_duration(payload)
            view_count, like_count, comment_count, share_count, engagement_rate, perf_sources, perf_reason = self._normalize_performance(payload)

            time_status: MetadataGroupStatus = "captured" if posted_at is not None or _reliable_posted_text(posted_text) else "missing"
            performance_status: MetadataGroupStatus = (
                "captured" if any(value is not None for value in (view_count, like_count, comment_count, share_count)) else "missing"
            )
            processing_fit_status: MetadataGroupStatus = "captured" if duration_seconds is not None else "missing"

            captured_count = sum(
                status == "captured" for status in (time_status, performance_status, processing_fit_status)
            )
            metadata_status: MetadataStatus
            if captured_count == 3:
                metadata_status = "complete"
            elif captured_count > 0:
                metadata_status = "partial"
            else:
                metadata_status = "missing"

            time_missing_reason = None if time_status == "captured" else time_reason
            performance_missing_reason = None if performance_status == "captured" else perf_reason
            processing_fit_missing_reason = None if processing_fit_status == "captured" else duration_reason
            metadata_missing_reason = _overall_missing_reason(
                metadata_status,
                time_missing_reason,
                performance_missing_reason,
                processing_fit_missing_reason,
            )

            source_summary = _source_summary(
                posted_source=posted_source,
                duration_source=duration_source,
                perf_sources=perf_sources,
            )

            return CaptureMetadataNormalizeResult(
                posted_at=posted_at,
                posted_text=posted_text,
                duration_seconds=duration_seconds,
                duration_text=duration_text,
                view_count=view_count,
                like_count=like_count,
                comment_count=comment_count,
                share_count=share_count,
                engagement_rate=engagement_rate,
                posted_source=posted_source,
                duration_source=duration_source,
                view_count_source=perf_sources["view_count_source"],
                like_count_source=perf_sources["like_count_source"],
                comment_count_source=perf_sources["comment_count_source"],
                share_count_source=perf_sources["share_count_source"],
                engagement_rate_source=perf_sources["engagement_rate_source"],
                metadata_status=metadata_status,
                time_status=time_status,
                performance_status=performance_status,
                processing_fit_status=processing_fit_status,
                metadata_missing_reason=metadata_missing_reason,
                time_missing_reason=time_missing_reason,
                performance_missing_reason=performance_missing_reason,
                processing_fit_missing_reason=processing_fit_missing_reason,
                metadata_source_summary=source_summary,
            )
        except Exception:
            return CaptureMetadataNormalizeResult(
                posted_at=payload.existing_posted_at,
                posted_text=payload.existing_posted_text,
                duration_seconds=payload.existing_duration_seconds,
                duration_text=payload.existing_duration_text,
                view_count=payload.existing_view_count,
                like_count=payload.existing_like_count,
                comment_count=payload.existing_comment_count,
                share_count=payload.existing_share_count,
                engagement_rate=payload.existing_engagement_rate,
                posted_source="existing_canonical" if (payload.existing_posted_at or payload.existing_posted_text) else "missing",
                duration_source="existing_canonical" if payload.existing_duration_seconds is not None else "missing",
                view_count_source="existing_canonical" if payload.existing_view_count is not None else "missing",
                like_count_source="existing_canonical" if payload.existing_like_count is not None else "missing",
                comment_count_source="existing_canonical" if payload.existing_comment_count is not None else "missing",
                share_count_source="existing_canonical" if payload.existing_share_count is not None else "missing",
                engagement_rate_source="existing_canonical" if payload.existing_engagement_rate is not None else "missing",
                metadata_status="failed",
                time_status="failed",
                performance_status="failed",
                processing_fit_status="failed",
                metadata_missing_reason="normalization_error",
                time_missing_reason="normalization_error",
                performance_missing_reason="normalization_error",
                processing_fit_missing_reason="normalization_error",
                metadata_source_summary="normalization_error",
            )

    def _normalize_time(self, payload: CaptureMetadataNormalizeInput) -> tuple[datetime | None, str | None, MetadataSource, str]:
        for evidence, source in ((payload.raw_network_aweme, "network_json"), (payload.raw_detail_aweme, "detail_hydrate")):
            if not isinstance(evidence, dict):
                continue
            raw_create = evidence.get("create_time")
            posted_at = _epoch_seconds_to_datetime(raw_create)
            if posted_at is not None:
                return posted_at, None, source, ""
            if raw_create is not None:
                return None, None, "missing", "invalid_create_time"

        dom_text = None
        if isinstance(payload.raw_dom_detail_metrics, dict):
            dom_posted_text = _reliable_posted_text(_string_or_none(payload.raw_dom_detail_metrics.get("posted_text")))
            if dom_posted_text:
                return None, dom_posted_text, "dom_detail_modal", ""
        if isinstance(payload.raw_dom_snapshot, dict):
            dom_text = payload.raw_dom_snapshot.get("visible_text")
        fallback_text = _extract_posted_text_from_dom(dom_text)
        if fallback_text:
            return None, fallback_text, "dom_snapshot", ""

        if payload.existing_posted_at is not None or _reliable_posted_text(payload.existing_posted_text):
            return payload.existing_posted_at, _reliable_posted_text(payload.existing_posted_text), "existing_canonical", ""

        has_structured = isinstance(payload.raw_network_aweme, dict) or isinstance(payload.raw_detail_aweme, dict)
        if not has_structured:
            return None, None, "missing", "no_network_or_detail_evidence"
        return None, None, "missing", "no_create_time"

    def _normalize_duration(self, payload: CaptureMetadataNormalizeInput) -> tuple[float | None, str | None, MetadataSource, str]:
        for evidence, source in ((payload.raw_network_aweme, "network_json"), (payload.raw_detail_aweme, "detail_hydrate")):
            seconds = _duration_seconds_from_aweme(evidence)
            if seconds is not None:
                return seconds, _format_duration(seconds), source, ""
            if isinstance(evidence, dict) and isinstance(evidence.get("video"), dict) and evidence["video"].get("duration") is not None:
                return None, None, "missing", "invalid_duration"

        if isinstance(payload.raw_dom_detail_metrics, dict):
            seconds = _duration_seconds_from_dom_detail(payload.raw_dom_detail_metrics)
            if seconds is not None:
                return seconds, _duration_text_from_dom_detail(payload.raw_dom_detail_metrics, seconds), "dom_detail_modal", ""

        dom_text = None
        if isinstance(payload.raw_dom_snapshot, dict):
            dom_text = payload.raw_dom_snapshot.get("visible_text")
        fallback = _duration_seconds_from_text(dom_text)
        if fallback is not None:
            return fallback, _format_duration(fallback), "dom_snapshot", ""

        if payload.existing_duration_seconds is not None:
            return payload.existing_duration_seconds, payload.existing_duration_text or _format_duration(payload.existing_duration_seconds), "existing_canonical", ""

        has_structured = isinstance(payload.raw_network_aweme, dict) or isinstance(payload.raw_detail_aweme, dict)
        if not has_structured:
            return None, None, "missing", "no_network_or_detail_evidence"
        return None, None, "missing", "no_video_duration"

    def _normalize_performance(
        self,
        payload: CaptureMetadataNormalizeInput,
    ) -> tuple[int | None, int | None, int | None, int | None, float | None, dict[str, MetadataSource], str]:
        defaults: dict[str, MetadataSource] = {
            "view_count_source": "missing",
            "like_count_source": "missing",
            "comment_count_source": "missing",
            "share_count_source": "missing",
            "engagement_rate_source": "missing",
        }

        for evidence, source in ((payload.raw_network_aweme, "network_json"), (payload.raw_detail_aweme, "detail_hydrate")):
            values = _statistics_from_aweme(evidence)
            if values is None:
                continue
            view_count, like_count, comment_count, share_count = values
            sources = dict(defaults)
            if view_count is not None:
                sources["view_count_source"] = source
            if like_count is not None:
                sources["like_count_source"] = source
            if comment_count is not None:
                sources["comment_count_source"] = source
            if share_count is not None:
                sources["share_count_source"] = source
            engagement_rate = _engagement_rate(view_count, like_count, comment_count, share_count)
            if engagement_rate is not None:
                sources["engagement_rate_source"] = source
            if any(v is not None for v in (view_count, like_count, comment_count, share_count)):
                return view_count, like_count, comment_count, share_count, engagement_rate, sources, ""

        if isinstance(payload.raw_dom_detail_metrics, dict):
            like_count = _non_negative_int(payload.raw_dom_detail_metrics.get("like_count"))
            comment_count = _non_negative_int(payload.raw_dom_detail_metrics.get("comment_count"))
            share_count = _non_negative_int(payload.raw_dom_detail_metrics.get("share_count"))
            if comment_count is None:
                comment_count = _engagement_count_from_dom_text("comment", payload.raw_dom_detail_metrics)
            if share_count is None:
                share_count = _engagement_count_from_dom_text("share", payload.raw_dom_detail_metrics)
            if any(v is not None for v in (like_count, comment_count, share_count)):
                sources = dict(defaults)
                if like_count is not None:
                    sources["like_count_source"] = _dom_like_count_source(payload.raw_dom_detail_metrics)
                if comment_count is not None:
                    sources["comment_count_source"] = _dom_engagement_count_source("comment", payload.raw_dom_detail_metrics, comment_count)
                if share_count is not None:
                    sources["share_count_source"] = _dom_engagement_count_source("share", payload.raw_dom_detail_metrics, share_count)
                return None, like_count, comment_count, share_count, None, sources, ""

        if any(
            value is not None
            for value in (
                payload.existing_view_count,
                payload.existing_like_count,
                payload.existing_comment_count,
                payload.existing_share_count,
            )
        ):
            sources = {
                "view_count_source": "existing_canonical" if payload.existing_view_count is not None else "missing",
                "like_count_source": "existing_canonical" if payload.existing_like_count is not None else "missing",
                "comment_count_source": "existing_canonical" if payload.existing_comment_count is not None else "missing",
                "share_count_source": "existing_canonical" if payload.existing_share_count is not None else "missing",
                "engagement_rate_source": "existing_canonical" if payload.existing_engagement_rate is not None else "missing",
            }
            engagement_rate = payload.existing_engagement_rate
            if engagement_rate is None:
                engagement_rate = _engagement_rate(
                    payload.existing_view_count,
                    payload.existing_like_count,
                    payload.existing_comment_count,
                    payload.existing_share_count,
                )
                if engagement_rate is not None:
                    sources["engagement_rate_source"] = "existing_canonical"
            return (
                payload.existing_view_count,
                payload.existing_like_count,
                payload.existing_comment_count,
                payload.existing_share_count,
                engagement_rate,
                sources,
                "",
            )

        has_structured = isinstance(payload.raw_network_aweme, dict) or isinstance(payload.raw_detail_aweme, dict)
        if not has_structured:
            return None, None, None, None, None, defaults, "no_network_or_detail_evidence"
        return None, None, None, None, None, defaults, "no_statistics"


def _epoch_seconds_to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        epoch = int(float(value))
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    if epoch > 10_000_000_000:
        epoch = epoch // 1000
    try:
        return datetime.fromtimestamp(epoch, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _duration_seconds_from_aweme(evidence: dict[str, Any] | None) -> float | None:
    if not isinstance(evidence, dict):
        return None
    video = evidence.get("video")
    if not isinstance(video, dict):
        return None
    raw = video.get("duration")
    if raw is None:
        return None
    try:
        numeric = float(raw)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    # Douyin is usually milliseconds, but keep second-scale values as-is.
    if numeric >= 1000:
        numeric = numeric / 1000.0
    if numeric > 60 * 60 * 24:
        return None
    return round(numeric, 3)


def _duration_seconds_from_text(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b", value)
    if not match:
        return None
    if match.group(1) is None:
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        if minutes > 59 or seconds > 59:
            return None
        return float(minutes * 60 + seconds)
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    if minutes > 59 or seconds > 59:
        return None
    return float(hours * 3600 + minutes * 60 + seconds)


def _duration_seconds_from_dom_detail(value: dict[str, Any]) -> float | None:
    raw_seconds = value.get("duration_seconds")
    if raw_seconds is not None:
        try:
            numeric = float(raw_seconds)
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None and 0 < numeric <= 60 * 60 * 24:
            return round(numeric, 3)
    return _duration_seconds_from_text(value.get("duration_text"))


def _duration_text_from_dom_detail(value: dict[str, Any], seconds: float) -> str:
    raw_text = _string_or_none(value.get("duration_text"))
    return raw_text or _format_duration(seconds)


def _format_duration(value: float) -> str:
    total = int(round(value))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _statistics_from_aweme(evidence: dict[str, Any] | None) -> tuple[int | None, int | None, int | None, int | None] | None:
    if not isinstance(evidence, dict):
        return None
    stats = evidence.get("statistics")
    if not isinstance(stats, dict):
        return None
    return (
        _non_negative_int(stats.get("play_count")),
        _non_negative_int(stats.get("digg_count")),
        _non_negative_int(stats.get("comment_count")),
        _non_negative_int(stats.get("share_count")),
    )


def _non_negative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _engagement_rate(view_count: int | None, like_count: int | None, comment_count: int | None, share_count: int | None) -> float | None:
    if view_count is None or view_count <= 0:
        return None
    interactions = (like_count or 0) + (comment_count or 0) + (share_count or 0)
    if interactions <= 0:
        return None
    return round(interactions / view_count, 6)


def _dom_like_count_source(raw_dom_detail_metrics: dict[str, Any]) -> MetadataSource:
    source = _string_or_none(raw_dom_detail_metrics.get("like_count_source"))
    if source == "dom_profile_card_fallback":
        return "dom_profile_card_fallback"
    return "dom_detail_modal"


def _dom_engagement_count_source(metric: Literal["comment", "share"], raw_dom_detail_metrics: dict[str, Any], count: int) -> MetadataSource:
    explicit = _string_or_none(raw_dom_detail_metrics.get(f"{metric}_count_source"))
    if explicit in {"dom_zero_sentinel", "dom_detail_modal", "dom_profile_card_fallback", "network_json", "detail_hydrate"}:
        return explicit  # type: ignore[return-value]
    text = _string_or_none(raw_dom_detail_metrics.get(f"{metric}_count_text"))
    if count == 0 and normalize_douyin_engagement_count(metric, None, text, share_icon_context=metric == "share" or text == "分享") == 0:
        return "dom_zero_sentinel"
    return "dom_detail_modal"


def _engagement_count_from_dom_text(metric: Literal["comment", "share"], raw_dom_detail_metrics: dict[str, Any]) -> int | None:
    text = _string_or_none(raw_dom_detail_metrics.get(f"{metric}_count_text"))
    numeric = normalize_douyin_count(text)
    if numeric is not None:
        return numeric
    return normalize_douyin_engagement_count(
        metric,
        None,
        text,
        share_icon_context=metric == "share" or text == "分享",
    )


def _extract_posted_text_from_dom(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    compact = re.sub(r"\s+", " ", value).strip()
    if not compact:
        return None
    if re.fullmatch(r"[0-9.]+", compact):
        return None
    for token in compact.split(" "):
        if _reliable_posted_text(token):
            if re.search(r"(刚刚|分钟|小时|天前|昨天|前|ago|yesterday|today)", token, re.IGNORECASE):
                return token
    return None


def _string_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _reliable_posted_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if re.fullmatch(r"[0-9.]+", normalized):
        return None
    lowered = normalized.lower()
    if lowered in {"not captured", "unknown", "n/a", "none", "null"}:
        return None
    return normalized


def _overall_missing_reason(metadata_status: MetadataStatus, *group_reasons: str | None) -> str | None:
    if metadata_status == "complete":
        return None
    reasons = [reason for reason in group_reasons if reason]
    return "; ".join(reasons) if reasons else None


def _source_summary(*, posted_source: MetadataSource, duration_source: MetadataSource, perf_sources: dict[str, MetadataSource]) -> str:
    perf_labels = sorted(
        {
            perf_sources.get("view_count_source"),
            perf_sources.get("like_count_source"),
            perf_sources.get("comment_count_source"),
            perf_sources.get("share_count_source"),
        }
        - {None, "missing"}
    )
    time_label = posted_source if posted_source != "missing" else "missing"
    duration_label = duration_source if duration_source != "missing" else "missing"
    perf_label = "+".join(perf_labels) if perf_labels else "missing"
    return f"time:{time_label}; performance:{perf_label}; processing_fit:{duration_label}"
