from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import re
from urllib.parse import parse_qs, urlparse

from src.adapters.base import SourceAdapter
from src.adapters.errors import SourceAdapterError, SourceAdapterErrorCode
from src.adapters.types import (
    NormalizedMetricSnapshot,
    NormalizedProfileIdentity,
    NormalizedSourceProfile,
    NormalizedSourceVideo,
    SourceFetchResult,
)
from src.enums import SourcePlatformEnum

FetchClient = Callable[[str], dict]


class DouyinProfileAdapter(SourceAdapter):
    source_platform = SourcePlatformEnum.DOUYIN
    SUPPORTED_HOST_PATTERNS = ("douyin.com", "iesdouyin.com")

    def __init__(self, fetch_client: FetchClient | None = None):
        self.fetch_client = fetch_client

    def validate_profile_url(self, profile_url: str) -> None:
        parsed = urlparse(profile_url)
        host = parsed.netloc.lower()
        if parsed.scheme not in {"http", "https"} or not host:
            raise SourceAdapterError(SourceAdapterErrorCode.INVALID_URL, "Profile URL must be an absolute http(s) URL")
        if not any(pattern in host for pattern in self.SUPPORTED_HOST_PATTERNS):
            raise SourceAdapterError(SourceAdapterErrorCode.UNSUPPORTED_PROFILE, "Only Douyin profile URLs are supported")
        self.normalize_profile_identity(profile_url)

    def normalize_profile_identity(self, profile_url: str) -> NormalizedProfileIdentity:
        parsed = urlparse(profile_url)
        path = parsed.path.strip("/")
        query = parse_qs(parsed.query)
        external_id = None
        handle = None

        user_match = re.search(r"user/([^/?#]+)", path)
        if user_match:
            external_id = user_match.group(1)

        if external_id is None and "sec_uid" in query:
            external_id = query["sec_uid"][0]

        if external_id is None and path.startswith("@"):
            handle = path.split("/", 1)[0].lstrip("@")
            external_id = f"handle:{handle}"

        if external_id is None:
            raise SourceAdapterError(
                SourceAdapterErrorCode.UNSUPPORTED_PROFILE,
                "Could not resolve Douyin profile identifier from URL",
            )

        canonical_url = f"https://www.douyin.com/user/{external_id}" if not external_id.startswith("handle:") else profile_url
        return NormalizedProfileIdentity(
            source_platform=self.source_platform,
            source_profile_external_id=external_id,
            canonical_url=canonical_url,
            handle=handle,
        )

    def fetch_profile(self, profile_url: str) -> SourceFetchResult:
        self.validate_profile_url(profile_url)
        if self.fetch_client is None:
            raise SourceAdapterError(
                SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                "Douyin live fetch is disabled or no fetch client was injected. Enable DOUYIN_ENABLE_LIVE_FETCH=true, ingest a dev payload, or use an already-ingested profile.",
            )
        try:
            raw_payload = self.fetch_client(profile_url)
        except SourceAdapterError:
            raise
        except Exception as exc:
            raise SourceAdapterError(
                SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                f"Douyin adapter fetch failed: {exc}",
            ) from exc
        return self.normalize_fetch_payload(profile_url, raw_payload)

    def normalize_fetch_payload(self, profile_url: str, raw_payload: dict) -> SourceFetchResult:
        identity = self.normalize_profile_identity(profile_url)
        profile_payload = raw_payload.get("profile") or raw_payload.get("user") or {}
        videos_payload = raw_payload.get("videos") or raw_payload.get("aweme_list") or []
        fetch_metadata = raw_payload.get("metadata") if isinstance(raw_payload.get("metadata"), dict) else {}
        if not isinstance(videos_payload, list):
            raise SourceAdapterError(
                SourceAdapterErrorCode.NORMALIZATION_FAILED,
                "Douyin videos payload must be a list",
                raw_payload=raw_payload,
            )

        profile = NormalizedSourceProfile(
            source_platform=self.source_platform,
            source_profile_external_id=str(profile_payload.get("id") or profile_payload.get("sec_uid") or identity.source_profile_external_id),
            profile_url=profile_url,
            display_name=profile_payload.get("display_name") or profile_payload.get("nickname"),
            handle=profile_payload.get("handle") or profile_payload.get("unique_id") or identity.handle,
            metadata_json={
                "follower_count": _to_int(profile_payload.get("follower_count")),
                "following_count": _to_int(profile_payload.get("following_count")),
                "canonical_url": identity.canonical_url,
            },
            raw_payload_json=profile_payload or None,
        )

        videos: list[NormalizedSourceVideo] = []
        drop_reasons: dict[str, int] = {}
        for item in videos_payload:
            try:
                videos.append(self._normalize_video(profile.source_profile_external_id, profile.display_name, item))
            except SourceAdapterError as exc:
                reason = str(exc.code)
                drop_reasons[reason] = drop_reasons.get(reason, 0) + 1

        parse_strategy = (
            fetch_metadata.get("parse_strategy")
            if isinstance(fetch_metadata.get("parse_strategy"), str)
            else "videos"
            if isinstance(raw_payload.get("videos"), list)
            else "aweme_list"
        )
        response_classification = fetch_metadata.get("response_classification") if isinstance(fetch_metadata.get("response_classification"), dict) else {}
        return SourceFetchResult(
            profile=profile,
            videos=videos,
            raw_payload_json=raw_payload,
            metadata_json={
                "adapter": "douyin_profile",
                "video_count": len(videos),
                "parse_strategy": parse_strategy,
                "raw_video_item_count": len(videos_payload),
                "normalized_video_count": len(videos),
                "drop_count": max(len(videos_payload) - len(videos), 0),
                "drop_reasons": drop_reasons,
                "fallback_used": False,
                "blocked_reason": response_classification.get("blocked_reason")
                or _blocked_reason_from_payload(raw_payload, len(videos_payload)),
                "response_shape": fetch_metadata.get("response_shape"),
                "embedded_document_count": fetch_metadata.get("embedded_document_count"),
                "browser_response_document_count": fetch_metadata.get("browser_response_document_count"),
                "video_candidate_count": fetch_metadata.get("video_candidate_count"),
                "profile_payload_present": fetch_metadata.get("profile_payload_present"),
                "response_classification": response_classification or None,
                "browser_probe": fetch_metadata.get("browser_probe"),
                "fetch_execution_path": fetch_metadata.get("fetch_execution_path"),
                "fallback_from_execution_path": fetch_metadata.get("fallback_from_execution_path"),
                "http_response_classification": fetch_metadata.get("http_response_classification"),
                "browser_context_status": fetch_metadata.get("browser_context_status"),
                "browser_context_reason": fetch_metadata.get("browser_context_reason"),
                "browser_runtime_context_id": fetch_metadata.get("browser_runtime_context_id"),
                "browser_profile_id": fetch_metadata.get("browser_profile_id"),
                "browser_page_url": fetch_metadata.get("browser_page_url"),
                "browser_page_title": fetch_metadata.get("browser_page_title"),
                "browser_video_link_count": fetch_metadata.get("browser_video_link_count"),
                "browser_surface_status": fetch_metadata.get("browser_surface_status"),
                "browser_surface_reason": fetch_metadata.get("browser_surface_reason"),
                "browser_profile_available": fetch_metadata.get("browser_profile_available"),
                "browser_profile_unavailable_reason": fetch_metadata.get("browser_profile_unavailable_reason"),
                "browser_fallback_attempted": fetch_metadata.get("browser_fallback_attempted"),
                "http_shell_detected": fetch_metadata.get("http_shell_detected"),
                "strategy_policy": fetch_metadata.get("strategy_policy"),
                "primary_execution_path": fetch_metadata.get("primary_execution_path"),
                "final_execution_path_used": fetch_metadata.get("final_execution_path_used"),
                "legacy_http_fallback_allowed": fetch_metadata.get("legacy_http_fallback_allowed"),
                "http_fallback_attempted": fetch_metadata.get("http_fallback_attempted"),
                "http_fallback_reason": fetch_metadata.get("http_fallback_reason"),
            },
        )

    def _normalize_video(
        self,
        profile_external_id: str,
        author_display_name: str | None,
        item: dict,
    ) -> NormalizedSourceVideo:
        external_id = item.get("id") or item.get("aweme_id") or item.get("video_id")
        if external_id is None:
            raise SourceAdapterError(
                SourceAdapterErrorCode.NORMALIZATION_FAILED,
                "Douyin video payload is missing an external id",
                raw_payload=item,
            )

        statistics = item.get("statistics") or item.get("stats") or {}
        title = item.get("title") or item.get("desc")
        hashtags = _extract_hashtags(item)
        source_video_url = (
            item.get("source_video_url")
            or item.get("share_url")
            or item.get("url")
            or f"https://www.douyin.com/video/{external_id}"
        )
        return NormalizedSourceVideo(
            source_platform=self.source_platform,
            source_profile_external_id=profile_external_id,
            source_video_external_id=str(external_id),
            source_video_url=source_video_url,
            author_display_name=author_display_name,
            title=title,
            description=item.get("description") or item.get("desc"),
            duration_seconds=_duration_seconds(item),
            posted_at=_posted_at(item.get("posted_at") or item.get("create_time")),
            hashtags=hashtags,
            thumbnail_url=item.get("thumbnail_url") or item.get("cover_url") or _nested_url(item.get("video"), "cover"),
            raw_visibility=item.get("visibility") or item.get("status"),
            raw_status=str(item.get("status")) if item.get("status") is not None else None,
            metadata_json={
                "author_display_name": author_display_name,
                "title": title,
                "hashtags": hashtags,
                "thumbnail_url": item.get("thumbnail_url") or item.get("cover_url"),
                "capture_item_id": item.get("capture_item_id"),
                "capture_session_id": item.get("capture_session_id"),
                "source": item.get("source"),
                "source_module": item.get("source_module"),
                "aweme_id": item.get("aweme_id"),
                "source_video_external_id": item.get("source_video_external_id"),
                "source_url": item.get("source_url") or item.get("source_video_url") or item.get("url"),
                "video_url": item.get("video_url") or item.get("source_url") or item.get("source_video_url") or item.get("url"),
                "profile_url": item.get("profile_url"),
                "profile_name": item.get("profile_name"),
                "caption": item.get("caption") or item.get("desc") or item.get("title"),
                "description": item.get("description") or item.get("desc"),
                "share_url": item.get("share_url"),
                "duration_seconds": _duration_seconds(item),
                "duration_text": item.get("duration_text"),
                "duration_source": item.get("duration_source"),
                "posted_at": item.get("posted_at") or item.get("create_time"),
                "posted_text": item.get("posted_text"),
                "posted_text_raw": item.get("posted_text_raw"),
                "posted_display": item.get("posted_display"),
                "posted_source": item.get("posted_source"),
                "view_count": _to_int(item.get("view_count")),
                "view_count_text": item.get("view_count_text"),
                "estimated_views_text_raw": item.get("estimated_views_text_raw"),
                "estimated_views_display": item.get("estimated_views_display"),
                "estimated_views_min": _to_int(item.get("estimated_views_min")),
                "estimated_views_max": _to_int(item.get("estimated_views_max")),
                "estimated_views_mid": _to_int(item.get("estimated_views_mid")),
                "estimated_views_parse_confidence": item.get("estimated_views_parse_confidence"),
                "like_count": _to_int(item.get("like_count")),
                "like_count_text": item.get("like_count_text"),
                "comment_count": _to_int(item.get("comment_count")),
                "comment_count_text": item.get("comment_count_text"),
                "share_count": _to_int(item.get("share_count")),
                "share_count_text": item.get("share_count_text"),
                "favorite_count": _to_int(item.get("favorite_count")),
                "favorite_count_text": item.get("favorite_count_text"),
                "engagement_score": item.get("engagement_score"),
                "engagement_rate": item.get("engagement_rate"),
                "engagement_rate_basis": item.get("engagement_rate_basis"),
                "reup_score": item.get("reup_score"),
                "reup_score_label": item.get("reup_score_label"),
                "reup_score_level": item.get("reup_score_level"),
                "reup_score_components": item.get("reup_score_components"),
                "reup_score_reasons": item.get("reup_score_reasons"),
                "preview_status": item.get("preview_status"),
                "media_status": item.get("media_status"),
                "review_board_status": item.get("review_board_status"),
                "review_status": item.get("review_status"),
                "decision_status": item.get("decision_status"),
                "preset": item.get("preset"),
                "matched_presets": item.get("matched_presets"),
                "has_thumbnail": item.get("has_thumbnail"),
                "has_posted": item.get("has_posted"),
                "has_duration": item.get("has_duration"),
                "has_estimated_views": item.get("has_estimated_views"),
                "has_likes": item.get("has_likes"),
                "has_comments": item.get("has_comments"),
                "has_shares": item.get("has_shares"),
                "has_all_core_metadata": item.get("has_all_core_metadata"),
                "missing_metadata_fields": item.get("missing_metadata_fields"),
                "raw_visibility": item.get("visibility"),
                "raw_status": item.get("status"),
            },
            raw_payload_json=item,
            metrics=NormalizedMetricSnapshot(
                view_count=_to_int(statistics.get("view_count") or statistics.get("play_count")),
                like_count=_to_int(statistics.get("like_count") or statistics.get("digg_count")),
                comment_count=_to_int(statistics.get("comment_count")),
                share_count=_to_int(statistics.get("share_count")),
                favorite_count=_to_int(statistics.get("favorite_count") or statistics.get("collect_count")),
                raw_payload_json=statistics or None,
            ),
        )


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _duration_seconds(item: dict) -> float | None:
    value = item.get("duration_seconds")
    if value is None:
        value = item.get("duration")
        if isinstance(value, int | float) and value > 1000:
            value = value / 1000
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _posted_at(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _extract_hashtags(item: dict) -> list[str]:
    raw_tags = item.get("hashtags") or item.get("cha_list") or []
    tags: list[str] = []
    for tag in raw_tags:
        if isinstance(tag, str):
            tags.append(tag.lstrip("#"))
        elif isinstance(tag, dict):
            name = tag.get("name") or tag.get("cha_name") or tag.get("hashtag_name")
            if name:
                tags.append(str(name).lstrip("#"))
    return tags


def _nested_url(container: object, key: str) -> str | None:
    if not isinstance(container, dict):
        return None
    value = container.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        url_list = value.get("url_list")
        if isinstance(url_list, list) and url_list:
            return str(url_list[0])
    return None


def _blocked_reason_from_payload(raw_payload: dict, raw_video_item_count: int) -> str | None:
    marker_blob = str(raw_payload).lower()
    if "login" in marker_blob or "verify login" in marker_blob:
        return "login_required"
    if "captcha" in marker_blob or "challenge" in marker_blob:
        return "challenge_required"
    if raw_video_item_count == 0:
        return "throttled_or_empty"
    return None
