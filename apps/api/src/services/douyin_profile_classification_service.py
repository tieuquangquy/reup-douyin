from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import CapturedItemStatus, SourcePlatformEnum, SourceVideoStatus
from src.models.capture_inbox import CapturedItem
from src.models.ingestion import SourceVideo

from src.schemas.douyin_extension import (
    DouyinProfileClassificationCounts,
    DouyinProfileVideoCandidate,
    DouyinProfileVideoClassificationResponse,
    DouyinProfileVideoClassificationStatus,
    DouyinProfileVideoClassificationTarget,
)

REQUIRED_DOUYIN_PROFILE_DETAIL_FIELDS = ("duration", "like_count", "comment_count", "favorite_count", "share_count")
CONTRACT_ONLY_DATABASE_LOOKUP_STATUS = "not_implemented_contract_only"
DATABASE_LOOKUP_STATUS_OK = "ok"


def build_douyin_profile_video_classification_response(
    *,
    db: Session,
    profile_url: str,
    sec_uid: str | None,
    collection_mode: str,
    candidates: list[DouyinProfileVideoCandidate],
    include_unknown: bool = False,
) -> DouyinProfileVideoClassificationResponse:
    candidate_aweme_ids = [_candidate_value(candidate, "aweme_id") for candidate in candidates]
    existing_index = lookup_existing_douyin_video_index(
        db=db,
        candidate_aweme_ids=[str(value or "") for value in candidate_aweme_ids],
        profile_url=profile_url,
        sec_uid=sec_uid,
    )
    result = classify_douyin_profile_candidates(
        candidates,
        existing_index=existing_index,
        collection_mode=collection_mode,
        include_unknown=include_unknown,
    )
    diagnostics = {
        **result["diagnostics"],
        "contract_only": False,
        "db_lookup_enabled": True,
        "lookup_candidate_count": len({str(value or "").strip() for value in candidate_aweme_ids if str(value or "").strip()}),
        "existing_match_count": len(existing_index),
        "profile_scope": "profile_url" if profile_url else ("aweme_id_global" if candidate_aweme_ids else "unknown"),
        "read_only": True,
    }
    return DouyinProfileVideoClassificationResponse(
        profile_url=profile_url,
        sec_uid=sec_uid,
        collection_mode=collection_mode,
        database_lookup_status=DATABASE_LOOKUP_STATUS_OK,
        total_candidates=len(candidates),
        counts=result["counts"],
        targets=result["targets"],
        collect_aweme_ids=result["collect_aweme_ids"],
        skip_aweme_ids=result["skip_aweme_ids"],
        diagnostics=diagnostics,
    )


def lookup_existing_douyin_video_index(
    *,
    db: Session,
    candidate_aweme_ids: list[str],
    profile_url: str | None = None,
    sec_uid: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Read existing Douyin Capture Inbox and canonical video records by external video id."""
    aweme_ids = _unique_nonempty_strings(candidate_aweme_ids)
    if not aweme_ids:
        return {}

    index: dict[str, dict[str, Any]] = {}
    capture_rows = list(
        db.scalars(
            select(CapturedItem).where(
                CapturedItem.source_platform == SourcePlatformEnum.DOUYIN,
                CapturedItem.source_video_external_id.in_(aweme_ids),
            )
        )
    )
    for item in capture_rows:
        aweme_id = _string_or_none(getattr(item, "source_video_external_id", None))
        if not aweme_id:
            continue
        record = map_capture_inbox_item_to_classification_record(item)
        index[aweme_id] = _prefer_classification_record(index.get(aweme_id), record, profile_url=profile_url)

    source_rows = list(
        db.scalars(
            select(SourceVideo).where(
                SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                SourceVideo.source_video_external_id.in_(aweme_ids),
            )
        )
    )
    for video in source_rows:
        aweme_id = _string_or_none(getattr(video, "source_video_external_id", None))
        if not aweme_id:
            continue
        record = map_source_video_to_classification_record(video)
        index[aweme_id] = _prefer_classification_record(index.get(aweme_id), record, profile_url=profile_url)

    return index


def map_capture_inbox_item_to_classification_record(item: Any) -> dict[str, Any]:
    metadata = getattr(item, "metadata_json", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    status = getattr(item, "status", None)
    metadata_status = _metadata_status_from_capture_item(status=status, metadata=metadata)
    return {
        "id": _string_or_none(getattr(item, "id", None)),
        "record_source": "capture_inbox",
        "aweme_id": _string_or_none(getattr(item, "source_video_external_id", None)),
        "source_video_external_id": _string_or_none(getattr(item, "source_video_external_id", None)),
        "profile_url": _string_or_none(getattr(item, "profile_url", None)),
        "metadata_status": metadata_status,
        "review_status": _string_or_none(metadata.get("review_status")) or "capture_inbox",
        "duration_seconds": getattr(item, "duration_seconds", None),
        "duration_text": metadata.get("duration_text"),
        "like_count": metadata.get("like_count"),
        "comment_count": metadata.get("comment_count"),
        "favorite_count": metadata.get("favorite_count"),
        "share_count": metadata.get("share_count"),
        "view_count": metadata.get("view_count"),
        "thumbnail_url": _string_or_none(getattr(item, "thumbnail_url", None)),
        "caption": _string_or_none(getattr(item, "caption", None)),
        "source_url": _string_or_none(getattr(item, "source_url", None)),
        "updated_at": getattr(item, "updated_at", None),
        "created_at": getattr(item, "created_at", None),
    }


def map_source_video_to_classification_record(video: Any) -> dict[str, Any]:
    metadata = getattr(video, "metadata_json", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    status = getattr(video, "status", None)
    metadata_status = "failed" if status == SourceVideoStatus.FAILED or str(status) == "FAILED" else _string_or_none(metadata.get("metadata_status")) or "ready"
    return {
        "id": _string_or_none(getattr(video, "id", None)),
        "record_source": "source_video",
        "aweme_id": _string_or_none(getattr(video, "source_video_external_id", None)),
        "source_video_external_id": _string_or_none(getattr(video, "source_video_external_id", None)),
        "profile_url": _string_or_none(metadata.get("profile_url")),
        "metadata_status": metadata_status,
        "review_status": _string_or_none(metadata.get("review_status")) or "canonical_source_video",
        "duration_seconds": getattr(video, "duration_seconds", None),
        "duration_text": metadata.get("duration_text"),
        "like_count": metadata.get("like_count"),
        "comment_count": metadata.get("comment_count"),
        "favorite_count": metadata.get("favorite_count"),
        "share_count": metadata.get("share_count"),
        "view_count": metadata.get("view_count"),
        "thumbnail_url": _string_or_none(metadata.get("thumbnail_url")),
        "caption": _string_or_none(getattr(video, "caption", None)),
        "source_url": _string_or_none(getattr(video, "source_url", None)),
        "updated_at": getattr(video, "updated_at", None),
        "created_at": getattr(video, "created_at", None),
    }


def classify_douyin_profile_candidates(
    candidates: list[DouyinProfileVideoCandidate] | list[Any],
    existing_index: dict[str, Any] | None,
    collection_mode: str,
    include_unknown: bool = False,
) -> dict[str, Any]:
    """Classify profile-scan candidate videos without mutating persistence state."""
    index = existing_index or {}
    counts: dict[str, int] = {
        "new": 0,
        "incomplete": 0,
        "complete": 0,
        "failed": 0,
        "skipped": 0,
        "unknown": 0,
        "collect": 0,
        "skip": 0,
    }
    targets: list[DouyinProfileVideoClassificationTarget] = []
    collect_aweme_ids: list[str] = []
    skip_aweme_ids: list[str] = []
    seen_aweme_ids: set[str] = set()
    duplicate_candidate_count = 0
    invalid_candidate_count = 0

    for candidate in candidates:
        aweme_id = _candidate_value(candidate, "aweme_id")
        aweme_id = str(aweme_id or "").strip()
        if aweme_id and aweme_id in seen_aweme_ids:
            duplicate_candidate_count += 1
            continue
        if aweme_id:
            seen_aweme_ids.add(aweme_id)

        if not aweme_id:
            invalid_candidate_count += 1
            classification: DouyinProfileVideoClassificationStatus = "unknown"
            reason = "invalid_aweme_id"
            missing_fields: list[str] = []
            existing = None
        else:
            existing = index.get(aweme_id)
            classification, reason, missing_fields = _classify_existing_record(existing)

        collect = _should_collect(classification, collection_mode, include_unknown=include_unknown)
        counts[classification] += 1
        counts["collect" if collect else "skip"] += 1
        if collect:
            collect_aweme_ids.append(aweme_id)
        else:
            skip_aweme_ids.append(aweme_id)

        target = DouyinProfileVideoClassificationTarget(
            aweme_id=aweme_id,
            classification=classification,
            collect=collect,
            reason=reason,
            required_missing_fields=missing_fields,
            existing_item_id=_string_or_none(_record_value(existing, "id")) if existing is not None else None,
            metadata_status=_string_or_none(_record_value(existing, "metadata_status")) if existing is not None else ("new" if classification == "new" else None),
            review_status=_string_or_none(_record_value(existing, "review_status")) if existing is not None else ("pending_review" if classification == "new" else None),
            video_url=_string_or_none(_candidate_value(candidate, "video_url")),
            source_url=_string_or_none(_candidate_value(candidate, "source_url")),
            thumbnail_url=_string_or_none(_candidate_value(candidate, "thumbnail_url")),
            caption=_string_or_none(_candidate_value(candidate, "caption")),
        )
        targets.append(target)

    return {
        "counts": DouyinProfileClassificationCounts(**counts),
        "targets": targets,
        "collect_aweme_ids": collect_aweme_ids,
        "skip_aweme_ids": skip_aweme_ids,
        "diagnostics": {
            "contract_only": True,
            "db_lookup_enabled": False,
            "duplicate_candidate_count": duplicate_candidate_count,
            "invalid_candidate_count": invalid_candidate_count,
        },
    }


def classify_douyin_profile_candidates_contract_only(
    *,
    profile_url: str,
    sec_uid: str | None,
    collection_mode: str,
    candidates: list[DouyinProfileVideoCandidate],
    include_unknown: bool = False,
) -> DouyinProfileVideoClassificationResponse:
    result = classify_douyin_profile_candidates(
        candidates,
        existing_index={},
        collection_mode=collection_mode,
        include_unknown=include_unknown,
    )
    return DouyinProfileVideoClassificationResponse(
        profile_url=profile_url,
        sec_uid=sec_uid,
        collection_mode=collection_mode,
        database_lookup_status=CONTRACT_ONLY_DATABASE_LOOKUP_STATUS,
        total_candidates=len(candidates),
        counts=result["counts"],
        targets=result["targets"],
        collect_aweme_ids=result["collect_aweme_ids"],
        skip_aweme_ids=result["skip_aweme_ids"],
        diagnostics=result["diagnostics"],
    )


def _classify_existing_record(existing: Any) -> tuple[DouyinProfileVideoClassificationStatus, str, list[str]]:
    if existing is None:
        return "new", "not_found_in_existing_index", []

    metadata_status = str(_record_value(existing, "metadata_status") or "").strip().lower()
    if metadata_status in {"failed", "error"}:
        return "failed", "previous_collect_failed", []
    if metadata_status == "skipped":
        return "skipped", "previously_skipped", []

    missing_fields = _missing_required_fields(existing)
    if not missing_fields:
        return "complete", "already_complete", []
    return "incomplete", "missing_required_metadata", missing_fields


def _missing_required_fields(existing: Any) -> list[str]:
    missing: list[str] = []
    duration_seconds = _record_value(existing, "duration_seconds")
    duration_text = str(_record_value(existing, "duration_text") or "").strip()
    if duration_seconds is None and not duration_text:
        missing.append("duration")
    for field in ("like_count", "comment_count", "favorite_count", "share_count"):
        if _record_value(existing, field) is None:
            missing.append(field)
    return missing


def _should_collect(classification: str, collection_mode: str, *, include_unknown: bool) -> bool:
    if classification == "unknown":
        return include_unknown and collection_mode != "failed_only"
    if classification == "skipped":
        return False
    if collection_mode in {"new_incomplete_failed", "new_and_incomplete"}:
        return classification in {"new", "incomplete", "failed"}
    if collection_mode == "new_only":
        return classification == "new"
    if collection_mode == "failed_only":
        return classification == "failed"
    if collection_mode == "refresh_all":
        return classification in {"new", "incomplete", "failed", "complete"}
    return classification in {"new", "incomplete", "failed"}


def _candidate_value(candidate: Any, field: str) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _record_value(record: Any, field: str) -> Any:
    if record is None:
        return None
    if isinstance(record, dict):
        if field in record:
            return record.get(field)
        metadata = record.get("metadata_json")
        return metadata.get(field) if isinstance(metadata, dict) else None
    value = getattr(record, field, None)
    if value is not None:
        return value
    metadata = getattr(record, "metadata_json", None)
    return metadata.get(field) if isinstance(metadata, dict) else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unique_nonempty_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            results.append(text)
    return results


def _metadata_status_from_capture_item(*, status: Any, metadata: dict[str, Any]) -> str:
    explicit = _string_or_none(metadata.get("metadata_status"))
    if explicit:
        return explicit
    if status == CapturedItemStatus.FAILED or str(status) == "FAILED":
        return "failed"
    if status == CapturedItemStatus.EXCLUDED or str(status) == "EXCLUDED":
        return "skipped"
    if status == CapturedItemStatus.DUPLICATE or str(status) == "DUPLICATE":
        return "skipped"
    return "ready"


def _prefer_classification_record(existing: dict[str, Any] | None, candidate: dict[str, Any], *, profile_url: str | None) -> dict[str, Any]:
    if existing is None:
        return candidate
    existing_score = _record_preference_score(existing, profile_url=profile_url)
    candidate_score = _record_preference_score(candidate, profile_url=profile_url)
    return candidate if candidate_score > existing_score else existing


def _record_preference_score(record: dict[str, Any], *, profile_url: str | None) -> tuple[int, int, int, str]:
    classification, _, _ = _classify_existing_record(record)
    classification_rank = {"complete": 5, "failed": 4, "incomplete": 3, "skipped": 2, "unknown": 1, "new": 0}.get(classification, 0)
    profile_rank = 1 if profile_url and _string_or_none(record.get("profile_url")) == profile_url else 0
    source_rank = 1 if record.get("record_source") == "capture_inbox" else 0
    timestamp = _string_or_none(record.get("updated_at") or record.get("created_at")) or ""
    return classification_rank, profile_rank, source_rank, timestamp
