from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.core.settings import get_settings
from src.downloaders.base import AssetDownloader, DownloadedObject
from src.downloaders.douyin_browser_download_cookies import sync_download_cookie_store_from_live_browser
from src.downloaders.douyin_download_session import resolve_douyin_download_session
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.http import HttpAssetDownloader
from src.downloaders.source_video_filename import build_source_video_raw_filename, parse_height_from_format_label
from src.downloaders.source_video_primary_fetcher import PrimaryVideoFetchResult, SourceVideoPrimaryFetcher
from src.enums import JobType, MediaAssetStatus, MediaAssetType, SourceVideoStatus
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset
from src.models.review import VideoCandidate
from src.services.job_service import JobService
from src.storage.local import LocalStorageBackend
from src.storage.manifest import assemble_asset_manifest
from src.storage.path_strategy import VideoStorageContext, asset_logical_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadRequest:
    source_video_id: UUID | None = None
    candidate_id: UUID | None = None
    force_refresh: bool = False


@dataclass(frozen=True)
class DownloadJobResult:
    job_id: str
    status: str
    source_video_id: str
    asset_count: int
    manifest: dict


class DownloadService:
    def __init__(
        self,
        db: Session,
        *,
        storage: LocalStorageBackend | None = None,
        downloader: AssetDownloader | None = None,
        primary_fetcher: SourceVideoPrimaryFetcher | None = None,
    ):
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)
        self.downloader = downloader or HttpAssetDownloader()
        settings = get_settings()
        self.primary_fetcher = primary_fetcher or SourceVideoPrimaryFetcher(
            http_downloader=self.downloader,
            yt_dlp_enabled=settings.douyin_yt_dlp_enabled,
            playwright_enabled=getattr(settings, "douyin_playwright_download_enabled", True),
        )

    def create_download_job(self, request: DownloadRequest, *, idempotency_key: str | None = None) -> DownloadJobResult:
        source_video = self._resolve_source_video(request)
        # API process owns the live Playwright window; flush cookies to shared store
        # before the worker (separate process) runs yt-dlp.
        sync_download_cookie_store_from_live_browser(self.db, source_video.workspace_id)
        settings = get_settings()
        job = JobService(self.db).create_job(
            job_type=JobType.DOWNLOAD_VIDEO,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "force_refresh": request.force_refresh,
            },
            idempotency_key=idempotency_key,
            max_attempts=int(getattr(settings, "douyin_download_transient_max_attempts", 8)),
        )
        manifest = self.get_manifest(source_video.id)
        logger.info("download_job_created", extra={"job_id": str(job.id), "source_video_id": str(source_video.id)})
        return DownloadJobResult(
            job_id=str(job.id),
            status=job.status,
            source_video_id=str(source_video.id),
            asset_count=len(manifest["assets"]),
            manifest=manifest,
        )

    def run_download(self, source_video_id: UUID, *, job_id: UUID | None = None, force_refresh: bool = False) -> dict:
        source_video = self._get_source_video(source_video_id)
        logger.info("download_started", extra={"source_video_id": str(source_video.id)})

        assets: list[MediaAsset] = []
        download_session = resolve_douyin_download_session(self.db, source_video.workspace_id)
        primary_result = self._fetch_primary_video(source_video, download_session)
        self._enrich_profile_identity_from_download(source_video, primary_result)
        context = self._storage_context(source_video)
        assets.append(
            self._persist_primary_video(
                source_video,
                context,
                primary_result,
                job_id=job_id,
                force_refresh=force_refresh,
            )
        )

        thumbnail_url = _metadata_string(source_video.metadata_json, "thumbnail_url")
        if thumbnail_url:
            try:
                assets.append(
                    self._persist_downloaded_asset(
                        source_video,
                        context,
                        MediaAssetType.THUMBNAIL,
                        thumbnail_url,
                        filename="thumbnail.jpg",
                        job_id=job_id,
                        force_refresh=force_refresh,
                    )
                )
            except DownloadError as exc:
                self._register_failed_asset(source_video, context, MediaAssetType.THUMBNAIL, thumbnail_url, exc, job_id)

        metadata_asset = self._persist_json_asset(
            source_video,
            context,
            MediaAssetType.METADATA_JSON,
            {
                "source_video": {
                    "id": str(source_video.id),
                    "external_id": source_video.source_video_external_id,
                    "source_url": source_video.source_url,
                    "caption": source_video.caption,
                    "metadata_json": source_video.metadata_json,
                    "raw_payload_json": source_video.raw_payload_json,
                }
            },
            filename="source_metadata.json",
            job_id=job_id,
            force_refresh=force_refresh,
        )
        assets.append(metadata_asset)

        if source_video.caption:
            assets.append(
                self._persist_bytes_asset(
                    source_video,
                    context,
                    MediaAssetType.SOURCE_CAPTION_RAW,
                    source_video.caption.encode("utf-8"),
                    filename="caption.txt",
                    mime_type="text/plain",
                    source_url=None,
                    job_id=job_id,
                    force_refresh=force_refresh,
                )
            )

        source_video.status = SourceVideoStatus.DOWNLOADED
        self.db.commit()
        manifest = self.get_manifest(source_video.id)
        logger.info("manifest_finalized", extra={"source_video_id": str(source_video.id), "asset_count": len(manifest["assets"])})
        return manifest

    def get_assets(self, source_video_id: UUID) -> list[MediaAsset]:
        return list(
            self.db.scalars(
                select(MediaAsset)
                .where(MediaAsset.source_video_id == source_video_id)
                .order_by(MediaAsset.asset_type, MediaAsset.version.desc())
            )
        )

    def get_manifest(self, source_video_id: UUID) -> dict:
        source_video = self._load_source_video(source_video_id)
        assets = self.get_assets(source_video_id)
        return assemble_asset_manifest(
            source_video=source_video,
            source_profile=source_video.source_profile,
            assets=assets,
            storage_root=str(self.storage.root),
        )

    def _fetch_primary_video(self, source_video: SourceVideo, download_session) -> PrimaryVideoFetchResult:
        fetch_kwargs = dict(
            session_cookie=download_session.session_cookie,
            user_agent=download_session.user_agent,
            proxy_url=download_session.proxy_url,
            playwright_cookies=download_session.playwright_cookies,
            cookie_source=download_session.cookie_source,
            workspace_id=source_video.workspace_id,
        )
        try:
            return self.primary_fetcher.fetch(source_video, **fetch_kwargs)
        except DownloadError as exc:
            if (
                exc.code != DownloadErrorCode.DOWNLOAD_FAILED
                or download_session.cookie_source in {"browser_live", "browser_store", "playwright_browser"}
            ):
                raise
            browser_session = resolve_douyin_download_session(
                self.db,
                source_video.workspace_id,
                prefer_browser=True,
            )
            if browser_session.cookie_source not in {"browser_live", "browser_store"}:
                raise
            logger.info(
                "download_retry_with_browser_cookies",
                extra={"source_video_id": str(source_video.id)},
            )
            return self.primary_fetcher.fetch(
                source_video,
                session_cookie=browser_session.session_cookie,
                user_agent=browser_session.user_agent,
                proxy_url=browser_session.proxy_url,
                playwright_cookies=browser_session.playwright_cookies,
                cookie_source=browser_session.cookie_source,
                workspace_id=source_video.workspace_id,
            )

    def _persist_primary_video(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        primary_result,
        *,
        job_id: UUID | None,
        force_refresh: bool,
    ) -> MediaAsset:
        from datetime import UTC, datetime

        ext = "mp4"
        resolver_name = getattr(primary_result.downloaded, "filename", None) or ""
        if "." in resolver_name:
            maybe_ext = resolver_name.rsplit(".", 1)[-1].lower()
            if maybe_ext in {"mp4", "webm", "m4v", "mov"}:
                ext = maybe_ext
        height = getattr(primary_result, "height", None)
        if not isinstance(height, int) or height <= 0:
            height = parse_height_from_format_label(getattr(primary_result, "format_id", None))
        if not isinstance(height, int) or height <= 0:
            height = None
        filename = build_source_video_raw_filename(
            aweme_id=source_video.source_video_external_id or "unknown",
            caption=source_video.caption,
            watermark_free=getattr(primary_result, "watermark_free", None),
            posted_at=getattr(source_video, "posted_at", None),
            height=height,
            fallback_date=datetime.now(UTC),
            extension=ext,
        )
        return self._persist_bytes_asset(
            source_video,
            context,
            MediaAssetType.SOURCE_VIDEO_RAW,
            primary_result.downloaded.content,
            filename=filename,
            mime_type=primary_result.downloaded.mime_type,
            source_url=primary_result.source_url,
            job_id=job_id,
            force_refresh=force_refresh,
            extra_metadata=primary_result.asset_metadata(),
        )

    def _persist_downloaded_asset(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        asset_type: MediaAssetType,
        url: str,
        *,
        filename: str,
        job_id: UUID | None,
        force_refresh: bool,
    ) -> MediaAsset:
        if not url:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Missing asset source URL")
        downloaded = self.downloader.fetch(url)
        return self._persist_bytes_asset(
            source_video,
            context,
            asset_type,
            downloaded.content,
            filename=downloaded.filename or filename,
            mime_type=downloaded.mime_type,
            source_url=url,
            job_id=job_id,
            force_refresh=force_refresh,
        )

    def _persist_json_asset(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        asset_type: MediaAssetType,
        payload: dict,
        *,
        filename: str,
        job_id: UUID | None,
        force_refresh: bool,
    ) -> MediaAsset:
        content = json.dumps(payload, ensure_ascii=True, indent=2, default=str).encode("utf-8")
        return self._persist_bytes_asset(
            source_video,
            context,
            asset_type,
            content,
            filename=filename,
            mime_type="application/json",
            source_url=None,
            job_id=job_id,
            force_refresh=force_refresh,
        )

    def _persist_bytes_asset(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        asset_type: MediaAssetType,
        content: bytes,
        *,
        filename: str,
        mime_type: str | None,
        source_url: str | None,
        job_id: UUID | None,
        force_refresh: bool,
        extra_metadata: dict | None = None,
    ) -> MediaAsset:
        if not content:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, f"Asset content is empty: {asset_type}")
        existing = self._current_asset(source_video.id, asset_type)
        if existing and not force_refresh and self.storage.exists(existing.storage_key):
            return existing

        version = (existing.version + 1) if existing else 1

        # RAW leaves keep operator-facing names; sidecars keep version prefix for refreshes.
        leaf = filename if asset_type == MediaAssetType.SOURCE_VIDEO_RAW else f"v{version}_{filename}"
        logical_key = asset_logical_key(context, asset_type, filename=leaf)
        try:
            write_result = self.storage.write_bytes(logical_key, content)
        except Exception as exc:
            raise DownloadError(DownloadErrorCode.WRITE_FAILED, f"Write failed: {exc}") from exc

        if write_result.size_bytes <= 0:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, "Written file is empty")

        metadata_json = {
            "absolute_path": write_result.absolute_path,
            **(extra_metadata or {}),
        }
        reusable = self._asset_by_storage_key(source_video.workspace_id, write_result.storage_key)
        if reusable is not None:
            # Re-download writes the same file path (RAW leaves keep operator-facing
            # names), so a new row would break uq_media_assets_workspace_storage_key.
            if existing is not None and existing is not reusable:
                existing.is_current = False
            reusable.source_video_id = source_video.id
            reusable.asset_type = asset_type
            reusable.status = MediaAssetStatus.AVAILABLE
            reusable.storage_provider = write_result.storage_provider
            reusable.logical_key = logical_key
            reusable.relative_path = write_result.relative_path
            reusable.manifest_group = "source_download"
            reusable.is_current = True
            reusable.created_by_job_id = job_id
            reusable.source_url = source_url
            reusable.mime_type = mime_type
            reusable.size_bytes = write_result.size_bytes
            reusable.checksum_sha256 = write_result.checksum_sha256
            reusable.metadata_json = metadata_json
            reusable.error_message = None
            self.db.flush()
            logger.info(
                "asset_refreshed_in_place",
                extra={"source_video_id": str(source_video.id), "asset_type": asset_type},
            )
            return reusable

        if existing is not None:
            existing.is_current = False

        asset = MediaAsset(
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            asset_type=asset_type,
            status=MediaAssetStatus.AVAILABLE,
            version=version,
            storage_provider=write_result.storage_provider,
            storage_key=write_result.storage_key,
            logical_key=logical_key,
            relative_path=write_result.relative_path,
            manifest_group="source_download",
            is_current=True,
            created_by_job_id=job_id,
            source_url=source_url,
            mime_type=mime_type,
            size_bytes=write_result.size_bytes,
            checksum_sha256=write_result.checksum_sha256,
            metadata_json=metadata_json,
        )
        self.db.add(asset)
        self.db.flush()
        logger.info("asset_persisted", extra={"source_video_id": str(source_video.id), "asset_type": asset_type})
        return asset

    def _register_failed_asset(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        asset_type: MediaAssetType,
        source_url: str,
        error: DownloadError,
        job_id: UUID | None,
    ) -> MediaAsset:
        existing = self._current_asset(source_video.id, asset_type)
        version = (existing.version + 1) if existing else 1

        logical_key = asset_logical_key(context, asset_type, filename="failed.placeholder")
        reusable = self._asset_by_storage_key(source_video.workspace_id, logical_key)
        if reusable is not None:
            # The placeholder key is constant, so repeated failures must reuse the row.
            if existing is not None and existing is not reusable:
                existing.is_current = False
            reusable.source_video_id = source_video.id
            reusable.asset_type = asset_type
            reusable.status = MediaAssetStatus.FAILED
            reusable.is_current = True
            reusable.logical_key = logical_key
            reusable.relative_path = logical_key
            reusable.manifest_group = "source_download"
            reusable.created_by_job_id = job_id
            reusable.source_url = source_url
            reusable.error_message = f"{error.code}: {error.message}"
            self.db.flush()
            return reusable

        if existing is not None:
            existing.is_current = False

        asset = MediaAsset(
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            asset_type=asset_type,
            status=MediaAssetStatus.FAILED,
            version=version,
            storage_provider=self.storage.provider_name,
            storage_key=logical_key,
            logical_key=logical_key,
            relative_path=logical_key,
            manifest_group="source_download",
            is_current=True,
            created_by_job_id=job_id,
            source_url=source_url,
            error_message=f"{error.code}: {error.message}",
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def _current_asset(self, source_video_id: UUID, asset_type: MediaAssetType) -> MediaAsset | None:
        return self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == asset_type,
                MediaAsset.is_current.is_(True),
            )
        )

    def _asset_by_storage_key(self, workspace_id: UUID, storage_key: str) -> MediaAsset | None:
        """Row that already owns this storage key (uq_media_assets_workspace_storage_key)."""
        return self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.workspace_id == workspace_id,
                MediaAsset.storage_key == storage_key,
            )
        )

    def _resolve_source_video(self, request: DownloadRequest) -> SourceVideo:
        if request.source_video_id:
            return self._get_source_video(request.source_video_id)
        if request.candidate_id:
            candidate = self.db.get(VideoCandidate, request.candidate_id)
            if candidate is None:
                raise DownloadError(DownloadErrorCode.INVALID_SOURCE_VIDEO, "Candidate not found")
            return self._get_source_video(candidate.source_video_id)
        raise DownloadError(DownloadErrorCode.INVALID_SOURCE_VIDEO, "source_video_id or candidate_id is required")

    def _get_source_video(self, source_video_id: UUID) -> SourceVideo:
        source_video = self._load_source_video(source_video_id)
        if not source_video.source_url and not source_video.source_video_external_id:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Source video has no source URL or external id")
        return source_video

    def _load_source_video(self, source_video_id: UUID) -> SourceVideo:
        source_video = self.db.scalar(
            select(SourceVideo)
            .where(SourceVideo.id == source_video_id)
            .options(selectinload(SourceVideo.source_profile))
        )
        if source_video is None:
            raise DownloadError(DownloadErrorCode.INVALID_SOURCE_VIDEO, "Source video not found")
        return source_video

    def _storage_context(self, source_video: SourceVideo) -> VideoStorageContext:
        profile = source_video.source_profile
        return VideoStorageContext(
            workspace_id=str(source_video.workspace_id),
            source_platform=source_video.source_platform,
            source_profile_external_id=profile.source_profile_external_id,
            source_video_external_id=source_video.source_video_external_id,
            profile_handle=getattr(profile, "handle", None),
            profile_display_name=getattr(profile, "display_name", None),
        )

    def _enrich_profile_identity_from_download(self, source_video: SourceVideo, primary_result) -> None:
        """Persist Douyin author handle/nickname discovered during download for operator folders."""
        profile = source_video.source_profile
        if profile is None:
            return
        handle = getattr(primary_result, "author_handle", None)
        display_name = getattr(primary_result, "author_display_name", None)
        handle = handle.strip().lstrip("@") if isinstance(handle, str) and handle.strip() else None
        display_name = display_name.strip() if isinstance(display_name, str) and display_name.strip() else None
        changed = False
        if handle and not profile.handle:
            profile.handle = handle
            changed = True
        if display_name and not profile.display_name:
            profile.display_name = display_name
            changed = True
        if changed:
            self.db.flush()
            logger.info(
                "source_profile_identity_enriched",
                extra={
                    "source_video_id": str(source_video.id),
                    "source_profile_id": str(profile.id),
                    "handle": profile.handle,
                    "display_name": profile.display_name,
                },
            )


def _metadata_string(metadata: dict | None, key: str) -> str | None:
    value = (metadata or {}).get(key)
    return value if isinstance(value, str) and value else None
