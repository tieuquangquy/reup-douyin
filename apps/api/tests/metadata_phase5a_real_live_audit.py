from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.settings import get_settings
from src.db.session import get_session_factory
from src.models.capture_inbox import CapturedItem, CaptureSession
from src.schemas.capture_inbox import CapturedItemResponse


KNOWN_METADATA_STATUSES = ("complete", "partial", "missing", "pending_hydration", "failed")
UNKNOWN_STATUS_KEY = "unknown/null"


@dataclass(frozen=True)
class CoverageRow:
    present: int
    total: int
    pct: float


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _coverage(present: int, total: int) -> CoverageRow:
    return CoverageRow(
        present=present,
        total=total,
        pct=round((present / total) * 100, 1) if total else 0.0,
    )


def _classify_usability(pct: float, *, usable_threshold: float, partial_threshold: float) -> str:
    if pct >= usable_threshold:
        return "usable"
    if pct >= partial_threshold:
        return "partial"
    return "not usable"


def _captured_group_count(item: CapturedItemResponse) -> int:
    return sum(
        status == "captured"
        for status in (item.time_status, item.performance_status, item.processing_fit_status)
    )


def _evidence_score(item: CapturedItemResponse) -> int:
    summary = item.raw_evidence_summary or {}
    return sum(
        1
        for key in ("has_network_aweme", "has_detail_aweme", "has_dom_snapshot")
        if summary.get(key) is True
    )


def _item_sort_key(item: CapturedItemResponse) -> tuple[int, int, int, int, int]:
    return (
        _captured_group_count(item),
        _evidence_score(item),
        int(item.view_count is not None or item.like_count is not None),
        int(item.duration_seconds is not None or _is_present(item.duration_text)),
        int(item.posted_at is not None or _is_present(item.posted_text)),
    )


def _metadata_status_distribution(items: list[CapturedItemResponse]) -> dict[str, int]:
    counts = Counter()
    for item in items:
        status = item.metadata_status if item.metadata_status in KNOWN_METADATA_STATUSES else UNKNOWN_STATUS_KEY
        counts[status] += 1
    for key in (*KNOWN_METADATA_STATUSES, UNKNOWN_STATUS_KEY):
        counts.setdefault(key, 0)
    return dict(counts)


def _field_coverage(items: list[CapturedItemResponse]) -> dict[str, dict[str, Any]]:
    total = len(items)
    coverage_rows = {
        "posted_at": _coverage(sum(item.posted_at is not None for item in items), total),
        "posted_text": _coverage(sum(_is_present(item.posted_text) for item in items), total),
        "time_status_captured": _coverage(sum(item.time_status == "captured" for item in items), total),
        "duration_seconds": _coverage(sum(item.duration_seconds is not None for item in items), total),
        "duration_text": _coverage(sum(_is_present(item.duration_text) for item in items), total),
        "processing_fit_status_captured": _coverage(sum(item.processing_fit_status == "captured" for item in items), total),
        "view_count": _coverage(sum(item.view_count is not None for item in items), total),
        "like_count": _coverage(sum(item.like_count is not None for item in items), total),
        "comment_count": _coverage(sum(item.comment_count is not None for item in items), total),
        "share_count": _coverage(sum(item.share_count is not None for item in items), total),
        "engagement_rate": _coverage(sum(item.engagement_rate is not None for item in items), total),
        "performance_status_captured": _coverage(sum(item.performance_status == "captured" for item in items), total),
    }
    return {key: asdict(value) for key, value in coverage_rows.items()}


def _raw_evidence_coverage(items: list[CapturedItemResponse], orm_items: dict[UUID, CapturedItem]) -> dict[str, dict[str, Any]]:
    total = len(items)

    def metadata_dict(item_id: UUID) -> dict[str, Any]:
        metadata = orm_items[item_id].metadata_json
        return metadata if isinstance(metadata, dict) else {}

    rows = {
        "raw_network_aweme": _coverage(
            sum(isinstance(metadata_dict(item.id).get("raw_network_aweme"), dict) for item in items),
            total,
        ),
        "raw_detail_aweme": _coverage(
            sum(isinstance(metadata_dict(item.id).get("raw_detail_aweme"), dict) for item in items),
            total,
        ),
        "raw_dom_snapshot": _coverage(
            sum(isinstance(metadata_dict(item.id).get("raw_dom_snapshot"), dict) for item in items),
            total,
        ),
        "raw_dom_detail_metrics": _coverage(
            sum(isinstance(metadata_dict(item.id).get("raw_dom_detail_metrics"), dict) for item in items),
            total,
        ),
        "raw_evidence_summary": _coverage(sum(isinstance(item.raw_evidence_summary, dict) for item in items), total),
        "raw_evidence_summary.has_network_aweme": _coverage(
            sum((item.raw_evidence_summary or {}).get("has_network_aweme") is True for item in items),
            total,
        ),
        "raw_evidence_summary.has_detail_aweme": _coverage(
            sum((item.raw_evidence_summary or {}).get("has_detail_aweme") is True for item in items),
            total,
        ),
        "raw_evidence_summary.has_dom_snapshot": _coverage(
            sum((item.raw_evidence_summary or {}).get("has_dom_snapshot") is True for item in items),
            total,
        ),
        "raw_evidence_summary.has_dom_detail_metrics": _coverage(
            sum((item.raw_evidence_summary or {}).get("has_dom_detail_metrics") is True for item in items),
            total,
        ),
    }
    return {key: asdict(value) for key, value in rows.items()}


def _diagnostic_record(label: str, item: CapturedItemResponse) -> dict[str, Any]:
    return {
        "label": label,
        "item_id": str(item.id),
        "aweme_id": item.aweme_id,
        "source_video_external_id": item.source_video_external_id,
        "metadata_status": item.metadata_status,
        "time_status": item.time_status,
        "time_missing_reason": item.time_missing_reason,
        "performance_status": item.performance_status,
        "performance_missing_reason": item.performance_missing_reason,
        "processing_fit_status": item.processing_fit_status,
        "processing_fit_missing_reason": item.processing_fit_missing_reason,
        "posted_at": item.posted_at.isoformat() if item.posted_at else None,
        "posted_text": item.posted_text,
        "duration_seconds": item.duration_seconds,
        "duration_text": item.duration_text,
        "view_count": item.view_count,
        "like_count": item.like_count,
        "comment_count": item.comment_count,
        "share_count": item.share_count,
        "raw_evidence_summary": item.raw_evidence_summary,
    }


def _sample_diagnostics(items: list[CapturedItemResponse]) -> list[dict[str, Any]]:
    if not items:
        return []
    samples: list[dict[str, Any]] = []
    used: set[UUID] = set()
    sorted_items = sorted(items, key=_item_sort_key, reverse=True)

    def add_first(label: str, predicate) -> None:
        for item in sorted_items:
            if item.id in used:
                continue
            if predicate(item):
                used.add(item.id)
                samples.append(_diagnostic_record(label, item))
                return

    add_first("best_metadata_item", lambda item: True)
    add_first("complete_item", lambda item: item.metadata_status == "complete")
    add_first("partial_item", lambda item: item.metadata_status == "partial")
    add_first("needs_metadata_item", lambda item: item.metadata_status in {"missing", "pending_hydration"})
    add_first("failed_item", lambda item: item.metadata_status == "failed")

    for item in sorted_items:
        if len(samples) >= 5:
            break
        if item.id in used:
            continue
        used.add(item.id)
        samples.append(_diagnostic_record("additional_sample", item))
    return samples


def run_live_audit() -> dict[str, Any]:
    settings = get_settings()
    parsed_url = urlparse(settings.database_url)
    session_factory = get_session_factory()
    with session_factory() as db:
        total_sessions = db.execute(select(func.count()).select_from(CaptureSession)).scalar_one()
        total_items = db.execute(select(func.count()).select_from(CapturedItem)).scalar_one()
        latest_session = db.execute(
            select(CaptureSession)
            .options(selectinload(CaptureSession.items))
            .order_by(CaptureSession.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        source_summary = {
            "settings_source": "apps/api/.env",
            "database_kind": "postgresql" if settings.database_url.startswith(("postgresql://", "postgresql+psycopg://")) else "other",
            "database_host": parsed_url.hostname,
            "database_port": parsed_url.port,
            "database_name": parsed_url.path.lstrip("/") or None,
            "capture_sessions_total": total_sessions,
            "captured_items_total": total_items,
        }

        if latest_session is None or not latest_session.items:
            return {
                "status": "LIVE_DATA_NOT_FOUND",
                "source": source_summary,
                "latest_session_id": str(latest_session.id) if latest_session else None,
                "latest_session_item_count": len(latest_session.items) if latest_session else 0,
                "operator_action": (
                    "Start the local backend against apps/api/.env, open Capture Inbox in the Douyin extension, "
                    "capture a real profile session, then rerun this audit."
                ),
            }

        responses = [CapturedItemResponse.model_validate(item) for item in latest_session.items]
        orm_items = {item.id: item for item in latest_session.items}

        field_coverage = _field_coverage(responses)
        raw_evidence_coverage = _raw_evidence_coverage(responses, orm_items)

        time_present_pct = round(
            (
                sum(item.posted_at is not None or _is_present(item.posted_text) for item in responses)
                / len(responses)
            )
            * 100,
            1,
        )
        processing_fit_present_pct = round(
            (
                sum(item.duration_seconds is not None or _is_present(item.duration_text) for item in responses)
                / len(responses)
            )
            * 100,
            1,
        )
        performance_present_pct = round(
            (
                sum(item.view_count is not None or item.like_count is not None for item in responses)
                / len(responses)
            )
            * 100,
            1,
        )

        verdict = {
            "time": {
                "coverage_pct": time_present_pct,
                "classification": _classify_usability(time_present_pct, usable_threshold=80.0, partial_threshold=50.0),
            },
            "performance": {
                "coverage_pct": performance_present_pct,
                "classification": _classify_usability(performance_present_pct, usable_threshold=70.0, partial_threshold=40.0),
            },
            "processing_fit": {
                "coverage_pct": processing_fit_present_pct,
                "classification": _classify_usability(processing_fit_present_pct, usable_threshold=80.0, partial_threshold=50.0),
            },
        }

        return {
            "status": "LIVE_DATA_FOUND",
            "source": source_summary,
            "latest_session_id": str(latest_session.id),
            "latest_capture_id": latest_session.capture_id,
            "latest_session_status": latest_session.status.value if hasattr(latest_session.status, "value") else str(latest_session.status),
            "latest_session_created_at": latest_session.created_at.isoformat(),
            "total_live_items": len(responses),
            "metadata_status_distribution": _metadata_status_distribution(responses),
            "field_coverage": field_coverage,
            "raw_evidence_coverage": raw_evidence_coverage,
            "sample_item_diagnostics": _sample_diagnostics(responses),
            "usability_verdict": verdict,
        }


def main() -> None:
    report = run_live_audit()
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
