from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.adapters.base import SourceAdapter
from src.adapters.douyin import DouyinProfileAdapter
from src.adapters.errors import SourceAdapterError, SourceAdapterErrorCode
from src.services.fetch_observability import (
    FETCH_STAGE_PARSE_PAYLOAD,
    FETCH_STAGE_NORMALIZE_PAYLOAD,
    FETCH_STAGE_PERSIST_ENTITIES,
    FETCH_STAGE_REQUEST_DISPATCH,
    FETCH_STAGE_RESPONSE_CLASSIFICATION,
    blocked_reason_from_error,
    stage_event,
)
from src.adapters.registry import build_source_adapters
from src.adapters.types import IngestSummary, NormalizedSourceProfile, NormalizedSourceVideo
from src.db.bootstrap import ensure_default_workspace
from src.enums import CrawlSessionStatus, SourcePlatformEnum, SourceProfileStatus, SourceVideoStatus
from src.models.ingestion import CrawlSession, SourceProfile, SourceVideo, VideoMetricSnapshot
from src.services.source_dedupe import normalized_profile_dedupe_key, normalized_video_dedupe_key

logger = logging.getLogger(__name__)


class SourceIngestError(Exception):
    def __init__(self, code: SourceAdapterErrorCode, message: str, *, raw_payload: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.raw_payload = raw_payload


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceIngestService:
    def __init__(self, db: Session, adapters: dict[SourcePlatformEnum, SourceAdapter] | None = None):
        self.db = db
        self.adapters = adapters or build_source_adapters()

    def ingest_profile(
        self,
        *,
        profile_url: str,
        workspace_id: UUID | None = None,
        source_platform: SourcePlatformEnum = SourcePlatformEnum.DOUYIN,
        crawl_mode: str | None = None,
        adapter_payload_json: dict | None = None,
    ) -> IngestSummary:
        workspace = ensure_default_workspace(self.db) if workspace_id is None else None
        workspace_id = workspace.id if workspace is not None else workspace_id
        if workspace_id is None:
            raise SourceIngestError(SourceAdapterErrorCode.PERSISTENCE_FAILED, "workspace_id could not be resolved")

        adapter = self.adapters[source_platform]
        crawl_session = CrawlSession(
            workspace_id=workspace_id,
            source_platform=source_platform,
            submitted_profile_url=profile_url,
            status=CrawlSessionStatus.RUNNING,
            started_at=utc_now(),
            metadata_json={
                "crawl_mode": crawl_mode or "default",
                "fetch_observability": {
                    "stages": {
                        FETCH_STAGE_REQUEST_DISPATCH: stage_event(
                            result="ok",
                            code="request.dispatch.started",
                            message="Live fetch request dispatched to adapter.",
                        ),
                    }
                },
            },
        )
        self.db.add(crawl_session)
        self.db.commit()
        self.db.refresh(crawl_session)
        logger.info("ingest_requested", extra={"crawl_session_id": str(crawl_session.id), "profile_url": profile_url})

        try:
            identity = adapter.normalize_profile_identity(profile_url)
            crawl_session.normalized_profile_identifier = identity.source_profile_external_id
            self.db.commit()

            logger.info("adapter_start", extra={"crawl_session_id": str(crawl_session.id), "source_platform": source_platform})
            if adapter_payload_json is not None and isinstance(adapter, DouyinProfileAdapter):
                fetch_result = adapter.normalize_fetch_payload(profile_url, adapter_payload_json)
            else:
                fetch_result = adapter.fetch_profile(profile_url)
            logger.info(
                "adapter_end",
                extra={"crawl_session_id": str(crawl_session.id), "video_count": len(fetch_result.videos)},
            )

            profile, profile_created = self._upsert_profile(
                workspace_id=workspace_id,
                normalized=fetch_result.profile,
            )
            crawl_session.source_profile_id = profile.id

            created_count = 0
            updated_count = 0
            snapshot_count = 0
            for normalized_video in fetch_result.videos:
                video, created = self._upsert_video(
                    workspace_id=workspace_id,
                    source_profile_id=profile.id,
                    crawl_session_id=crawl_session.id,
                    normalized=normalized_video,
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                self._create_metric_snapshot(
                    workspace_id=workspace_id,
                    source_video_id=video.id,
                    crawl_session_id=crawl_session.id,
                    normalized=normalized_video,
                )
                snapshot_count += 1

            crawl_session.status = CrawlSessionStatus.COMPLETED
            crawl_session.finished_at = utc_now()
            crawl_session.videos_discovered_count = len(fetch_result.videos)
            crawl_session.videos_created_count = created_count
            crawl_session.videos_updated_count = updated_count
            crawl_session.snapshots_created_count = snapshot_count
            crawl_session.raw_payload_json = fetch_result.raw_payload_json
            diagnostics = fetch_result.metadata_json if isinstance(fetch_result.metadata_json, dict) else {}
            stage_payload = diagnostics.get("stages") if isinstance(diagnostics.get("stages"), dict) else {}
            response_classification = diagnostics.get("response_classification") if isinstance(diagnostics.get("response_classification"), dict) else {}
            response_result = response_classification.get("result")
            if not isinstance(response_result, str):
                response_result = "warning" if len(fetch_result.videos) == 0 else "ok"
            response_code = response_classification.get("code")
            if not isinstance(response_code, str):
                response_code = "true_zero_videos" if len(fetch_result.videos) == 0 else "response.classified.ok"
            response_message = response_classification.get("message")
            if not isinstance(response_message, str):
                response_message = (
                    "Douyin returned a parseable profile payload with zero videos."
                    if len(fetch_result.videos) == 0
                    else "Adapter fetch returned parseable payload."
                )
            stage_payload[FETCH_STAGE_RESPONSE_CLASSIFICATION] = stage_event(
                result=response_result,
                code=response_code,
                message=response_message,
                metrics={
                    "videos_payload_count": diagnostics.get("raw_video_item_count", len(fetch_result.videos)),
                    "embedded_document_count": diagnostics.get("embedded_document_count", 0),
                    "fetch_execution_path": diagnostics.get("fetch_execution_path"),
                    "fallback_from_execution_path": diagnostics.get("fallback_from_execution_path"),
                    "browser_profile_available": diagnostics.get("browser_profile_available"),
                    "browser_fallback_attempted": diagnostics.get("browser_fallback_attempted"),
                    "http_shell_detected": diagnostics.get("http_shell_detected"),
                    "strategy_policy": diagnostics.get("strategy_policy"),
                    "primary_execution_path": diagnostics.get("primary_execution_path"),
                    "final_execution_path_used": diagnostics.get("final_execution_path_used"),
                    "http_fallback_attempted": diagnostics.get("http_fallback_attempted"),
                },
            )
            stage_payload[FETCH_STAGE_PARSE_PAYLOAD] = stage_event(
                result="warning" if len(fetch_result.videos) == 0 else "ok",
                code="parse.true_zero_videos" if len(fetch_result.videos) == 0 else "parse.completed",
                message=(
                    "Adapter parsing completed, but no profile videos were exposed."
                    if len(fetch_result.videos) == 0
                    else "Adapter parsing completed."
                ),
                metrics={
                    "parse_strategy": diagnostics.get("parse_strategy"),
                    "raw_video_item_count": diagnostics.get("raw_video_item_count", len(fetch_result.videos)),
                    "embedded_document_count": diagnostics.get("embedded_document_count", 0),
                    "fetch_execution_path": diagnostics.get("fetch_execution_path"),
                },
            )
            stage_payload[FETCH_STAGE_NORMALIZE_PAYLOAD] = stage_event(
                result="warning" if len(fetch_result.videos) == 0 else "ok",
                code="normalize.zero_videos" if len(fetch_result.videos) == 0 else "normalize.completed",
                message=(
                    "Adapter normalization completed with zero videos."
                    if len(fetch_result.videos) == 0
                    else "Adapter normalization completed."
                ),
                metrics={
                    "videos_normalized_count": len(fetch_result.videos),
                    "drop_count": diagnostics.get("drop_count", 0),
                },
            )
            stage_payload[FETCH_STAGE_PERSIST_ENTITIES] = stage_event(
                result="warning" if len(fetch_result.videos) == 0 else "ok",
                code="persist.zero_videos" if len(fetch_result.videos) == 0 else "persist.completed",
                message=(
                    "Canonical ingest completed without source videos to persist."
                    if len(fetch_result.videos) == 0
                    else "Canonical ingest persistence completed."
                ),
                metrics={
                    "videos_created": created_count,
                    "videos_updated": updated_count,
                    "metric_snapshots_created": snapshot_count,
                },
            )

            crawl_session.raw_summary_json = {
                "profile_payload_present": fetch_result.profile.raw_payload_json is not None,
                "video_payload_count": len(fetch_result.videos),
                "parse_strategy": diagnostics.get("parse_strategy"),
                "raw_video_item_count": diagnostics.get("raw_video_item_count"),
                "normalized_video_count": diagnostics.get("normalized_video_count", len(fetch_result.videos)),
                "drop_count": diagnostics.get("drop_count", 0),
                "drop_reasons": diagnostics.get("drop_reasons", {}),
                "fallback_used": diagnostics.get("fallback_used", False),
                "response_shape": diagnostics.get("response_shape"),
                "embedded_document_count": diagnostics.get("embedded_document_count"),
                "response_classification_code": response_code,
                "response_classification_message": response_message,
                "fetch_execution_path": diagnostics.get("fetch_execution_path"),
                "fallback_from_execution_path": diagnostics.get("fallback_from_execution_path"),
                "http_response_classification_code": (
                    diagnostics.get("http_response_classification", {}).get("code")
                    if isinstance(diagnostics.get("http_response_classification"), dict)
                    else None
                ),
                "http_response_classification_message": (
                    diagnostics.get("http_response_classification", {}).get("message")
                    if isinstance(diagnostics.get("http_response_classification"), dict)
                    else None
                ),
                "browser_context_status": diagnostics.get("browser_context_status"),
                "browser_context_reason": diagnostics.get("browser_context_reason"),
                "browser_profile_available": diagnostics.get("browser_profile_available"),
                "browser_profile_unavailable_reason": diagnostics.get("browser_profile_unavailable_reason"),
                "browser_fallback_attempted": diagnostics.get("browser_fallback_attempted"),
                "http_shell_detected": diagnostics.get("http_shell_detected"),
                "strategy_policy": diagnostics.get("strategy_policy"),
                "primary_execution_path": diagnostics.get("primary_execution_path"),
                "final_execution_path_used": diagnostics.get("final_execution_path_used"),
                "legacy_http_fallback_allowed": diagnostics.get("legacy_http_fallback_allowed"),
                "http_fallback_attempted": diagnostics.get("http_fallback_attempted"),
                "http_fallback_reason": diagnostics.get("http_fallback_reason"),
            }
            crawl_session.result_summary_json = {
                "profile_created": profile_created,
                "source_profile_id": str(profile.id),
                "videos_discovered": len(fetch_result.videos),
                "videos_created": created_count,
                "videos_updated": updated_count,
                "metric_snapshots_created": snapshot_count,
                "persisted_video_count": created_count + updated_count,
            }
            metadata = deepcopy(crawl_session.metadata_json or {})
            metadata["fetch_observability"] = {
                "stages": stage_payload,
                "blocked_reason": diagnostics.get("blocked_reason"),
                "fetch_execution_path": diagnostics.get("fetch_execution_path"),
                "fallback_from_execution_path": diagnostics.get("fallback_from_execution_path"),
                "http_response_classification": diagnostics.get("http_response_classification"),
                "browser_context_status": diagnostics.get("browser_context_status"),
                "browser_context_reason": diagnostics.get("browser_context_reason"),
                "browser_profile_available": diagnostics.get("browser_profile_available"),
                "browser_profile_unavailable_reason": diagnostics.get("browser_profile_unavailable_reason"),
                "browser_fallback_attempted": diagnostics.get("browser_fallback_attempted"),
                "http_shell_detected": diagnostics.get("http_shell_detected"),
                "strategy_policy": diagnostics.get("strategy_policy"),
                "primary_execution_path": diagnostics.get("primary_execution_path"),
                "final_execution_path_used": diagnostics.get("final_execution_path_used"),
                "legacy_http_fallback_allowed": diagnostics.get("legacy_http_fallback_allowed"),
                "http_fallback_attempted": diagnostics.get("http_fallback_attempted"),
                "http_fallback_reason": diagnostics.get("http_fallback_reason"),
            }
            crawl_session.metadata_json = metadata
            profile.last_crawled_at = crawl_session.finished_at
            self.db.commit()
            logger.info(
                "crawl_session_completed",
                extra={
                    "crawl_session_id": str(crawl_session.id),
                    "videos_created": created_count,
                    "videos_updated": updated_count,
                    "snapshots_created": snapshot_count,
                },
            )
            return self._summary(crawl_session)
        except SourceAdapterError as exc:
            self.db.rollback()
            self._mark_failed(crawl_session.id, exc.code, exc.message, raw_payload=exc.raw_payload)
            raise SourceIngestError(exc.code, exc.message, raw_payload=exc.raw_payload) from exc
        except Exception as exc:
            self.db.rollback()
            self._mark_failed(
                crawl_session.id,
                SourceAdapterErrorCode.PERSISTENCE_FAILED,
                f"Ingest persistence failed: {exc}",
            )
            raise SourceIngestError(SourceAdapterErrorCode.PERSISTENCE_FAILED, str(exc)) from exc

    def _upsert_profile(
        self,
        *,
        workspace_id: UUID,
        normalized: NormalizedSourceProfile,
    ) -> tuple[SourceProfile, bool]:
        source_platform, source_profile_external_id = normalized_profile_dedupe_key(normalized)
        profile = self.db.scalar(
            select(SourceProfile).where(
                SourceProfile.source_platform == source_platform,
                SourceProfile.source_profile_external_id == source_profile_external_id,
            )
        )
        created = profile is None
        if profile is None:
            profile = SourceProfile(
                workspace_id=workspace_id,
                source_platform=normalized.source_platform,
                source_profile_external_id=normalized.source_profile_external_id,
                profile_url=normalized.profile_url,
                status=SourceProfileStatus.ACTIVE,
            )
            self.db.add(profile)

        profile.profile_url = normalized.profile_url
        profile.display_name = normalized.display_name
        profile.handle = normalized.handle
        profile.metadata_json = normalized.metadata_json
        profile.raw_payload_json = normalized.raw_payload_json
        self.db.flush()
        logger.info("profile_upsert", extra={"source_profile_id": str(profile.id), "created": created})
        return profile, created

    def _upsert_video(
        self,
        *,
        workspace_id: UUID,
        source_profile_id: UUID,
        crawl_session_id: UUID,
        normalized: NormalizedSourceVideo,
    ) -> tuple[SourceVideo, bool]:
        source_platform, source_video_external_id = normalized_video_dedupe_key(normalized)
        video = self.db.scalar(
            select(SourceVideo).where(
                SourceVideo.source_platform == source_platform,
                SourceVideo.source_video_external_id == source_video_external_id,
            )
        )
        created = video is None
        if video is None:
            video = SourceVideo(
                workspace_id=workspace_id,
                source_profile_id=source_profile_id,
                first_crawl_session_id=crawl_session_id,
                source_platform=normalized.source_platform,
                source_video_external_id=normalized.source_video_external_id,
                source_url=normalized.source_video_url,
                status=SourceVideoStatus.DISCOVERED,
            )
            self.db.add(video)

        video.source_profile_id = source_profile_id
        video.source_url = normalized.source_video_url
        video.caption = normalized.description or normalized.title
        video.posted_at = normalized.posted_at
        video.duration_seconds = normalized.duration_seconds
        video.metadata_json = normalized.metadata_json
        video.raw_payload_json = normalized.raw_payload_json
        self.db.flush()
        return video, created

    def _create_metric_snapshot(
        self,
        *,
        workspace_id: UUID,
        source_video_id: UUID,
        crawl_session_id: UUID,
        normalized: NormalizedSourceVideo,
    ) -> VideoMetricSnapshot:
        metrics = normalized.metrics
        snapshot = VideoMetricSnapshot(
            workspace_id=workspace_id,
            source_video_id=source_video_id,
            crawl_session_id=crawl_session_id,
            view_count=metrics.view_count,
            like_count=metrics.like_count,
            comment_count=metrics.comment_count,
            share_count=metrics.share_count,
            favorite_count=metrics.favorite_count,
            raw_payload_json=metrics.raw_payload_json,
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    def _mark_failed(
        self,
        crawl_session_id: UUID,
        error_code: SourceAdapterErrorCode,
        error_message: str,
        *,
        raw_payload: dict | None = None,
    ) -> None:
        crawl_session = self.db.get(CrawlSession, crawl_session_id)
        if crawl_session is None:
            return
        crawl_session.status = CrawlSessionStatus.FAILED
        crawl_session.finished_at = utc_now()
        crawl_session.error_code = error_code
        crawl_session.error_message = error_message
        if raw_payload is not None:
            crawl_session.raw_payload_json = raw_payload

        raw_metadata = raw_payload.get("metadata") if isinstance(raw_payload, dict) and isinstance(raw_payload.get("metadata"), dict) else {}
        response_classification = raw_metadata.get("response_classification") if isinstance(raw_metadata.get("response_classification"), dict) else {}
        blocked_reason = response_classification.get("blocked_reason")
        if not isinstance(blocked_reason, str) or not blocked_reason:
            blocked_reason = blocked_reason_from_error(error_code=str(error_code), error_message=error_message)
        metadata = deepcopy(crawl_session.metadata_json or {})
        observability = metadata.get("fetch_observability") if isinstance(metadata.get("fetch_observability"), dict) else {}
        stages = observability.get("stages") if isinstance(observability.get("stages"), dict) else {}
        stages[FETCH_STAGE_RESPONSE_CLASSIFICATION] = stage_event(
            result=response_classification.get("result") if isinstance(response_classification.get("result"), str) else ("blocked" if blocked_reason else "failed"),
            code=response_classification.get("code") if isinstance(response_classification.get("code"), str) else f"response.classified.{blocked_reason or 'failed'}",
            message=response_classification.get("message") if isinstance(response_classification.get("message"), str) else error_message,
            metrics=response_classification.get("metrics") if isinstance(response_classification.get("metrics"), dict) else None,
        )
        if raw_metadata:
            crawl_session.raw_summary_json = {
                "profile_payload_present": raw_metadata.get("profile_payload_present"),
                "video_payload_count": 0,
                "parse_strategy": raw_metadata.get("parse_strategy") or "videos",
                "raw_video_item_count": raw_metadata.get("video_candidate_count", 0),
                "normalized_video_count": 0,
                "drop_count": 0,
                "drop_reasons": {},
                "fallback_used": False,
                "response_shape": raw_metadata.get("response_shape"),
                "embedded_document_count": raw_metadata.get("embedded_document_count"),
                "response_classification_code": response_classification.get("code"),
                "response_classification_message": response_classification.get("message"),
                "fetch_execution_path": raw_metadata.get("fetch_execution_path"),
                "fallback_from_execution_path": raw_metadata.get("fallback_from_execution_path"),
                "http_response_classification_code": (
                    raw_metadata.get("http_response_classification", {}).get("code")
                    if isinstance(raw_metadata.get("http_response_classification"), dict)
                    else None
                ),
                "http_response_classification_message": (
                    raw_metadata.get("http_response_classification", {}).get("message")
                    if isinstance(raw_metadata.get("http_response_classification"), dict)
                    else None
                ),
                "browser_context_status": raw_metadata.get("browser_context_status"),
                "browser_context_reason": raw_metadata.get("browser_context_reason"),
                "browser_profile_available": raw_metadata.get("browser_profile_available"),
                "browser_profile_unavailable_reason": raw_metadata.get("browser_profile_unavailable_reason"),
                "browser_fallback_attempted": raw_metadata.get("browser_fallback_attempted"),
                "http_shell_detected": raw_metadata.get("http_shell_detected"),
                "strategy_policy": raw_metadata.get("strategy_policy"),
                "primary_execution_path": raw_metadata.get("primary_execution_path"),
                "final_execution_path_used": raw_metadata.get("final_execution_path_used"),
                "legacy_http_fallback_allowed": raw_metadata.get("legacy_http_fallback_allowed"),
                "http_fallback_attempted": raw_metadata.get("http_fallback_attempted"),
                "http_fallback_reason": raw_metadata.get("http_fallback_reason"),
            }
        observability["stages"] = stages
        observability["blocked_reason"] = blocked_reason
        observability["fetch_execution_path"] = raw_metadata.get("fetch_execution_path")
        observability["fallback_from_execution_path"] = raw_metadata.get("fallback_from_execution_path")
        observability["http_response_classification"] = raw_metadata.get("http_response_classification")
        observability["browser_context_status"] = raw_metadata.get("browser_context_status")
        observability["browser_context_reason"] = raw_metadata.get("browser_context_reason")
        observability["browser_profile_available"] = raw_metadata.get("browser_profile_available")
        observability["browser_profile_unavailable_reason"] = raw_metadata.get("browser_profile_unavailable_reason")
        observability["browser_fallback_attempted"] = raw_metadata.get("browser_fallback_attempted")
        observability["http_shell_detected"] = raw_metadata.get("http_shell_detected")
        observability["strategy_policy"] = raw_metadata.get("strategy_policy")
        observability["primary_execution_path"] = raw_metadata.get("primary_execution_path")
        observability["final_execution_path_used"] = raw_metadata.get("final_execution_path_used")
        observability["legacy_http_fallback_allowed"] = raw_metadata.get("legacy_http_fallback_allowed")
        observability["http_fallback_attempted"] = raw_metadata.get("http_fallback_attempted")
        observability["http_fallback_reason"] = raw_metadata.get("http_fallback_reason")
        metadata["fetch_observability"] = observability
        crawl_session.metadata_json = metadata
        self.db.commit()
        logger.info(
            "crawl_session_failed",
            extra={"crawl_session_id": str(crawl_session.id), "error_code": error_code},
        )

    def _summary(self, crawl_session: CrawlSession) -> IngestSummary:
        return IngestSummary(
            crawl_session_id=str(crawl_session.id),
            status=crawl_session.status,
            source_profile_id=str(crawl_session.source_profile_id) if crawl_session.source_profile_id else None,
            source_platform=crawl_session.source_platform or SourcePlatformEnum.DOUYIN,
            submitted_profile_url=crawl_session.submitted_profile_url or "",
            normalized_profile_identifier=crawl_session.normalized_profile_identifier,
            videos_discovered_count=crawl_session.videos_discovered_count,
            videos_created_count=crawl_session.videos_created_count,
            videos_updated_count=crawl_session.videos_updated_count,
            snapshots_created_count=crawl_session.snapshots_created_count,
            error_code=crawl_session.error_code,
            error_message=crawl_session.error_message,
        )


def get_crawl_session(db: Session, crawl_session_id: UUID) -> CrawlSession | None:
    return db.scalar(
        select(CrawlSession)
        .where(CrawlSession.id == crawl_session_id)
        .options(selectinload(CrawlSession.source_profile))
    )
