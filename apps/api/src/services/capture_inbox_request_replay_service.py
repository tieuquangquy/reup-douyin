from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.models.capture_inbox import CaptureSession, CapturedItem
from src.services.capture_inbox_metadata_hydration_service import (
    CaptureInboxMetadataHydrationError,
    CaptureInboxMetadataHydrationService,
    _float_or_none,
    _int_or_none,
    _normalize_aweme_id,
    _string_or_none,
)
from src.services.capture_metadata_normalizer import CaptureMetadataNormalizeInput, CaptureMetadataNormalizer
from src.services.douyin_browser_context_registry import douyin_browser_context_registry

logger = logging.getLogger(__name__)

_AWEME_USEFUL_KEYS = {
    "aweme_id",
    "create_time",
    "statistics",
    "video",
    "desc",
    "author",
    "share_info",
    "text_extra",
    "music",
}
_SECRET_MARKERS = ("cookie", "token", "authorization", "credential", "csrf", "mstoken", "header")
_CAPTCHA_OR_BLOCK_MARKERS = (
    "captcha",
    "verify",
    "security check",
    "challenge",
    "验证",
    "安全验证",
    "请完成验证",
    "抖音安全中心",
    "login required",
)
_CURSOR_KEYS = ("cursor", "max_cursor", "min_cursor", "offset", "page")


class CaptureInboxRequestReplayError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class DouyinReplayCandidate:
    request_url: str
    request_method: str
    request_headers: dict[str, str]
    request_post_data: str | None
    matched_aweme_count: int
    has_statistics_count: int
    has_duration_count: int
    sample_aweme_ids: list[str]
    response_shape_summary: str
    cursor_fields: dict[str, Any]
    request_cursor_param_name: str | None

    def public_summary(self) -> dict[str, Any]:
        return {
            "request_url": request_url_without_query_secrets(self.request_url),
            "request_method": self.request_method,
            "matched_aweme_count": self.matched_aweme_count,
            "has_statistics_count": self.has_statistics_count,
            "has_duration_count": self.has_duration_count,
            "sample_aweme_ids": self.sample_aweme_ids[:5],
            "response_shape_summary": self.response_shape_summary,
            "cursor_fields": self.cursor_fields,
            "request_cursor_param_name": self.request_cursor_param_name,
        }


@dataclass(frozen=True)
class CaptureInboxRequestReplayResult:
    capture_session_id: UUID
    selected_account_id: UUID
    selected_fetch_path: str
    candidate_request_count: int
    best_candidate: dict[str, Any] | None
    aweme_seen_count: int
    aweme_with_statistics_count: int
    aweme_with_duration_count: int
    matched_count: int
    updated_count: int
    duration_updated_count: int
    performance_updated_count: int
    pages_replayed_count: int
    max_pages_requested: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": True,
            "capture_session_id": str(self.capture_session_id),
            "selected_account_id": str(self.selected_account_id),
            "selected_fetch_path": self.selected_fetch_path,
            "candidate_request_count": self.candidate_request_count,
            "best_candidate": self.best_candidate,
            "aweme_seen_count": self.aweme_seen_count,
            "aweme_with_statistics_count": self.aweme_with_statistics_count,
            "aweme_with_duration_count": self.aweme_with_duration_count,
            "matched_count": self.matched_count,
            "updated_count": self.updated_count,
            "duration_updated_count": self.duration_updated_count,
            "performance_updated_count": self.performance_updated_count,
            "pages_replayed_count": self.pages_replayed_count,
            "max_pages_requested": self.max_pages_requested,
        }


class CaptureInboxRequestReplayService:
    def __init__(self, db: Session):
        self.db = db
        self._normalizer = CaptureMetadataNormalizer()
        self._hydration_service = CaptureInboxMetadataHydrationService(db)

    def discover_and_replay(
        self,
        capture_session_id: UUID,
        *,
        account_connection_id: UUID | None = None,
        max_pages: int = 3,
        delay_seconds: float = 2.0,
        timeout_seconds: float = 20.0,
    ) -> CaptureInboxRequestReplayResult:
        session = self._get_capture_session(capture_session_id)
        account, preflight = self._hydration_service._resolve_browser_backed_account(
            workspace_id=session.workspace_id,
            requested_account_id=account_connection_id,
        )
        if preflight.preflight_result != "passed" or preflight.selected_fetch_path != "browser_profile":
            raise CaptureInboxRequestReplayError(
                preflight.preflight_failure_code or "browser_profile_not_ready",
                preflight.preflight_failure_message or "Browser-backed Douyin account is not ready for request replay.",
            )
        candidates = [item for item in session.items if item.source_video_external_id]
        try:
            self._hydration_service._ensure_browser_context_for_hydration(
                account=account,
                total_items_considered=len(candidates),
            )
        except CaptureInboxMetadataHydrationError as exc:
            raise CaptureInboxRequestReplayError(exc.code, exc.message, details=dict(exc.details)) from exc
        profile_url = self._profile_url_for_session(session)
        fetch_result = douyin_browser_context_registry.fetch_profile_page(
            account.id,
            profile_url=profile_url,
            timeout_ms=max(5_000, int(timeout_seconds * 1000)),
            settle_seconds=2,
            scroll_passes=4,
        )
        if not fetch_result.available:
            raise CaptureInboxRequestReplayError(
                "browser_context_unavailable",
                fetch_result.reason or fetch_result.status or "Browser profile page fetch was unavailable.",
            )

        candidate_requests = detect_candidate_requests(fetch_result.response_records)
        if not candidate_requests:
            raise CaptureInboxRequestReplayError(
                "no_aweme_list_request_found",
                "No aweme-list request was detected from the profile/feed page.",
                details={"profile_url": profile_url},
            )
        best_candidate = choose_best_candidate(candidate_requests)
        aweme_map, replay_summary = self._replay_candidate_request(
            account_id=account.id,
            candidate=best_candidate,
            max_pages=max_pages,
            delay_seconds=delay_seconds,
            timeout_seconds=timeout_seconds,
        )
        update_summary = self._batch_update_items_from_network_awemes(session, aweme_map)
        return CaptureInboxRequestReplayResult(
            capture_session_id=session.id,
            selected_account_id=account.id,
            selected_fetch_path=preflight.selected_fetch_path or "browser_profile",
            candidate_request_count=len(candidate_requests),
            best_candidate=best_candidate.public_summary(),
            aweme_seen_count=replay_summary["aweme_seen_count"],
            aweme_with_statistics_count=replay_summary["aweme_with_statistics_count"],
            aweme_with_duration_count=replay_summary["aweme_with_duration_count"],
            matched_count=update_summary["matched_count"],
            updated_count=update_summary["updated_count"],
            duration_updated_count=update_summary["duration_updated_count"],
            performance_updated_count=update_summary["performance_updated_count"],
            pages_replayed_count=replay_summary["pages_replayed_count"],
            max_pages_requested=max(1, int(max_pages)),
        )

    def _get_capture_session(self, capture_session_id: UUID) -> CaptureSession:
        session = self.db.scalar(
            select(CaptureSession)
            .options(selectinload(CaptureSession.items))
            .where(CaptureSession.id == capture_session_id)
        )
        if session is None:
            raise CaptureInboxRequestReplayError(
                "capture_session_not_found",
                "Capture session was not found for request replay discovery.",
            )
        return session

    def _profile_url_for_session(self, session: CaptureSession) -> str:
        if isinstance(session.submitted_profile_url, str) and session.submitted_profile_url.strip():
            return session.submitted_profile_url
        if isinstance(session.page_url, str) and session.page_url.strip():
            return session.page_url
        raise CaptureInboxRequestReplayError(
            "profile_url_missing",
            "Capture session does not have a Douyin profile/feed URL for request discovery.",
        )

    def _replay_candidate_request(
        self,
        *,
        account_id: UUID,
        candidate: DouyinReplayCandidate,
        max_pages: int,
        delay_seconds: float,
        timeout_seconds: float,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
        aweme_by_id: dict[str, dict[str, Any]] = {}
        current_url = candidate.request_url
        current_body = candidate.request_post_data
        seen_cursor_values: set[str] = set()
        aweme_with_statistics_count = 0
        aweme_with_duration_count = 0
        pages_replayed_count = 0
        for page_index in range(max(1, int(max_pages))):
            if page_index > 0 and delay_seconds > 0:
                time.sleep(delay_seconds)
            replay_result = douyin_browser_context_registry.replay_request(
                account_id,
                request_url=current_url,
                method=candidate.request_method,
                headers=candidate.request_headers,
                body=current_body,
                timeout_ms=max(1_000, int(timeout_seconds * 1000)),
            )
            if not replay_result.available:
                raise CaptureInboxRequestReplayError(
                    "browser_context_unavailable",
                    replay_result.reason or replay_result.status or "Browser request replay failed.",
                )
            if replay_result.response_text and looks_like_captcha_or_block(replay_result.response_text):
                raise CaptureInboxRequestReplayError(
                    "captcha_or_login_wall_detected",
                    "Douyin replay response hit captcha/login wall.",
                )
            payload = replay_result.response_document
            if not isinstance(payload, (dict, list)):
                raise CaptureInboxRequestReplayError(
                    "replay_response_not_json",
                    "Douyin replay response did not return a usable JSON body.",
                )
            for aweme in extract_aweme_objects(payload):
                aweme_id = _normalize_aweme_id(aweme.get("aweme_id"))
                if aweme_id is None:
                    continue
                sanitized = sanitize_network_aweme(aweme)
                existing = aweme_by_id.get(aweme_id)
                if existing is None or aweme_score(sanitized) > aweme_score(existing):
                    aweme_by_id[aweme_id] = sanitized
                if isinstance(sanitized.get("statistics"), dict):
                    aweme_with_statistics_count += 1
                video = sanitized.get("video")
                if isinstance(video, dict) and video.get("duration") is not None:
                    aweme_with_duration_count += 1
            pages_replayed_count += 1
            cursor_summary = summarize_cursor_fields(payload)
            if not cursor_summary.get("has_more"):
                break
            cursor_name = candidate.request_cursor_param_name
            next_cursor = next_cursor_value(cursor_summary, cursor_name)
            if cursor_name is None or next_cursor is None:
                break
            cursor_key = f"{cursor_name}:{next_cursor}"
            if cursor_key in seen_cursor_values:
                break
            seen_cursor_values.add(cursor_key)
            current_url, current_body = apply_cursor_to_request(
                request_url=current_url,
                request_method=candidate.request_method,
                request_body=current_body,
                cursor_name=cursor_name,
                cursor_value=next_cursor,
            )
        return aweme_by_id, {
            "aweme_seen_count": len(aweme_by_id),
            "aweme_with_statistics_count": aweme_with_statistics_count,
            "aweme_with_duration_count": aweme_with_duration_count,
            "pages_replayed_count": pages_replayed_count,
        }

    def _batch_update_items_from_network_awemes(
        self,
        session: CaptureSession,
        aweme_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, int]:
        matched_count = 0
        updated_count = 0
        duration_updated_count = 0
        performance_updated_count = 0
        items_by_aweme_id = {
            _normalize_aweme_id(item.source_video_external_id): item
            for item in session.items
            if _normalize_aweme_id(item.source_video_external_id) is not None
        }
        now = datetime.now(UTC).isoformat()
        for aweme_id, raw_network_aweme in aweme_by_id.items():
            item = items_by_aweme_id.get(aweme_id)
            if item is None:
                continue
            matched_count += 1
            metadata = dict(getattr(item, "metadata_json", None) or {})
            previous_duration = item.duration_seconds
            previous_view = _int_or_none(metadata.get("view_count"))
            previous_like = _int_or_none(metadata.get("like_count"))
            metadata["raw_network_aweme"] = raw_network_aweme
            metadata["raw_evidence_summary"] = merge_network_evidence_summary(
                existing=dict(metadata.get("raw_evidence_summary") or {}),
                raw_network_aweme=raw_network_aweme,
                raw_dom_snapshot=metadata.get("raw_dom_snapshot"),
                raw_detail_aweme=metadata.get("raw_detail_aweme"),
            )
            normalized = self._normalizer.normalize(
                CaptureMetadataNormalizeInput(
                    raw_network_aweme=raw_network_aweme,
                    raw_detail_aweme=metadata.get("raw_detail_aweme") if isinstance(metadata.get("raw_detail_aweme"), dict) else None,
                    raw_dom_snapshot=metadata.get("raw_dom_snapshot") if isinstance(metadata.get("raw_dom_snapshot"), dict) else None,
                    raw_evidence_summary=metadata["raw_evidence_summary"],
                    existing_posted_at=item.posted_at,
                    existing_posted_text=_string_or_none(metadata.get("posted_text")),
                    existing_duration_seconds=item.duration_seconds,
                    existing_duration_text=_string_or_none(metadata.get("duration_text")),
                    existing_view_count=_int_or_none(metadata.get("view_count")),
                    existing_like_count=_int_or_none(metadata.get("like_count")),
                    existing_comment_count=_int_or_none(metadata.get("comment_count")),
                    existing_share_count=_int_or_none(metadata.get("share_count")),
                    existing_engagement_rate=_float_or_none(metadata.get("engagement_rate")),
                )
            )
            item.posted_at = normalized.posted_at
            item.duration_seconds = normalized.duration_seconds
            metadata.update(
                {
                    "posted_at": normalized.posted_at.isoformat() if normalized.posted_at else None,
                    "posted_text": normalized.posted_text,
                    "duration_seconds": normalized.duration_seconds,
                    "duration_text": normalized.duration_text,
                    "view_count": normalized.view_count,
                    "like_count": normalized.like_count,
                    "comment_count": normalized.comment_count,
                    "share_count": normalized.share_count,
                    "engagement_rate": normalized.engagement_rate,
                    "posted_source": normalized.posted_source,
                    "duration_source": normalized.duration_source,
                    "view_count_source": normalized.view_count_source,
                    "like_count_source": normalized.like_count_source,
                    "comment_count_source": normalized.comment_count_source,
                    "share_count_source": normalized.share_count_source,
                    "engagement_rate_source": normalized.engagement_rate_source,
                    "metadata_status": normalized.metadata_status,
                    "time_status": normalized.time_status,
                    "performance_status": normalized.performance_status,
                    "processing_fit_status": normalized.processing_fit_status,
                    "metadata_missing_reason": normalized.metadata_missing_reason,
                    "time_missing_reason": normalized.time_missing_reason,
                    "performance_missing_reason": normalized.performance_missing_reason,
                    "processing_fit_missing_reason": normalized.processing_fit_missing_reason,
                    "metadata_source_summary": normalized.metadata_source_summary,
                    "last_metadata_hydrated_at": now,
                    "last_metadata_hydration_source": "network_request_replay",
                    "last_metadata_hydration_result": "success",
                }
            )
            item.metadata_json = metadata
            self.db.add(item)
            updated_count += 1
            if previous_duration is None and normalized.duration_seconds is not None:
                duration_updated_count += 1
            if (previous_view is None and normalized.view_count is not None) or (previous_like is None and normalized.like_count is not None):
                performance_updated_count += 1
        self.db.commit()
        return {
            "matched_count": matched_count,
            "updated_count": updated_count,
            "duration_updated_count": duration_updated_count,
            "performance_updated_count": performance_updated_count,
        }


def detect_candidate_requests(response_records: list[dict]) -> list[DouyinReplayCandidate]:
    candidates: list[DouyinReplayCandidate] = []
    for record in response_records:
        payload = record.get("response_document")
        if not isinstance(payload, (dict, list)):
            continue
        awemes = extract_aweme_objects(payload)
        if not awemes:
            continue
        matched_aweme_count = len(awemes)
        has_statistics_count = sum(1 for item in awemes if isinstance(item.get("statistics"), dict))
        has_duration_count = sum(
            1
            for item in awemes
            if isinstance(item.get("video"), dict) and item.get("video", {}).get("duration") is not None
        )
        sample_aweme_ids = [aweme_id for aweme_id in (_normalize_aweme_id(item.get("aweme_id")) for item in awemes) if aweme_id][:5]
        cursor_fields = summarize_cursor_fields(payload)
        request_url = str(record.get("request_url") or "")
        request_method = str(record.get("request_method") or "GET").upper()
        request_post_data = record.get("request_post_data") if isinstance(record.get("request_post_data"), str) else None
        request_cursor_param_name = detect_request_cursor_param_name(
            request_url=request_url,
            request_body=request_post_data,
            cursor_fields=cursor_fields,
        )
        candidates.append(
            DouyinReplayCandidate(
                request_url=request_url,
                request_method=request_method,
                request_headers=dict(record.get("request_headers") or {}),
                request_post_data=request_post_data,
                matched_aweme_count=matched_aweme_count,
                has_statistics_count=has_statistics_count,
                has_duration_count=has_duration_count,
                sample_aweme_ids=sample_aweme_ids,
                response_shape_summary=summarize_response_shape(payload),
                cursor_fields=cursor_fields,
                request_cursor_param_name=request_cursor_param_name,
            )
        )
    return candidates


def choose_best_candidate(candidates: list[DouyinReplayCandidate]) -> DouyinReplayCandidate:
    return sorted(
        candidates,
        key=lambda item: (
            item.has_statistics_count,
            item.has_duration_count,
            item.matched_aweme_count,
            bool(item.request_cursor_param_name),
        ),
        reverse=True,
    )[0]


def extract_aweme_objects(payload: dict | list) -> list[dict[str, Any]]:
    awemes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in walk_json(payload):
        if not isinstance(item, dict):
            continue
        aweme_id = _normalize_aweme_id(item.get("aweme_id"))
        if aweme_id is None:
            continue
        if not any(key in item for key in ("statistics", "video", "create_time", "desc", "author")):
            continue
        if aweme_id in seen:
            continue
        seen.add(aweme_id)
        awemes.append(item)
    return awemes


def summarize_response_shape(payload: dict | list) -> str:
    if isinstance(payload, dict):
        keys = sorted(str(key) for key in payload.keys())[:6]
        if "aweme_list" in payload:
            return "aweme_list"
        if "item_list" in payload:
            return "item_list"
        if "data" in payload and isinstance(payload.get("data"), dict) and "aweme_list" in payload["data"]:
            return "data.aweme_list"
        if "data" in payload and isinstance(payload.get("data"), dict) and "list" in payload["data"]:
            return "data.list"
        return ",".join(keys)
    return "list_root"


def summarize_cursor_fields(payload: dict | list) -> dict[str, Any]:
    summary: dict[str, Any] = {"has_more": False}
    for item in walk_json(payload):
        if not isinstance(item, dict):
            continue
        for key in ("cursor", "max_cursor", "min_cursor", "offset", "page", "has_more"):
            if key not in item:
                continue
            if key == "has_more":
                summary["has_more"] = bool(item.get(key))
                continue
            if key not in summary:
                summary[key] = item.get(key)
    return summary


def detect_request_cursor_param_name(*, request_url: str, request_body: str | None, cursor_fields: dict[str, Any]) -> str | None:
    available_names = [name for name in _CURSOR_KEYS if name in cursor_fields]
    if not available_names:
        return None
    query_keys = {key for key, _ in parse_qsl(urlparse(request_url).query, keep_blank_values=True)}
    for name in available_names:
        if name in query_keys:
            return name
    body_map = parse_request_body_map(request_body)
    for name in available_names:
        if name in body_map:
            return name
    return available_names[0]


def next_cursor_value(cursor_fields: dict[str, Any], cursor_name: str | None) -> str | None:
    if cursor_name and cursor_name in cursor_fields and cursor_fields.get(cursor_name) is not None:
        return str(cursor_fields[cursor_name])
    for name in ("max_cursor", "cursor", "min_cursor", "offset", "page"):
        if cursor_fields.get(name) is not None:
            return str(cursor_fields[name])
    return None


def apply_cursor_to_request(
    *,
    request_url: str,
    request_method: str,
    request_body: str | None,
    cursor_name: str,
    cursor_value: str,
) -> tuple[str, str | None]:
    parsed = urlparse(request_url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_updated = False
    updated_pairs = []
    for key, value in query_pairs:
        if key == cursor_name:
            updated_pairs.append((key, cursor_value))
            query_updated = True
        else:
            updated_pairs.append((key, value))
    if query_updated:
        request_url = urlunparse(parsed._replace(query=urlencode(updated_pairs)))
        return request_url, request_body
    if request_method.upper() == "POST" and request_body:
        body_map = parse_request_body_map(request_body)
        if cursor_name in body_map:
            body_map[cursor_name] = cursor_value
            return request_url, dump_request_body_map(request_body, body_map)
    return request_url, request_body


def parse_request_body_map(request_body: str | None) -> dict[str, Any]:
    if not request_body:
        return {}
    try:
        parsed = json.loads(request_body)
    except json.JSONDecodeError:
        return {key: value for key, value in parse_qsl(request_body, keep_blank_values=True)}
    return parsed if isinstance(parsed, dict) else {}


def dump_request_body_map(original_body: str, body_map: dict[str, Any]) -> str:
    try:
        json.loads(original_body)
    except json.JSONDecodeError:
        return urlencode({key: "" if value is None else str(value) for key, value in body_map.items()})
    return json.dumps(body_map, ensure_ascii=False, separators=(",", ":"))


def walk_json(value: object):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def sanitize_network_aweme(value: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    aweme_id = _normalize_aweme_id(value.get("aweme_id"))
    if aweme_id is not None:
        sanitized["aweme_id"] = aweme_id
    for key in _AWEME_USEFUL_KEYS:
        if key == "aweme_id" or key not in value:
            continue
        sanitized_value = sanitize_value(value[key], depth=0)
        if sanitized_value is not None:
            sanitized[key] = sanitized_value
    return sanitized


def sanitize_value(value: Any, *, depth: int) -> Any:
    if depth > 5:
        return None
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in list(value.items())[:30]:
            normalized_key = str(key)
            if any(marker in normalized_key.lower() for marker in _SECRET_MARKERS):
                continue
            sanitized_nested = sanitize_value(nested, depth=depth + 1)
            if sanitized_nested is not None:
                sanitized[normalized_key] = sanitized_nested
        return sanitized or None
    if isinstance(value, list):
        items: list[Any] = []
        for entry in value[:30]:
            sanitized_entry = sanitize_value(entry, depth=depth + 1)
            if sanitized_entry is not None:
                items.append(sanitized_entry)
        return items
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def aweme_score(value: dict[str, Any]) -> int:
    score = 0
    if isinstance(value.get("statistics"), dict):
        score += 3
    if isinstance(value.get("video"), dict) and value["video"].get("duration") is not None:
        score += 2
    if value.get("create_time") is not None:
        score += 1
    if value.get("author") is not None:
        score += 1
    return score


def looks_like_captcha_or_block(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _CAPTCHA_OR_BLOCK_MARKERS)


def merge_network_evidence_summary(
    *,
    existing: dict[str, Any],
    raw_network_aweme: dict[str, Any],
    raw_dom_snapshot: Any,
    raw_detail_aweme: Any,
) -> dict[str, Any]:
    merged = dict(existing)
    network_keys = sorted(raw_network_aweme.keys())
    evidence_sources = [source for source in merged.get("evidence_sources", []) if isinstance(source, str)]
    for source in ("network_request_replay", "network_json"):
        if source not in evidence_sources:
            evidence_sources.append(source)
    merged.update(
        {
            "has_network_aweme": True,
            "has_detail_aweme": isinstance(raw_detail_aweme, dict),
            "has_dom_snapshot": isinstance(raw_dom_snapshot, dict),
            "network_keys": network_keys,
            "evidence_sources": evidence_sources,
            "evidence_collection_version": "phase6e_request_replay",
        }
    )
    return merged


def request_url_without_query_secrets(request_url: str) -> str:
    parsed = urlparse(request_url)
    safe_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if any(marker in lowered for marker in _SECRET_MARKERS):
            continue
        safe_pairs.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(safe_pairs)))
