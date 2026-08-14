from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import logging
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.core.settings import get_settings
from src.downloaders.base import AssetDownloader, DownloadedObject
from src.downloaders.douyin_browser_download_cookies import (
    _account_for_workspace,
    sync_download_cookie_store_from_live_browser,
)
from src.downloaders.douyin_download_session import resolve_douyin_download_session
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.download_quality_policy import current_quality_policy
from src.downloaders.post_download_qa import evaluate_post_download_qa
from src.downloaders.http import HttpAssetDownloader
from src.downloaders.source_video_filename import build_source_video_raw_filename, parse_height_from_format_label
from src.downloaders.source_video_primary_fetcher import PrimaryVideoFetchResult, SourceVideoPrimaryFetcher
from src.enums import JobType, MediaAssetStatus, MediaAssetType, SourceVideoStatus
from src.models.ingestion import SourceVideo
from src.models.jobs import Job
from src.models.media import MediaAsset
from src.models.review import VideoCandidate
from src.services.job_service import JobService
from src.storage.asset_health import validate_asset_health
from src.storage.local import LocalStorageBackend
from src.storage.manifest import assemble_asset_manifest
from src.storage.path_strategy import VideoStorageContext, asset_logical_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadRequest:
    source_video_id: UUID | None = None
    candidate_id: UUID | None = None
    force_refresh: bool = False
    account_connection_id: UUID | None = None
    # Optional stable transfer namespace for callers that own a queue item.
    # When omitted, normal idempotent commands derive one from the command key.
    transfer_id: str | None = None


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
        media_probe: Callable[[str], object] | None = None,
        media_path_probe: Callable[[str | Path], object] | None = None,
    ):
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)
        self.downloader = downloader or HttpAssetDownloader(
            max_bytes=int(getattr(get_settings(), "douyin_download_max_bytes", 2_000_000_000))
        )
        settings = get_settings()
        self.primary_fetcher = primary_fetcher or SourceVideoPrimaryFetcher(
            http_downloader=self.downloader,
            yt_dlp_enabled=settings.douyin_yt_dlp_enabled,
            playwright_enabled=getattr(settings, "douyin_playwright_download_enabled", True),
        )
        if media_probe is None:
            default_probe, default_path_probe = self._default_media_probes()
            self.media_probe = default_probe
            self.media_path_probe = media_path_probe or default_path_probe
        else:
            self.media_probe = media_probe
            owner = getattr(media_probe, "__self__", None)
            self.media_path_probe = media_path_probe or getattr(owner, "probe_path", None)

    def create_download_job(
        self,
        request: DownloadRequest,
        *,
        idempotency_key: str | None = None,
        commit: bool = True,
    ) -> DownloadJobResult:
        source_video = self._resolve_source_video(request)
        # Resolve the effective account before idempotency lookup.  Replaying a
        # key must compare against the account that would actually run this
        # command (source binding, explicit operator choice, or the current
        # default), never merely against the optional request field.
        account_connection_id = self._resolve_effective_account_connection_id(
            source_video,
            request.account_connection_id,
        )
        # Normalize the default command key after resolving the canonical
        # SourceVideo and concrete account.  The API may receive either a
        # candidate_id or source_video_id for the same object; deriving the
        # key from the request selector would create duplicate jobs.  Refresh
        # remains an explicit uncached command unless the caller supplies a
        # deliberate key.
        effective_idempotency_key = idempotency_key
        if effective_idempotency_key is None and not request.force_refresh:
            effective_idempotency_key = f"download:{source_video.id}:{account_connection_id or 'unbound'}"
        stable_transfer_id = request.transfer_id
        if stable_transfer_id is None and effective_idempotency_key:
            stable_transfer_id = _stable_transfer_id(
                source_video.id,
                account_connection_id,
                effective_idempotency_key,
            )
        if effective_idempotency_key:
            existing_job = self.db.scalar(
                select(Job).where(
                    Job.workspace_id == source_video.workspace_id,
                    Job.idempotency_key == effective_idempotency_key,
                )
            )
            if existing_job is not None:
                if (
                    existing_job.job_type != JobType.DOWNLOAD_VIDEO
                    or existing_job.source_video_id != source_video.id
                ):
                    raise DownloadError(
                        DownloadErrorCode.VALIDATION_FAILED,
                        "Idempotency key is already bound to a different download command",
                    )
                existing_payload = dict(existing_job.payload_json or {})
                existing_account = existing_payload.get("account_connection_id")
                if str(existing_account or "") != str(account_connection_id or ""):
                    raise DownloadError(
                        DownloadErrorCode.VALIDATION_FAILED,
                        "Idempotency key is already bound to a different Douyin account",
                    )
                if bool(existing_payload.get("force_refresh")) != bool(request.force_refresh):
                    raise DownloadError(
                        DownloadErrorCode.VALIDATION_FAILED,
                        "Idempotency key is already bound to a different refresh policy",
                    )
                manifest = self.get_manifest(source_video.id)
                return DownloadJobResult(
                    job_id=str(existing_job.id),
                    status=existing_job.status,
                    source_video_id=str(source_video.id),
                    asset_count=len(manifest["assets"]),
                    manifest=manifest,
                )
        # API process owns the live Playwright window; flush cookies to shared store
        # before the worker (separate process) runs yt-dlp.
        sync_download_cookie_store_from_live_browser(
            self.db,
            source_video.workspace_id,
            account_connection_id,
        )
        settings = get_settings()
        create_kwargs = dict(
            job_type=JobType.DOWNLOAD_VIDEO,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "force_refresh": request.force_refresh,
                "account_connection_id": str(account_connection_id) if account_connection_id else None,
                "transfer_id": stable_transfer_id,
            },
            idempotency_key=effective_idempotency_key,
            max_attempts=int(getattr(settings, "douyin_download_transient_max_attempts", 8)),
            commit=commit,
        )
        try:
            if commit:
                job = JobService(self.db).create_job(**create_kwargs)
            else:
                # Isolate a unique-key race without rolling back the queue item's
                # surrounding unit of work.
                with self.db.begin_nested():
                    job = JobService(self.db).create_job(**create_kwargs)
        except IntegrityError:
            # Two Start/Download clicks can race between the preflight SELECT and
            # the unique insert. The loser returns the winner's durable job.
            if commit:
                self.db.rollback()
            if not effective_idempotency_key:
                raise
            job = self.db.scalar(
                select(Job).where(
                    Job.workspace_id == source_video.workspace_id,
                    Job.idempotency_key == effective_idempotency_key,
                )
            )
            if job is None:
                raise
            if job.job_type != JobType.DOWNLOAD_VIDEO or job.source_video_id != source_video.id:
                raise DownloadError(
                    DownloadErrorCode.VALIDATION_FAILED,
                    "Idempotency key race resolved to a different download command",
                )
            existing_payload = dict(job.payload_json or {})
            existing_account = existing_payload.get("account_connection_id")
            if str(existing_account or "") != str(account_connection_id or ""):
                raise DownloadError(
                    DownloadErrorCode.VALIDATION_FAILED,
                    "Idempotency key race resolved to a different Douyin account",
                )
            if bool(existing_payload.get("force_refresh")) != bool(request.force_refresh):
                raise DownloadError(
                    DownloadErrorCode.VALIDATION_FAILED,
                    "Idempotency key race resolved to a different refresh policy",
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

    def _resolve_effective_account_connection_id(
        self,
        source_video: SourceVideo,
        requested_account_connection_id: UUID | None,
    ) -> UUID | None:
        """Resolve and validate the immutable account binding for a job."""
        account_connection_id = requested_account_connection_id or _source_account_connection_id(source_video)
        if account_connection_id is None:
            # A local env-cookie-only setup is valid, but when an account exists
            # bind the concrete default now so a queued retry cannot switch later.
            account = _account_for_workspace(self.db, source_video.workspace_id)
            resolved_default_id = getattr(account, "id", None)
            return resolved_default_id if isinstance(resolved_default_id, UUID) else None
        if _account_for_workspace(self.db, source_video.workspace_id, account_connection_id) is None:
            raise DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                "Selected Douyin account does not exist in this workspace",
            )
        return account_connection_id

    def run_download(
        self,
        source_video_id: UUID,
        *,
        job_id: UUID | None = None,
        force_refresh: bool = False,
        on_progress: Callable[[str, int | None], None] | None = None,
        account_connection_id: UUID | None = None,
        transfer_id: UUID | str | None = None,
    ) -> dict:
        source_video = self._get_source_video(source_video_id)
        logger.info("download_started", extra={"source_video_id": str(source_video.id)})
        _emit_download_progress(on_progress, "cache_validate", 2)

        assets: list[MediaAsset] = []
        staging_cleanup_after_commit: list[str] = []
        existing_primary = self._current_asset(source_video.id, MediaAssetType.SOURCE_VIDEO_RAW)
        cached_primary = (
            None
            if force_refresh
            else self._validate_cached_asset(
                source_video,
                existing_primary,
                require_video=True,
            )
        )
        if cached_primary is not None:
            assets.append(cached_primary)
            _emit_download_progress(on_progress, "cache_hit", 82)
            context = self._storage_context(source_video)
        else:
            _emit_download_progress(on_progress, "resolve_session", 7)
            account_connection_id = account_connection_id or _source_account_connection_id(source_video)
            download_session = resolve_douyin_download_session(
                self.db,
                source_video.workspace_id,
                account_connection_id=account_connection_id,
            )
            _emit_download_progress(on_progress, "resolve_candidates", 12)

            def transfer_progress(bytes_done: int, bytes_total: int | None) -> None:
                if bytes_total and bytes_total > 0:
                    fraction = max(0.0, min(1.0, bytes_done / bytes_total))
                    percent = 15 + int(round(fraction * 62))
                else:
                    percent = 25
                _emit_download_progress(
                    on_progress,
                    f"transfer_primary|{max(0, int(bytes_done))}|{max(0, int(bytes_total or 0))}",
                    percent,
                )

            fetch_kwargs = {
                "job_id": job_id,
                "account_connection_id": account_connection_id,
                "on_transfer_progress": transfer_progress,
            }
            # Keep the optional keyword out of legacy/test adapters when no
            # persisted stable namespace exists; _fetch_primary_video itself
            # falls back to job_id for those older jobs.
            if transfer_id is not None:
                fetch_kwargs["transfer_id"] = transfer_id
            primary_result = self._fetch_primary_video(source_video, download_session, **fetch_kwargs)
            self._enrich_profile_identity_from_download(source_video, primary_result)
            # Download may discover the actual author identity.  Build the
            # storage context only after enrichment so the first raw asset uses
            # the correct operator-facing profile namespace.
            context = self._storage_context(source_video)
            _emit_download_progress(on_progress, "validate_primary", 80)
            assets.append(
                self._persist_primary_video(
                    source_video,
                    context,
                    primary_result,
                    job_id=job_id,
                    # An invalid current row must be replaced even when this was not
                    # an operator-requested force refresh. Otherwise the generic
                    # persistence guard would return the corrupt existing row.
                    force_refresh=force_refresh or existing_primary is not None,
                    defer_cleanup=True,
                )
            )
            if primary_result.downloaded.local_path and primary_result.downloaded.cleanup_local_path:
                staging_cleanup_after_commit.append(primary_result.downloaded.local_path)
            _emit_download_progress(on_progress, "atomic_promote", 86)

        thumbnail_url = _metadata_string(source_video.metadata_json, "thumbnail_url")
        if thumbnail_url:
            _emit_download_progress(on_progress, "thumbnail_optional", 89)
            existing_thumbnail = self._current_asset(source_video.id, MediaAssetType.THUMBNAIL)
            cached_thumbnail = (
                None
                if force_refresh
                else self._validate_cached_asset(
                    source_video,
                    existing_thumbnail,
                    require_video=False,
                )
            )
            if cached_thumbnail is not None:
                assets.append(cached_thumbnail)
            else:
                try:
                    assets.append(
                        self._persist_downloaded_asset(
                            source_video,
                            context,
                            MediaAssetType.THUMBNAIL,
                            thumbnail_url,
                            filename="thumbnail.jpg",
                            job_id=job_id,
                            force_refresh=force_refresh or existing_thumbnail is not None,
                        )
                    )
                except DownloadError as exc:
                    self._register_failed_asset(
                        source_video,
                        context,
                        MediaAssetType.THUMBNAIL,
                        thumbnail_url,
                        exc,
                        job_id,
                    )

        _emit_download_progress(on_progress, "persist_sidecars", 93)
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
        _emit_download_progress(on_progress, "finalize_manifest", 98)
        self.db.commit()
        # Do not delete the resumable staging source until the DB transaction has
        # committed.  If the commit fails, the next retry can still resume or
        # re-probe the completed transfer.
        for staging_path in staging_cleanup_after_commit:
            _remove_staging_path(staging_path)
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

    def _fetch_primary_video(
        self,
        source_video: SourceVideo,
        download_session,
        *,
        job_id: UUID | None = None,
        account_connection_id: UUID | None = None,
        transfer_id: UUID | str | None = None,
        on_transfer_progress: Callable[[int, int | None], None] | None = None,
    ) -> PrimaryVideoFetchResult:
        # The API/queue-selected account is authoritative for this attempt.  Do
        # not recompute it from source metadata after the session was resolved,
        # otherwise the browser/yt-dlp resolver can silently switch accounts.
        account_id = account_connection_id or _source_account_connection_id(source_video)
        fetch_kwargs = dict(
            session_cookie=download_session.session_cookie,
            user_agent=download_session.user_agent,
            proxy_url=download_session.proxy_url,
            playwright_cookies=download_session.playwright_cookies,
            cookie_source=download_session.cookie_source,
            workspace_id=source_video.workspace_id,
            account_connection_id=account_id,
            transfer_id=transfer_id or job_id,
            on_progress=on_transfer_progress,
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
                account_connection_id=account_id,
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
                account_connection_id=account_id,
                transfer_id=job_id,
                on_progress=on_transfer_progress,
            )

    def _persist_primary_video(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        primary_result,
        *,
        job_id: UUID | None,
        force_refresh: bool,
        defer_cleanup: bool = False,
    ) -> MediaAsset:
        from datetime import UTC, datetime

        ext = "mp4"
        resolver_name = getattr(primary_result.downloaded, "filename", None) or ""
        if "." in resolver_name:
            maybe_ext = resolver_name.rsplit(".", 1)[-1].lower()
            if maybe_ext in {"mp4", "webm", "m4v", "mov", "mkv"}:
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
        cleanup_staging = False
        try:
            media_probe = self._validate_downloaded_primary_video(
                context,
                primary_result.downloaded,
                filename=filename,
            )
            extra_metadata = {
                **primary_result.asset_metadata(),
                "media_probe": _video_probe_metadata(media_probe),
                "download_quality_policy": current_quality_policy(get_settings()),
                "post_download_qa": evaluate_post_download_qa(
                    media_probe,
                    advertised_width=getattr(primary_result, "width", None),
                    advertised_height=getattr(primary_result, "height", None),
                    advertised_codec=getattr(primary_result, "codec", None),
                    advertised_fps=getattr(primary_result, "fps", None),
                    expect_audio=True,
                ),
            }
            if primary_result.downloaded.local_path:
                asset = self._persist_file_asset(
                    source_video,
                    context,
                    MediaAssetType.SOURCE_VIDEO_RAW,
                    primary_result.downloaded.local_path,
                    filename=filename,
                    mime_type=primary_result.downloaded.mime_type,
                    source_url=primary_result.source_url,
                    job_id=job_id,
                    force_refresh=force_refresh,
                    extra_metadata=extra_metadata,
                )
            else:
                asset = self._persist_bytes_asset(
                    source_video,
                    context,
                    MediaAssetType.SOURCE_VIDEO_RAW,
                    primary_result.downloaded.content or b"",
                    filename=filename,
                    mime_type=primary_result.downloaded.mime_type,
                    source_url=primary_result.source_url,
                    job_id=job_id,
                    force_refresh=force_refresh,
                    extra_metadata=extra_metadata,
                )
            cleanup_staging = True
            return asset
        except DownloadError as exc:
            # Invalid media is terminal and should not poison the next attempt;
            # transfer/write failures retain the .part artifact for resume.
            cleanup_staging = exc.code == DownloadErrorCode.VALIDATION_FAILED
            raise
        finally:
            if (
                cleanup_staging
                and not defer_cleanup
                and primary_result.downloaded.cleanup_local_path
                and primary_result.downloaded.local_path
            ):
                _remove_staging_path(primary_result.downloaded.local_path)

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

        return self._persist_written_asset(
            source_video,
            asset_type,
            existing=existing,
            version=version,
            logical_key=logical_key,
            write_result=write_result,
            filename=filename,
            mime_type=mime_type,
            source_url=source_url,
            job_id=job_id,
            extra_metadata=extra_metadata,
        )

    def _persist_file_asset(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        asset_type: MediaAssetType,
        source_path: str | Path,
        *,
        filename: str,
        mime_type: str | None,
        source_url: str | None,
        job_id: UUID | None,
        force_refresh: bool,
        extra_metadata: dict | None = None,
    ) -> MediaAsset:
        path = Path(source_path).resolve()
        if not path.is_file() or path.stat().st_size <= 0:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, f"Asset file is empty: {asset_type}")
        existing = self._current_asset(source_video.id, asset_type)
        if existing and not force_refresh and self.storage.exists(existing.storage_key):
            return existing
        version = (existing.version + 1) if existing else 1
        leaf = filename if asset_type == MediaAssetType.SOURCE_VIDEO_RAW else f"v{version}_{filename}"
        logical_key = asset_logical_key(context, asset_type, filename=leaf)
        try:
            promote = getattr(self.storage, "promote_file", None)
            write_result = (
                promote(logical_key, path)
                if callable(promote)
                else self.storage.write_file(logical_key, path)
            )
        except Exception as exc:
            raise DownloadError(DownloadErrorCode.WRITE_FAILED, f"File write failed: {exc}") from exc
        return self._persist_written_asset(
            source_video,
            asset_type,
            existing=existing,
            version=version,
            logical_key=logical_key,
            write_result=write_result,
            filename=filename,
            mime_type=mime_type,
            source_url=source_url,
            job_id=job_id,
            extra_metadata=extra_metadata,
        )

    def _persist_written_asset(
        self,
        source_video: SourceVideo,
        asset_type: MediaAssetType,
        *,
        existing: MediaAsset | None,
        version: int,
        logical_key: str,
        write_result,
        filename: str,
        mime_type: str | None,
        source_url: str | None,
        job_id: UUID | None,
        extra_metadata: dict | None,
    ) -> MediaAsset:

        if write_result.size_bytes <= 0:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, "Written file is empty")

        metadata_json = {
            "absolute_path": write_result.absolute_path,
            **(extra_metadata or {}),
        }
        local_fingerprint = _local_file_fingerprint(write_result.absolute_path)
        if local_fingerprint is not None:
            metadata_json["local_file_fingerprint"] = local_fingerprint
            metadata_json["integrity_verified_at"] = datetime.now(UTC).isoformat()
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

    def _default_media_probes(
        self,
    ) -> tuple[Callable[[str], object] | None, Callable[[str | Path], object] | None]:
        """Use one ffprobe service for both stored assets and completed staging files."""
        if shutil.which("ffprobe") is None:
            return None, None
        from src.render_pipeline.services.video_probe_service import VideoProbeService

        service = VideoProbeService(self.storage)
        return service.probe, service.probe_path

    def _validate_downloaded_primary_video(
        self,
        context: VideoStorageContext,
        downloaded: DownloadedObject,
        *,
        filename: str,
    ) -> object:
        """Fail closed before a response body becomes ``SOURCE_VIDEO_RAW``.

        ``VideoProbeService`` probes storage keys, so the current in-memory downloader
        stages the bytes under a unique, unregistered TEMP_FILE key.  The staging file is
        always removed.  The upcoming streaming downloader can pass its completed ``.part``
        path through the same probe without this extra write.
        """
        try:
            has_payload = downloaded.has_payload
        except OSError as exc:
            raise DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                f"Downloaded primary media staging file could not be read: {exc}",
                reason="media_corrupt",
            ) from exc
        if not has_payload:
            raise DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                "Downloaded primary media payload is empty",
                reason="media_corrupt",
            )
        if self.media_probe is None and self.media_path_probe is None:
            raise DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                "Downloaded primary media cannot be validated because ffprobe is unavailable",
            )

        if downloaded.local_path and self.media_path_probe is not None:
            try:
                probe = self.media_path_probe(downloaded.local_path)
            except Exception as exc:
                raise DownloadError(
                    DownloadErrorCode.VALIDATION_FAILED,
                    f"Downloaded primary media failed ffprobe validation: {type(exc).__name__}: {exc}",
                    reason="media_corrupt",
                ) from exc
            return _require_usable_video_probe(probe)

        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
        if not suffix.isalnum() or len(suffix) > 8:
            suffix = "mp4"
        probe_key = asset_logical_key(
            context,
            MediaAssetType.TEMP_FILE,
            filename=f"download_probe_{uuid4().hex}.{suffix}",
        )
        try:
            try:
                if downloaded.local_path:
                    staged = self.storage.write_file(probe_key, downloaded.local_path)
                else:
                    staged = self.storage.write_bytes(probe_key, downloaded.content or b"")
            except Exception as exc:
                raise DownloadError(
                    DownloadErrorCode.WRITE_FAILED,
                    f"Could not stage downloaded primary media for validation: {exc}",
                ) from exc

            try:
                probe = self.media_probe(staged.storage_key)
            except Exception as exc:
                raise DownloadError(
                    DownloadErrorCode.VALIDATION_FAILED,
                    f"Downloaded primary media failed ffprobe validation: {type(exc).__name__}: {exc}",
                ) from exc

            return _require_usable_video_probe(probe)
        finally:
            try:
                self.storage.delete(probe_key)
            except Exception:
                logger.warning(
                    "download_media_probe_temp_cleanup_failed",
                    extra={"probe_key": probe_key},
                )

    def _validate_cached_asset(
        self,
        source_video: SourceVideo,
        asset: MediaAsset | None,
        *,
        require_video: bool,
    ) -> MediaAsset | None:
        """Return a reusable current asset only after local integrity checks pass."""
        if asset is None:
            return None
        status = getattr(asset.status, "value", asset.status)
        if status != MediaAssetStatus.AVAILABLE.value or not bool(asset.is_current):
            return None

        expected_size = int(asset.size_bytes or 0)
        expected_checksum = str(asset.checksum_sha256 or "").strip().lower()
        errors: list[str] = []
        if expected_size <= 0:
            errors.append("missing_expected_size")
        if len(expected_checksum) != 64:
            errors.append("missing_expected_checksum")
        if require_video:
            metadata = dict(getattr(asset, "metadata_json", None) or {})
            stored_policy = dict(metadata.get("download_quality_policy") or {})
            expected_policy = current_quality_policy(get_settings())
            # Legacy assets predate the policy fingerprint. Keep them reusable
            # after the normal checksum/probe validation; only a fingerprinted
            # asset whose policy actually changed is a quality-policy miss.
            if stored_policy and str(stored_policy.get("fingerprint") or "") != str(
                expected_policy.get("fingerprint") or ""
            ):
                errors.append("download_quality_policy_stale")

        if require_video and self.media_probe is None and self.media_path_probe is None:
            errors.append("media_probe_unavailable")
        if not errors and _fast_cache_fingerprint_valid(
            self.storage,
            asset,
            expected_size=expected_size,
            require_video=require_video,
        ):
            logger.info(
                "download_asset_cache_hit_fast",
                extra={
                    "source_video_id": str(source_video.id),
                    "asset_type": str(asset.asset_type),
                    "size_bytes": expected_size,
                },
            )
            return asset

        try:
            health = validate_asset_health(
                self.storage,
                asset.storage_key,
                expected_checksum_sha256=expected_checksum or None,
            )
        except Exception as exc:
            logger.warning(
                "download_asset_cache_validation_failed",
                extra={
                    "source_video_id": str(source_video.id),
                    "asset_type": str(asset.asset_type),
                    "error": type(exc).__name__,
                },
            )
            return None

        errors.extend(health.errors)
        if expected_size > 0 and health.size_bytes != expected_size:
            errors.append("size_mismatch")
        if expected_checksum and health.checksum_sha256 != expected_checksum:
            errors.append("checksum_mismatch")

        if not errors and require_video and (self.media_probe is not None or self.media_path_probe is not None):
            try:
                if self.media_path_probe is not None:
                    probe = self.media_path_probe(self.storage.resolve(asset.storage_key).absolute_path)
                else:
                    assert self.media_probe is not None
                    probe = self.media_probe(asset.storage_key)
            except Exception as exc:
                logger.warning(
                    "download_asset_cache_probe_failed",
                    extra={
                        "source_video_id": str(source_video.id),
                        "asset_type": str(asset.asset_type),
                        "error": type(exc).__name__,
                    },
                )
                return None
            if not _is_usable_video_probe(probe):
                errors.append("invalid_video_stream")

        if errors:
            logger.info(
                "download_asset_cache_miss",
                extra={
                    "source_video_id": str(source_video.id),
                    "asset_type": str(asset.asset_type),
                    "reasons": sorted(set(errors)),
                },
            )
            return None

        metadata = dict(getattr(asset, "metadata_json", None) or {})
        resolved_path = self.storage.resolve(asset.storage_key).absolute_path
        fingerprint = _local_file_fingerprint(resolved_path)
        if fingerprint is not None:
            metadata["local_file_fingerprint"] = fingerprint
            metadata["integrity_verified_at"] = datetime.now(UTC).isoformat()
            if require_video and "probe" in locals():
                metadata["media_probe"] = _video_probe_metadata(probe)
            asset.metadata_json = metadata
            self.db.flush()

        logger.info(
            "download_asset_cache_hit",
            extra={
                "source_video_id": str(source_video.id),
                "asset_type": str(asset.asset_type),
                "size_bytes": health.size_bytes,
            },
        )
        return asset

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


def _stable_transfer_id(
    source_video_id: UUID,
    account_connection_id: UUID | None,
    command_key: str,
) -> str:
    """Return a stable, path-safe transfer namespace across job recreation.

    Queue Hold/Resume intentionally creates a new terminal job row. Binding
    staging to the job UUID would strand a valid HTTP ``.part`` file and force a
    full re-download. The command key is stable for that queue item, while the
    hash keeps credentials and arbitrary caller text out of filesystem paths.
    """
    material = "|".join(
        (
            str(source_video_id),
            str(account_connection_id or "unbound"),
            str(command_key),
        )
    ).encode("utf-8")
    return f"transfer-{hashlib.sha256(material).hexdigest()[:32]}"


def _source_account_connection_id(source_video: SourceVideo) -> UUID | None:
    metadata = dict(getattr(source_video, "metadata_json", None) or {})
    raw = (
        metadata.get("resolved_douyin_account_connection_id")
        or metadata.get("selected_douyin_account_connection_id")
        or metadata.get("douyin_account_connection_id")
    )
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        raise DownloadError(
            DownloadErrorCode.VALIDATION_FAILED,
            "Source video has an invalid Douyin account binding",
        )


def _emit_download_progress(
    callback: Callable[[str, int | None], None] | None,
    phase: str,
    percent: int | None,
) -> None:
    if callback is None:
        return
    callback(phase, None if percent is None else max(0, min(99, int(percent))))


def _is_usable_video_probe(probe: object) -> bool:
    def positive(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

    return bool(
        positive(getattr(probe, "width", None))
        and positive(getattr(probe, "height", None))
        and positive(getattr(probe, "duration_seconds", None))
        and str(getattr(probe, "video_codec", None) or "").strip()
    )


def _require_usable_video_probe(probe: object) -> object:
    if _is_usable_video_probe(probe):
        return probe
    audio_codec = str(getattr(probe, "audio_codec", None) or "").strip()
    reason = "audio-only payload" if audio_codec else "invalid or non-video payload"
    raise DownloadError(
        DownloadErrorCode.VALIDATION_FAILED,
        f"Downloaded primary media has no usable video stream ({reason})",
        reason="media_corrupt",
    )


def _remove_staging_path(path: str | Path) -> None:
    """Remove only files created under the managed download staging root."""
    from src.downloaders.download_staging import is_managed_staging_path

    candidate = Path(path).resolve()
    if not is_managed_staging_path(candidate):
        logger.warning("download_staging_cleanup_skipped_outside_root", extra={"path_name": candidate.name})
        return
    try:
        candidate.unlink(missing_ok=True)
        companion_names = {
            f"{candidate.name}.resume.json",
            f"{candidate.stem}.info.json",
            f"{candidate.name}.part",
            f"{candidate.name}.ytdl",
            f"{candidate.stem}.part",
            f"{candidate.stem}.ytdl",
        }
        for sibling in list(candidate.parent.iterdir()):
            if not sibling.is_file() or sibling == candidate:
                continue
            if sibling.name in companion_names:
                sibling.unlink(missing_ok=True)
        # Remove only empty transfer/aweme/account directories; never recurse.
        for parent in (candidate.parent, candidate.parent.parent, candidate.parent.parent.parent):
            try:
                parent.rmdir()
            except OSError:
                break
    except OSError:
        logger.warning("download_staging_cleanup_failed", extra={"path_name": candidate.name}, exc_info=True)


def _video_probe_metadata(probe: object) -> dict[str, object]:
    """Persist a bounded technical summary, never the temporary probe path."""
    raw = getattr(probe, "raw", None)
    raw = raw if isinstance(raw, dict) else {}
    audio_codec = str(getattr(probe, "audio_codec", None) or "").strip() or None
    audio_stream_count = raw.get("audio_stream_count")
    if not isinstance(audio_stream_count, int) or audio_stream_count < 0:
        audio_stream_count = 1 if audio_codec is not None else 0
    return {
        "probe_strategy": str(raw.get("probe_strategy") or "ffprobe"),
        "width": getattr(probe, "width", None),
        "height": getattr(probe, "height", None),
        "fps": getattr(probe, "fps", None),
        "duration_seconds": getattr(probe, "duration_seconds", None),
        "video_codec": str(getattr(probe, "video_codec", None) or "").strip() or None,
        "audio_codec": audio_codec,
        "audio_stream_count": audio_stream_count,
        "has_audio": audio_stream_count > 0,
    }


def _local_file_fingerprint(path: str | Path) -> dict[str, int] | None:
    try:
        stat = Path(path).resolve().stat()
    except OSError:
        return None
    return {
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "file_id": int(getattr(stat, "st_ino", 0) or 0),
    }


def _fast_cache_fingerprint_valid(
    storage,
    asset,
    *,
    expected_size: int,
    require_video: bool,
) -> bool:
    if str(getattr(storage, "provider_name", "")) != "local":
        return False
    metadata = dict(getattr(asset, "metadata_json", None) or {})
    expected = metadata.get("local_file_fingerprint")
    if not isinstance(expected, dict):
        return False
    verified_raw = metadata.get("integrity_verified_at")
    if not isinstance(verified_raw, str):
        return False
    try:
        verified_at = datetime.fromisoformat(verified_raw.replace("Z", "+00:00"))
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=UTC)
    except ValueError:
        return False
    settings = get_settings()
    raw_hours = getattr(settings, "douyin_download_cache_deep_verify_interval_hours", 24.0)
    try:
        interval_hours = float(raw_hours) if isinstance(raw_hours, (int, float, str)) else 24.0
    except (TypeError, ValueError):
        interval_hours = 24.0
    if interval_hours <= 0 or (datetime.now(UTC) - verified_at).total_seconds() > interval_hours * 3600:
        return False
    try:
        current = _local_file_fingerprint(storage.resolve(asset.storage_key).absolute_path)
    except Exception:
        return False
    if current is None or current != expected or current.get("size_bytes") != expected_size:
        return False
    if require_video:
        probe = metadata.get("media_probe")
        if not isinstance(probe, dict):
            return False
        if not (
            isinstance(probe.get("width"), (int, float))
            and probe.get("width", 0) > 0
            and isinstance(probe.get("height"), (int, float))
            and probe.get("height", 0) > 0
            and isinstance(probe.get("duration_seconds"), (int, float))
            and probe.get("duration_seconds", 0) > 0
            and str(probe.get("video_codec") or "").strip()
        ):
            return False
    return True
