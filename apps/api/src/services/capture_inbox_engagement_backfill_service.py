from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import time
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.enums import CapturedItemStatus, SourcePlatformEnum
from src.models.capture_inbox import CaptureSession, CapturedItem
from src.schemas.capture_inbox import CapturedItemResponse
from src.services.douyin_metadata_normalization import (
    normalize_douyin_count,
    normalize_douyin_engagement_count,
)

EngagementMetric = Literal["comment", "share"]
BackfillOutcome = Literal["updated", "skipped", "no_recoverable_evidence", "dry_run"]


@dataclass(frozen=True)
class EngagementBackfillPlan:
    comment_count: int | None = None
    comment_count_text: str | None = None
    comment_count_source: str | None = None
    share_count: int | None = None
    share_count_text: str | None = None
    share_count_source: str | None = None


@dataclass(frozen=True)
class EngagementBackfillItemResult:
    item_id: UUID
    aweme_id: str | None
    outcome: BackfillOutcome
    comment_recovered: bool
    share_recovered: bool
    message: str


@dataclass(frozen=True)
class EngagementBackfillRunResult:
    capture_session_id: UUID | None = None
    profile_identifier: str | None = None
    scanned_count: int = 0
    candidate_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    no_evidence_count: int = 0
    dry_run: bool = False
    batch_size: int = 0
    sleep_ms: int = 0
    item_results: list[EngagementBackfillItemResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["item_results"] = [
            {
                **asdict(result),
                "item_id": str(result.item_id),
            }
            for result in self.item_results
        ]
        if payload.get("capture_session_id") is not None:
            payload["capture_session_id"] = str(payload["capture_session_id"])
        return payload


def item_needs_engagement_backfill(item: CapturedItem) -> bool:
    metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
    return metadata.get("comment_count") is None or metadata.get("share_count") is None


def build_engagement_backfill_plan(
    *,
    metadata: dict[str, Any],
    raw_payload: dict[str, Any],
    existing_comment_count: int | None,
    existing_share_count: int | None,
) -> EngagementBackfillPlan | None:
    comment = _recover_metric(
        metric="comment",
        existing_count=existing_comment_count,
        metadata=metadata,
        raw_payload=raw_payload,
    )
    share = _recover_metric(
        metric="share",
        existing_count=existing_share_count,
        metadata=metadata,
        raw_payload=raw_payload,
    )
    if comment is None and share is None:
        return None
    return EngagementBackfillPlan(
        comment_count=comment[0] if comment else None,
        comment_count_text=comment[1] if comment else None,
        comment_count_source=comment[2] if comment else None,
        share_count=share[0] if share else None,
        share_count_text=share[1] if share else None,
        share_count_source=share[2] if share else None,
    )


def apply_engagement_backfill_to_item(item: CapturedItem) -> EngagementBackfillItemResult:
    metadata = dict(item.metadata_json or {})
    raw_payload = item.raw_payload_json if isinstance(item.raw_payload_json, dict) else {}
    existing_comment = _non_negative_int(metadata.get("comment_count"))
    existing_share = _non_negative_int(metadata.get("share_count"))
    if not item_needs_engagement_backfill(item):
        return EngagementBackfillItemResult(
            item_id=item.id,
            aweme_id=_string_or_none(item.source_video_external_id),
            outcome="skipped",
            comment_recovered=False,
            share_recovered=False,
            message="engagement_counts_already_present",
        )

    plan = build_engagement_backfill_plan(
        metadata=metadata,
        raw_payload=raw_payload,
        existing_comment_count=existing_comment,
        existing_share_count=existing_share,
    )
    if plan is None:
        return EngagementBackfillItemResult(
            item_id=item.id,
            aweme_id=_string_or_none(item.source_video_external_id),
            outcome="no_recoverable_evidence",
            comment_recovered=False,
            share_recovered=False,
            message="no_stored_zero_evidence",
        )

    now = datetime.now(UTC).isoformat()
    if plan.comment_count is not None:
        metadata["comment_count"] = plan.comment_count
        if plan.comment_count_text is not None:
            metadata["comment_count_text"] = plan.comment_count_text
        if plan.comment_count_source is not None:
            metadata["comment_count_source"] = plan.comment_count_source
    if plan.share_count is not None:
        metadata["share_count"] = plan.share_count
        if plan.share_count_text is not None:
            metadata["share_count_text"] = plan.share_count_text
        if plan.share_count_source is not None:
            metadata["share_count_source"] = plan.share_count_source
    metadata["engagement_zero_backfill_at"] = now
    metadata["engagement_zero_backfill_source"] = "stored_evidence_replay"
    item.metadata_json = merge_hydrated_engagement_metadata(metadata, CapturedItemResponse.model_validate(item))
    return EngagementBackfillItemResult(
        item_id=item.id,
        aweme_id=_string_or_none(item.source_video_external_id),
        outcome="updated",
        comment_recovered=plan.comment_count is not None,
        share_recovered=plan.share_count is not None,
        message="engagement_zero_backfill_applied",
    )


def merge_hydrated_engagement_metadata(metadata: dict[str, Any], response: CapturedItemResponse) -> dict[str, Any]:
    merged = dict(metadata)
    for key in (
        "comment_count",
        "share_count",
        "comment_count_text",
        "share_count_text",
        "comment_count_source",
        "share_count_source",
        "favorite_count",
        "favorite_count_text",
        "engagement_score",
        "engagement_rate",
        "engagement_rate_basis",
        "has_comments",
        "has_shares",
        "has_all_core_metadata",
        "missing_metadata_fields",
        "metadata_status",
        "performance_status",
        "metadata_missing_reason",
        "performance_missing_reason",
    ):
        value = getattr(response, key, None)
        if value is not None or key in {"comment_count", "share_count", "has_comments", "has_shares", "has_all_core_metadata"}:
            merged[key] = value
    if response.missing_metadata_fields is not None:
        merged["missing_metadata_fields"] = list(response.missing_metadata_fields)
    return merged


class CaptureInboxEngagementBackfillService:
    def __init__(self, db: Session):
        self.db = db

    def backfill_capture_session(
        self,
        capture_session_id: UUID,
        *,
        limit: int | None = None,
        offset: int = 0,
        batch_size: int = 50,
        sleep_ms: int = 0,
        dry_run: bool = False,
    ) -> EngagementBackfillRunResult:
        stmt = (
            select(CapturedItem)
            .where(CapturedItem.capture_session_id == capture_session_id)
            .order_by(CapturedItem.raw_item_index.asc())
            .offset(max(0, offset))
        )
        if limit is not None:
            stmt = stmt.limit(max(1, limit))
        items = list(self.db.scalars(stmt).all())
        return self._backfill_loaded_items(
            items,
            capture_session_id=capture_session_id,
            profile_identifier=None,
            batch_size=batch_size,
            sleep_ms=sleep_ms,
            dry_run=dry_run,
        )

    def backfill_profile(
        self,
        profile_identifier: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        batch_size: int = 50,
        sleep_ms: int = 0,
        dry_run: bool = False,
        statuses: tuple[CapturedItemStatus, ...] | None = None,
    ) -> EngagementBackfillRunResult:
        allowed_statuses = statuses or (
            CapturedItemStatus.READY,
            CapturedItemStatus.ENRICHED,
            CapturedItemStatus.RAW,
            CapturedItemStatus.PREVIEW_MISSING,
            CapturedItemStatus.READY_FOR_REVIEW,
        )
        stmt = (
            select(CapturedItem)
            .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
            .where(
                CapturedItem.source_platform == SourcePlatformEnum.DOUYIN,
                CapturedItem.status.in_(allowed_statuses),
                or_(
                    CapturedItem.source_profile_external_id == profile_identifier,
                    CaptureSession.normalized_profile_identifier == profile_identifier,
                ),
            )
            .order_by(CapturedItem.updated_at.desc())
            .offset(max(0, offset))
        )
        if limit is not None:
            stmt = stmt.limit(max(1, limit))
        items = list(self.db.scalars(stmt).all())
        return self._backfill_loaded_items(
            items,
            capture_session_id=None,
            profile_identifier=profile_identifier,
            batch_size=batch_size,
            sleep_ms=sleep_ms,
            dry_run=dry_run,
        )

    def backfill_items(self, items: list[CapturedItem], *, dry_run: bool = False) -> list[EngagementBackfillItemResult]:
        results: list[EngagementBackfillItemResult] = []
        for item in items:
            if not item_needs_engagement_backfill(item):
                results.append(
                    EngagementBackfillItemResult(
                        item_id=item.id,
                        aweme_id=_string_or_none(item.source_video_external_id),
                        outcome="skipped",
                        comment_recovered=False,
                        share_recovered=False,
                        message="engagement_counts_already_present",
                    )
                )
                continue
            if dry_run:
                plan = build_engagement_backfill_plan(
                    metadata=dict(item.metadata_json or {}),
                    raw_payload=item.raw_payload_json if isinstance(item.raw_payload_json, dict) else {},
                    existing_comment_count=_non_negative_int((item.metadata_json or {}).get("comment_count")),
                    existing_share_count=_non_negative_int((item.metadata_json or {}).get("share_count")),
                )
                if plan is None:
                    results.append(
                        EngagementBackfillItemResult(
                            item_id=item.id,
                            aweme_id=_string_or_none(item.source_video_external_id),
                            outcome="no_recoverable_evidence",
                            comment_recovered=False,
                            share_recovered=False,
                            message="no_stored_zero_evidence",
                        )
                    )
                else:
                    results.append(
                        EngagementBackfillItemResult(
                            item_id=item.id,
                            aweme_id=_string_or_none(item.source_video_external_id),
                            outcome="dry_run",
                            comment_recovered=plan.comment_count is not None,
                            share_recovered=plan.share_count is not None,
                            message="would_apply_engagement_zero_backfill",
                        )
                    )
                continue
            results.append(apply_engagement_backfill_to_item(item))
            self.db.add(item)
        if not dry_run and any(result.outcome == "updated" for result in results):
            self.db.commit()
        return results

    def _backfill_loaded_items(
        self,
        items: list[CapturedItem],
        *,
        capture_session_id: UUID | None,
        profile_identifier: str | None,
        batch_size: int,
        sleep_ms: int,
        dry_run: bool,
    ) -> EngagementBackfillRunResult:
        candidates = [item for item in items if item_needs_engagement_backfill(item)]
        results: list[EngagementBackfillItemResult] = []
        effective_batch_size = max(1, batch_size)
        for index in range(0, len(candidates), effective_batch_size):
            batch = candidates[index : index + effective_batch_size]
            results.extend(self.backfill_items(batch, dry_run=dry_run))
            if sleep_ms > 0 and index + effective_batch_size < len(candidates):
                time.sleep(sleep_ms / 1000.0)
        updated_count = sum(1 for result in results if result.outcome == "updated")
        skipped_count = sum(1 for result in results if result.outcome == "skipped")
        no_evidence_count = sum(1 for result in results if result.outcome == "no_recoverable_evidence")
        return EngagementBackfillRunResult(
            capture_session_id=capture_session_id,
            profile_identifier=profile_identifier,
            scanned_count=len(items),
            candidate_count=len(candidates),
            updated_count=updated_count,
            skipped_count=skipped_count,
            no_evidence_count=no_evidence_count,
            dry_run=dry_run,
            batch_size=effective_batch_size,
            sleep_ms=max(0, sleep_ms),
            item_results=results,
        )


def resolve_engagement_count_for_display(
    *,
    metric: EngagementMetric,
    existing_count: int | None,
    metadata: dict[str, Any],
    raw_payload: dict[str, Any],
) -> int | None:
    recovered = _recover_metric(
        metric=metric,
        existing_count=existing_count,
        metadata=metadata,
        raw_payload=raw_payload,
    )
    if recovered is None:
        return existing_count
    return recovered[0]


def _recover_metric(
    *,
    metric: EngagementMetric,
    existing_count: int | None,
    metadata: dict[str, Any],
    raw_payload: dict[str, Any],
) -> tuple[int, str | None, str] | None:
    if existing_count is not None:
        return None

    statistics_value, statistics_source = _recover_from_statistics(metric, metadata, raw_payload)
    if statistics_value is not None:
        return statistics_value, None, statistics_source

    for container in (
        metadata,
        raw_payload,
        _record(metadata.get("raw_dom_detail_metrics")),
        _record(raw_payload.get("raw_dom_detail_metrics")),
    ):
        if not container:
            continue
        text = _first_string(
            container,
            f"{metric}_count_text",
            f"{metric}_text",
        )
        parsed, parsed_source = _parse_metric_text(
            metric,
            text,
            dom_context=isinstance(container.get("extraction_source"), str) or text in {"抢首评", "分享"},
        )
        if parsed is not None:
            return parsed, text, parsed_source

    dom_metrics = _record(metadata.get("raw_dom_detail_metrics")) or _record(raw_payload.get("raw_dom_detail_metrics"))
    if dom_metrics:
        dom_count = _non_negative_int(dom_metrics.get(f"{metric}_count"))
        if dom_count is not None:
            source = _string_or_none(dom_metrics.get(f"{metric}_count_source")) or "dom_detail_modal"
            text = _first_string(dom_metrics, f"{metric}_count_text")
            return dom_count, text, source

    return None


def _recover_from_statistics(
    metric: EngagementMetric,
    metadata: dict[str, Any],
    raw_payload: dict[str, Any],
) -> tuple[int | None, str]:
    key = "comment_count" if metric == "comment" else "share_count"
    for aweme, source in (
        (_record(metadata.get("raw_network_aweme")), "network_json"),
        (_record(metadata.get("raw_detail_aweme")), "detail_hydrate"),
        (_record(raw_payload.get("raw_network_aweme")), "network_json"),
        (_record(raw_payload.get("raw_detail_aweme")), "detail_hydrate"),
        (_record(raw_payload.get("statistics")), "network_json"),
        (_record(metadata.get("statistics")), "network_json"),
    ):
        if not aweme:
            continue
        stats = _record(aweme.get("statistics")) or aweme
        value = _non_negative_int(stats.get(key))
        if value is not None:
            return value, source
    return None, "missing"


def _parse_metric_text(metric: EngagementMetric, text: str | None, *, dom_context: bool) -> tuple[int | None, str]:
    if not text:
        return None, "missing"
    numeric = normalize_douyin_count(text)
    if numeric is not None:
        return numeric, "existing_canonical"
    share_icon_context = dom_context or text.strip() == "分享"
    zero = normalize_douyin_engagement_count(
        metric,
        None,
        text,
        share_icon_context=share_icon_context,
    )
    if zero == 0:
        return 0, "dom_zero_sentinel"
    return None, "missing"


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _first_string(container: dict[str, Any] | None, *keys: str) -> str | None:
    if not container:
        return None
    for key in keys:
        value = container.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _non_negative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
