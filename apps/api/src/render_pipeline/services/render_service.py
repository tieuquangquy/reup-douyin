from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from src.core.settings import get_settings
from src.enums import JobType, MediaAssetStatus, MediaAssetType, RenderOutputStatus, SourceVideoStatus
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset, RenderOutput
from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.runners.base import ExportRunner
from src.render_pipeline.runners.ffmpeg_runner import FfmpegRenderRunner
from src.render_pipeline.services.output_validator import validate_render_output
from src.render_pipeline.services.render_input_resolver import RenderInputResolver
from src.render_pipeline.services.render_manifest_builder import build_render_manifest
from src.render_pipeline.services.video_probe_service import VideoProbeService
from src.render_pipeline.types import RENDER_PIPELINE_VERSION, ExportInput, RenderPipelineResult, RenderProfile, RenderRequest
from src.services.job_service import JobService
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend
from src.storage.path_strategy import VideoStorageContext, asset_logical_key
from src.tts_pipeline.services.subtitle_builder import prepare_srt_file_for_burn

logger = logging.getLogger(__name__)


class RenderService:
    def __init__(
        self,
        db: Session,
        *,
        storage: StorageBackend | None = None,
        runner: ExportRunner | None = None,
    ):
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)
        self.runner = runner or FfmpegRenderRunner()
        self.probe_service = VideoProbeService(self.storage)

    def create_render_job(self, request: RenderRequest):
        source_video = self._load_source_video(request.source_video_id)
        job = JobService(self.db).create_job(
            job_type=JobType.RENDER_FINAL,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "render_mode": request.render_mode,
                "force_refresh": request.force_refresh,
            },
            idempotency_key=None,
        )
        logger.info("render_job_created", extra={"job_id": str(job.id), "source_video_id": str(source_video.id)})
        return job

    def run_render(self, request: RenderRequest, *, job_id: UUID | None = None) -> RenderPipelineResult:
        source_video = self._load_source_video(request.source_video_id)
        context = self._storage_context(source_video)
        render_version = self._next_render_version(source_video.id)
        profile = RenderProfile()
        started_at = datetime.now(UTC)
        render_output = RenderOutput(
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            status=RenderOutputStatus.RENDERING,
            render_type=request.render_mode,
            target_platform="generic",
            version=self._version_number(render_version),
            output_format=profile.output_format,
            subtitle_burned=profile.subtitle_burned,
            audio_strategy=profile.audio_strategy,
            render_version=render_version,
            created_by_job_id=job_id,
            started_at=started_at,
            render_settings_json=profile.__dict__,
        )
        self.db.add(render_output)
        self.db.flush()

        try:
            self._mark_previous_render_assets_non_current(source_video.id)
            resolved = RenderInputResolver(self.db, self.storage).resolve(source_video.id)
            source_probe = self.probe_service.probe(resolved.source_video_storage_key)
            output_key = asset_logical_key(context, MediaAssetType.FINAL_RENDER_VIDEO, filename=f"{render_version}_final.mp4")
            output_path = str(self.storage.resolve(output_key).absolute_path)
            source_subtitle_path = str(self.storage.resolve(resolved.subtitle_storage_key).absolute_path)
            burn_subtitle_path, subtitle_burn_warnings = prepare_srt_file_for_burn(source_subtitle_path)
            export_result = self.runner.export(
                ExportInput(
                    source_video_path=str(self.storage.resolve(resolved.source_video_storage_key).absolute_path),
                    narration_path=str(self.storage.resolve(resolved.narration_storage_key).absolute_path),
                    subtitle_path=burn_subtitle_path,
                    output_path=output_path,
                    profile=profile,
                    source_probe=source_probe,
                )
            )
            output_probe = self.probe_service.probe(output_key)
            validate_render_output(export_result.output_path, output_probe, source_probe)
            output_asset = self._register_existing_file_asset(
                source_video,
                output_key,
                MediaAssetType.FINAL_RENDER_VIDEO,
                mime_type="video/mp4",
                manifest_group="render_outputs",
                job_id=job_id,
            )
            log_asset = self._persist_asset(
                source_video,
                context,
                MediaAssetType.RENDER_LOG,
                export_result.log_text.encode("utf-8") or b"render completed",
                filename=f"{render_version}_render.log",
                mime_type="text/plain",
                manifest_group="render_debug",
                job_id=job_id,
                metadata={"command": export_result.command},
            )
            merged_warnings = _dedupe_warnings(
                [
                    *(resolved.render_prep_manifest.get("warnings") or []),
                    *subtitle_burn_warnings,
                    *export_result.warnings,
                ]
            )
            manifest = build_render_manifest(
                source_video_id=str(source_video.id),
                render_output_id=str(render_output.id),
                render_version=render_version,
                resolved_input=resolved,
                output_asset={
                    "id": str(output_asset.id),
                    "storage_key": output_asset.storage_key,
                    "mime_type": output_asset.mime_type,
                    "asset_type": output_asset.asset_type,
                },
                render_profile=profile,
                input_probe=source_probe,
                output_probe=output_probe,
                warnings=merged_warnings,
                job_id=str(job_id) if job_id else None,
            )
            manifest_asset = self._persist_json_asset(
                source_video,
                context,
                MediaAssetType.RENDER_MANIFEST,
                manifest,
                filename=f"{render_version}_render_manifest.json",
                manifest_group="render_debug",
                job_id=job_id,
            )
            render_output.status = RenderOutputStatus.READY_FOR_REVIEW
            render_output.media_asset_id = output_asset.id
            render_output.width = output_probe.width or source_probe.width
            render_output.height = output_probe.height or source_probe.height
            render_output.fps = output_probe.fps or source_probe.fps
            render_output.duration_seconds = output_probe.duration_seconds or source_probe.duration_seconds
            render_output.video_codec = profile.video_codec
            render_output.audio_codec = profile.audio_codec
            render_output.warning_summary_json = {"warnings": merged_warnings}
            render_output.metadata_json = {"render_manifest_asset_id": str(manifest_asset.id), "render_log_asset_id": str(log_asset.id), "manifest": manifest}
            render_output.finished_at = datetime.now(UTC)
            source_video.status = SourceVideoStatus.READY_FINAL_REVIEW
            self.db.commit()
        except RenderPipelineError as exc:
            render_output.status = RenderOutputStatus.FAILED
            render_output.error_message = f"{exc.code}: {exc.message}"
            render_output.finished_at = datetime.now(UTC)
            self.db.commit()
            raise
        except Exception as exc:
            self.db.rollback()
            raise RenderPipelineError(RenderPipelineErrorCode.PERSISTENCE_FAILED, f"Render failed: {exc}") from exc

        return RenderPipelineResult(
            render_output_id=render_output.id,
            output_asset_id=output_asset.id,
            render_version=render_version,
            manifest=manifest,
            warnings=merged_warnings,
        )

    def list_renders(self, source_video_id: UUID) -> list[RenderOutput]:
        return list(
            self.db.scalars(
                select(RenderOutput)
                .where(RenderOutput.source_video_id == source_video_id)
                .order_by(RenderOutput.created_at.desc())
            )
        )

    def get_render(self, render_id: UUID) -> RenderOutput:
        render = self.db.get(RenderOutput, render_id)
        if render is None:
            raise RenderPipelineError(RenderPipelineErrorCode.MISSING_RENDER_PREP_MANIFEST, "Render output not found")
        return render

    def approve_render(self, render_id: UUID) -> RenderOutput:
        render = self.get_render(render_id)
        if render.status not in {RenderOutputStatus.READY_FOR_REVIEW, RenderOutputStatus.APPROVED}:
            raise RenderPipelineError(
                RenderPipelineErrorCode.OUTPUT_VALIDATION_FAILED,
                f"Render output cannot be approved from status {render.status}",
            )
        render.status = RenderOutputStatus.APPROVED
        render.metadata_json = self._merge_final_review_metadata(render.metadata_json, {"approved_at": datetime.now(UTC).isoformat()})
        self.db.commit()
        self.db.refresh(render)
        logger.info("render_output_approved", extra={"render_id": str(render.id), "source_video_id": str(render.source_video_id)})
        return render

    def mark_publish_ready(self, render_id: UUID) -> RenderOutput:
        render = self.approve_render(render_id)
        source_video = self._load_source_video(render.source_video_id)
        source_video.status = SourceVideoStatus.PUBLISH_READY
        render.metadata_json = self._merge_final_review_metadata(
            render.metadata_json,
            {
                "publish_ready_at": datetime.now(UTC).isoformat(),
                "publish_ready_source_video_id": str(source_video.id),
            },
        )
        self.db.commit()
        self.db.refresh(render)
        logger.info("source_video_marked_publish_ready", extra={"render_id": str(render.id), "source_video_id": str(source_video.id)})
        return render

    def latest_render(self, source_video_id: UUID) -> RenderOutput | None:
        return self.db.scalar(
            select(RenderOutput)
            .where(RenderOutput.source_video_id == source_video_id)
            .order_by(RenderOutput.created_at.desc())
            .limit(1)
        )

    def _load_source_video(self, source_video_id: UUID) -> SourceVideo:
        source_video = self.db.scalar(
            select(SourceVideo).where(SourceVideo.id == source_video_id).options(selectinload(SourceVideo.source_profile))
        )
        if source_video is None:
            raise RenderPipelineError(RenderPipelineErrorCode.MISSING_SOURCE_VIDEO_ASSET, "Source video not found")
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

    def _next_render_version(self, source_video_id: UUID) -> str:
        max_version = self.db.scalar(select(func.max(RenderOutput.version)).where(RenderOutput.source_video_id == source_video_id))
        return f"{RENDER_PIPELINE_VERSION}_RUN_{(max_version or 0) + 1}"

    def _version_number(self, version: str) -> int:
        return int(version.rsplit("_", 1)[-1])

    def _mark_previous_render_assets_non_current(self, source_video_id: UUID) -> None:
        self.db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type.in_([MediaAssetType.FINAL_RENDER_VIDEO, MediaAssetType.RENDER_LOG, MediaAssetType.RENDER_DEBUG_JSON, MediaAssetType.RENDER_MANIFEST]),
            )
            .values(is_current=False)
        )

    def _register_existing_file_asset(self, source_video: SourceVideo, logical_key: str, asset_type: MediaAssetType, *, mime_type: str, manifest_group: str, job_id: UUID | None) -> MediaAsset:
        metadata = self.storage.metadata(logical_key)
        if not metadata.exists or not metadata.size_bytes:
            raise RenderPipelineError(RenderPipelineErrorCode.OUTPUT_VALIDATION_FAILED, "Rendered output asset missing after export")
        asset = MediaAsset(
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            asset_type=asset_type,
            status=MediaAssetStatus.AVAILABLE,
            version=self._next_asset_version(source_video.id, asset_type),
            storage_provider=self.storage.provider_name,
            storage_key=logical_key,
            logical_key=logical_key,
            relative_path=logical_key,
            manifest_group=manifest_group,
            is_current=True,
            created_by_job_id=job_id,
            mime_type=mime_type,
            size_bytes=metadata.size_bytes,
            checksum_sha256=metadata.checksum_sha256,
            metadata_json={"absolute_path": metadata.absolute_path},
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def _persist_json_asset(self, source_video: SourceVideo, context: VideoStorageContext, asset_type: MediaAssetType, payload: dict, *, filename: str, manifest_group: str, job_id: UUID | None) -> MediaAsset:
        return self._persist_asset(source_video, context, asset_type, json.dumps(payload, ensure_ascii=True, indent=2, default=str).encode("utf-8"), filename=filename, mime_type="application/json", manifest_group=manifest_group, job_id=job_id, metadata={"manifest": payload} if asset_type == MediaAssetType.RENDER_MANIFEST else {})

    def _persist_asset(self, source_video: SourceVideo, context: VideoStorageContext, asset_type: MediaAssetType, content: bytes, *, filename: str, mime_type: str, manifest_group: str, job_id: UUID | None, metadata: dict | None = None) -> MediaAsset:
        logical_key = asset_logical_key(context, asset_type, filename=f"v{self._next_asset_version(source_video.id, asset_type)}_{filename}")
        write_result = self.storage.write_bytes(logical_key, content)
        asset = MediaAsset(
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            asset_type=asset_type,
            status=MediaAssetStatus.AVAILABLE,
            version=self._next_asset_version(source_video.id, asset_type),
            storage_provider=write_result.storage_provider,
            storage_key=write_result.storage_key,
            logical_key=logical_key,
            relative_path=write_result.relative_path,
            manifest_group=manifest_group,
            is_current=True,
            created_by_job_id=job_id,
            mime_type=mime_type,
            size_bytes=write_result.size_bytes,
            checksum_sha256=write_result.checksum_sha256,
            metadata_json={**(metadata or {}), "absolute_path": write_result.absolute_path},
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def _next_asset_version(self, source_video_id: UUID, asset_type: MediaAssetType) -> int:
        max_version = self.db.scalar(select(func.max(MediaAsset.version)).where(MediaAsset.source_video_id == source_video_id, MediaAsset.asset_type == asset_type))
        return (max_version or 0) + 1

    def _merge_final_review_metadata(self, metadata: dict | None, patch: dict) -> dict:
        next_metadata = dict(metadata or {})
        final_review = dict(next_metadata.get("final_review") or {})
        final_review.update(patch)
        next_metadata["final_review"] = final_review
        return next_metadata


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in warnings if isinstance(item, str) and item))
