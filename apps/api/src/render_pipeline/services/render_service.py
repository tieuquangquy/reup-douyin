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
        from src.services.quality_localization_service import (
            QUALITY_METADATA_KEY,
            QUALITY_WORKFLOW_VERSION,
            QualityLocalizationService,
        )
        from src.services.pipeline_recipe_runtime import bind_job_to_recipe_reference

        quality_summary = QualityLocalizationService(self.db, storage=self.storage).summary(source_video.id)
        quality_state = dict(dict(source_video.metadata_json or {}).get(QUALITY_METADATA_KEY) or {})
        quality_active = quality_summary.get("workflow_stage") != "NOT_STARTED"
        workflow_version = QUALITY_WORKFLOW_VERSION if quality_active else request.workflow_version
        if workflow_version == QUALITY_WORKFLOW_VERSION and not bool(quality_summary.get("can_render_final")):
            raise RenderPipelineError(
                RenderPipelineErrorCode.QUALITY_REVIEW_REQUIRED,
                f"Quality localization is at {quality_summary.get('workflow_stage')}; "
                "visual review and explicit audio approval are required",
            )
        recipe_reference = quality_state.get("pipeline_recipe_lock")
        if workflow_version == QUALITY_WORKFLOW_VERSION and (
            not isinstance(recipe_reference, dict) or not recipe_reference
        ):
            raise RenderPipelineError(
                RenderPipelineErrorCode.PIPELINE_RECIPE_WORKFLOW_MISMATCH,
                "Quality localization has no immutable pipeline recipe reference",
            )
        job = JobService(self.db).create_job(
            job_type=JobType.RENDER_FINAL,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "render_mode": request.render_mode,
                "force_refresh": request.force_refresh,
                "workflow_version": workflow_version,
            },
            idempotency_key=None,
        )
        if workflow_version == QUALITY_WORKFLOW_VERSION:
            bind_job_to_recipe_reference(job, recipe_reference)
            self.db.commit()
        logger.info("render_job_created", extra={"job_id": str(job.id), "source_video_id": str(source_video.id)})
        return job

    def run_render(self, request: RenderRequest, *, job_id: UUID | None = None) -> RenderPipelineResult:
        source_video = self._load_source_video(request.source_video_id)
        context = self._storage_context(source_video)
        from src.services.quality_localization_service import (
            QUALITY_WORKFLOW_VERSION,
            QualityLocalizationService,
        )

        quality_service = QualityLocalizationService(self.db, storage=self.storage)
        quality_summary = quality_service.summary(source_video.id)
        quality_expected = request.workflow_version == QUALITY_WORKFLOW_VERSION
        if quality_expected and not bool(quality_summary.get("can_render_final")):
            raise RenderPipelineError(
                RenderPipelineErrorCode.QUALITY_REVIEW_REQUIRED,
                f"Quality localization is at {quality_summary.get('workflow_stage')}; "
                "visual review and explicit audio approval are required",
            )
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

        if quality_expected:
            return self._run_quality_adaptive_render(
                request=request,
                source_video=source_video,
                render_output=render_output,
                render_version=render_version,
                profile=profile,
                started_at=started_at,
                job_id=job_id,
                quality_service=quality_service,
            )

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
                    "asset_type": str(getattr(output_asset.asset_type, "value", output_asset.asset_type)),
                    "size_bytes": output_asset.size_bytes,
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
            render_meta = {
                "render_manifest_asset_id": str(manifest_asset.id),
                "render_log_asset_id": str(log_asset.id),
                "manifest": manifest,
            }
            if job_id is not None:
                render_meta["created_by_job_id"] = str(job_id)
            else:
                logger.warning(
                    "render_completed_without_job_id",
                    extra={"render_output_id": str(render_output.id), "source_video_id": str(source_video.id)},
                )
            render_output.metadata_json = render_meta
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

    def _run_quality_adaptive_render(
        self,
        *,
        request: RenderRequest,
        source_video: SourceVideo,
        render_output: RenderOutput,
        render_version: str,
        profile: RenderProfile,
        started_at: datetime,
        job_id: UUID | None,
        quality_service,
    ) -> RenderPipelineResult:
        """Persist the same adaptive Phase 4 output validated by regression."""

        try:
            self._mark_previous_render_assets_non_current(source_video.id)
            final_path = quality_service.run_final_adaptive(
                source_video.id,
                operator_id="frontend_operator",
            )
            output_key = final_path.resolve().relative_to(self.storage.root).as_posix()
            output_probe = self.probe_service.probe(output_key)
            output_asset = self._register_existing_file_asset(
                source_video,
                output_key,
                MediaAssetType.FINAL_RENDER_VIDEO,
                mime_type="video/mp4",
                manifest_group="quality_adaptive_final",
                job_id=job_id,
            )
            root = final_path.parent
            adaptive_meta = json.loads(
                (root / "phase4_adaptive_render_meta.json").read_text(
                    encoding="utf-8"
                )
            )
            output_qa_path = root / "qa" / "phase4_adaptive_final_output_qa.json"
            output_qa = json.loads(output_qa_path.read_text(encoding="utf-8"))
            warnings = [str(value) for value in list(output_qa.get("warnings") or [])]
            manifest = {
                "schema_version": "quality_adaptive_render_manifest_v1",
                "pipeline_version": "QUALITY_LOCALIZATION_V24_1",
                "source_video_id": str(source_video.id),
                "render_output_id": str(render_output.id),
                "render_version": render_version,
                "output": {
                    "media_asset_id": str(output_asset.id),
                    "storage_key": output_asset.storage_key,
                    "sha256": output_asset.checksum_sha256,
                    "size_bytes": output_asset.size_bytes,
                },
                "adaptive_render_meta": adaptive_meta,
                "output_qa": output_qa,
                "artifact_root": root.relative_to(self.storage.root).as_posix(),
            }
            context = self._storage_context(source_video)
            manifest_asset = self._persist_json_asset(
                source_video,
                context,
                MediaAssetType.RENDER_MANIFEST,
                manifest,
                filename=f"{render_version}_quality_adaptive_manifest.json",
                manifest_group="render_debug",
                job_id=job_id,
            )
            render_output.status = RenderOutputStatus.READY_FOR_REVIEW
            render_output.media_asset_id = output_asset.id
            render_output.width = output_probe.width
            render_output.height = output_probe.height
            render_output.fps = output_probe.fps
            render_output.duration_seconds = output_probe.duration_seconds
            render_output.video_codec = output_probe.video_codec or profile.video_codec
            render_output.audio_codec = output_probe.audio_codec or profile.audio_codec
            render_output.subtitle_burned = True
            render_output.audio_strategy = str(
                dict(adaptive_meta.get("audio_mix") or {}).get("strategy")
                or "quality_adaptive_mix"
            )
            render_output.render_version = render_version
            render_output.warning_summary_json = {"warnings": warnings}
            render_output.metadata_json = {
                "render_manifest_asset_id": str(manifest_asset.id),
                "manifest": manifest,
                "quality_workflow": True,
                "created_by_job_id": str(job_id) if job_id else None,
            }
            render_output.started_at = started_at
            render_output.finished_at = datetime.now(UTC)
            self._mark_superseded_render_outputs(source_video.id, render_output.id)
            source_video.status = SourceVideoStatus.READY_FINAL_REVIEW
            self.db.commit()
            return RenderPipelineResult(
                render_output_id=render_output.id,
                output_asset_id=output_asset.id,
                render_version=render_version,
                manifest=manifest,
                warnings=warnings,
            )
        except Exception as exc:
            self.db.rollback()
            raise RenderPipelineError(
                RenderPipelineErrorCode.PERSISTENCE_FAILED,
                f"Adaptive quality render failed: {exc}",
            ) from exc

    def list_renders(self, source_video_id: UUID) -> list[RenderOutput]:
        return [
            self._hydrate_render_display_fields(render)
            for render in self.db.scalars(
                select(RenderOutput)
                .where(RenderOutput.source_video_id == source_video_id)
                .order_by(RenderOutput.created_at.desc())
            )
        ]

    def get_render(self, render_id: UUID) -> RenderOutput:
        render = self.db.get(RenderOutput, render_id)
        if render is None:
            raise RenderPipelineError(RenderPipelineErrorCode.MISSING_RENDER_PREP_MANIFEST, "Render output not found")
        return self._hydrate_render_display_fields(render)

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
        self._sync_reup_queue_ready_to_export(render)
        self.db.commit()
        self.db.refresh(render)
        logger.info("source_video_marked_publish_ready", extra={"render_id": str(render.id), "source_video_id": str(source_video.id)})
        return render

    def _sync_reup_queue_ready_to_export(self, render: RenderOutput) -> None:
        """Reconcile a successful manual Final Review back to its queue item.

        Final Review retries create independent RENDER_FINAL jobs.  Without this
        reconciliation an earlier failed auto job leaves the Reup Queue tile in
        FAILED_NEEDS_ATTENTION even though a later approved output is durable.
        """
        from src.enums import ReupQueueMediaPrepStatus, ReupQueueStatus
        from src.models.reup_queue import ReupQueueItem

        terminal = {
            ReupQueueStatus.COMPLETED,
            ReupQueueStatus.CANCELLED,
            ReupQueueStatus.PUBLISH_HANDOFF_CREATED,
        }
        now = datetime.now(UTC)
        items = list(
            self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.source_video_id == render.source_video_id
                )
            )
        )
        for item in items:
            if item.status in terminal:
                continue
            item.status = ReupQueueStatus.READY_TO_EXPORT
            item.media_prep_status = ReupQueueMediaPrepStatus.READY_FOR_EXPORT
            item.render_output_id = render.id
            if render.created_by_job_id is not None:
                item.job_id = render.created_by_job_id
            item.media_ready_at = item.media_ready_at or now
            item.blocked_reason = None
            item.blocked_at = None
            item.failed_at = None
            item.last_error_code = None
            item.last_error_message = None
            item.last_action_at = now
            item.last_action_note = (
                "Final Review approved; adaptive output is ready for manual export."
            )
            item.metadata_json = {
                **dict(item.metadata_json or {}),
                "render_qa": {
                    "status": "pass",
                    "summary": "Adaptive encoded-output QA PASS",
                    "failed": [],
                    "warned": [],
                },
            }

    def latest_render(self, source_video_id: UUID) -> RenderOutput | None:
        render = self.db.scalar(
            select(RenderOutput)
            .where(RenderOutput.source_video_id == source_video_id)
            .order_by(RenderOutput.created_at.desc())
            .limit(1)
        )
        return self._hydrate_render_display_fields(render) if render else None

    def to_render_response(self, render: RenderOutput) -> "RenderOutputResponse":
        from src.schemas.renders import RenderOutputResponse

        hydrated = self._hydrate_render_display_fields(render)
        payload = RenderOutputResponse.model_validate(hydrated)
        return payload.model_copy(update={"size_bytes": self._resolve_size_bytes(hydrated)})

    def _hydrate_render_display_fields(self, render: RenderOutput) -> RenderOutput:
        """Backfill probe fields, size metadata, and job id for Final Review Info."""
        asset = render.media_asset
        if asset is None and render.media_asset_id is not None:
            asset = self.db.get(MediaAsset, render.media_asset_id)

        storage_key = asset.storage_key if asset is not None else None
        probe = None
        needs_probe = (
            render.width is None
            or render.height is None
            or render.fps is None
            or render.duration_seconds is None
            or self._resolve_size_bytes(render, asset=asset) is None
        )
        if needs_probe and storage_key:
            try:
                probe = self.probe_service.probe(storage_key)
            except RenderPipelineError:
                probe = None

        changed = False
        if probe is not None:
            if render.width is None and probe.width is not None:
                render.width = probe.width
                changed = True
            if render.height is None and probe.height is not None:
                render.height = probe.height
                changed = True
            if render.fps is None and probe.fps is not None:
                render.fps = probe.fps
                changed = True
            if render.duration_seconds is None and probe.duration_seconds is not None:
                render.duration_seconds = probe.duration_seconds
                changed = True
            if render.video_codec is None and probe.video_codec:
                render.video_codec = probe.video_codec
                changed = True
            if render.audio_codec is None and probe.audio_codec:
                render.audio_codec = probe.audio_codec
                changed = True

        if render.duration_seconds is None:
            source = self.db.get(SourceVideo, render.source_video_id)
            if source is not None and source.duration_seconds:
                render.duration_seconds = float(source.duration_seconds)
                changed = True

        size_bytes = self._resolve_size_bytes(render, asset=asset, probe=probe)
        meta = dict(render.metadata_json or {})
        nested = dict(meta.get("manifest") or {})
        nested_output = dict(nested.get("output") or {})
        if size_bytes is not None:
            if meta.get("size_bytes") != size_bytes:
                meta["size_bytes"] = size_bytes
                changed = True
            if nested_output.get("size_bytes") != size_bytes:
                nested_output["size_bytes"] = size_bytes
                nested["output"] = nested_output
                changed = True

        if render.created_by_job_id is None:
            recovered = self._recover_job_id(render, asset=asset, manifest=nested)
            if recovered is not None:
                render.created_by_job_id = recovered
                nested["job_id"] = str(recovered)
                meta["created_by_job_id"] = str(recovered)
                changed = True
            else:
                display_job = self._display_job_id_hint(meta=meta, asset=asset, manifest=nested)
                if display_job:
                    if nested.get("job_id") != display_job:
                        nested["job_id"] = display_job
                        changed = True
                    if meta.get("created_by_job_id") != display_job:
                        meta["created_by_job_id"] = display_job
                        changed = True
        else:
            job_s = str(render.created_by_job_id)
            if nested.get("job_id") != job_s:
                nested["job_id"] = job_s
                changed = True
            if meta.get("created_by_job_id") != job_s:
                meta["created_by_job_id"] = job_s
                changed = True

        if nested:
            meta["manifest"] = nested
        if meta != (render.metadata_json or {}):
            render.metadata_json = meta
            changed = True

        if changed:
            self.db.commit()
            self.db.refresh(render)
            logger.info(
                "render_display_fields_hydrated",
                extra={
                    "render_id": str(render.id),
                    "width": render.width,
                    "height": render.height,
                    "fps": render.fps,
                    "duration_seconds": render.duration_seconds,
                    "size_bytes": size_bytes,
                    "created_by_job_id": str(render.created_by_job_id) if render.created_by_job_id else None,
                },
            )
        return render

    def _resolve_size_bytes(
        self,
        render: RenderOutput,
        *,
        asset: MediaAsset | None = None,
        probe=None,
    ) -> int | None:
        meta = render.metadata_json or {}
        nested = meta.get("manifest") if isinstance(meta.get("manifest"), dict) else {}
        nested_output = nested.get("output") if isinstance(nested.get("output"), dict) else {}
        for candidate in (
            meta.get("size_bytes"),
            nested_output.get("size_bytes"),
            getattr(asset, "size_bytes", None) if asset is not None else None,
            (probe.raw or {}).get("size_bytes") if probe is not None else None,
        ):
            try:
                value = int(candidate)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        if asset is None and render.media_asset_id is not None:
            loaded = self.db.get(MediaAsset, render.media_asset_id)
            if loaded is not None and loaded.size_bytes and loaded.size_bytes > 0:
                return int(loaded.size_bytes)
        return None

    def _recover_job_id(
        self,
        render: RenderOutput,
        *,
        asset: MediaAsset | None,
        manifest: dict,
    ) -> UUID | None:
        from src.enums import JobType
        from src.models.jobs import Job, JobStep

        linked = self.db.scalar(
            select(Job)
            .where(Job.render_output_id == render.id)
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        if linked is not None:
            return linked.id

        candidates: list[str] = []
        if isinstance(manifest.get("job_id"), str) and manifest["job_id"].strip():
            candidates.append(manifest["job_id"].strip())
        if asset is not None and asset.created_by_job_id is not None:
            candidates.append(str(asset.created_by_job_id))

        for raw in candidates:
            try:
                job_id = UUID(raw)
            except (TypeError, ValueError):
                continue
            if self.db.get(Job, job_id) is not None:
                return job_id

        steps = list(
            self.db.scalars(
                select(JobStep)
                .join(Job, Job.id == JobStep.job_id)
                .where(
                    Job.source_video_id == render.source_video_id,
                    Job.job_type == JobType.RENDER_FINAL,
                )
                .order_by(Job.created_at.desc())
            )
        )
        render_id = str(render.id)
        for step in steps:
            payload = step.output_json or step.result_json or {}
            if isinstance(payload, dict) and str(payload.get("render_output_id") or "") == render_id:
                return step.job_id
        return None

    def _display_job_id_hint(
        self,
        *,
        meta: dict,
        asset: MediaAsset | None,
        manifest: dict,
    ) -> str | None:
        """Display-only job id that survives FK clear / deleted job rows."""
        for candidate in (
            meta.get("created_by_job_id"),
            manifest.get("job_id"),
            str(asset.created_by_job_id) if asset is not None and asset.created_by_job_id is not None else None,
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

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

    def _mark_superseded_render_outputs(
        self, source_video_id: UUID, current_render_output_id: UUID
    ) -> None:
        """Close abandoned RENDERING rows after a later output is durable."""
        self.db.execute(
            update(RenderOutput)
            .where(
                RenderOutput.source_video_id == source_video_id,
                RenderOutput.id != current_render_output_id,
                RenderOutput.status == RenderOutputStatus.RENDERING,
            )
            .values(
                status=RenderOutputStatus.FAILED,
                error_message="Superseded by a later durable render output",
                finished_at=datetime.now(UTC),
            )
        )

    def _register_existing_file_asset(self, source_video: SourceVideo, logical_key: str, asset_type: MediaAssetType, *, mime_type: str, manifest_group: str, job_id: UUID | None) -> MediaAsset:
        metadata = self.storage.metadata(logical_key)
        if not metadata.exists or not metadata.size_bytes:
            raise RenderPipelineError(RenderPipelineErrorCode.OUTPUT_VALIDATION_FAILED, "Rendered output asset missing after export")
        existing = self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.workspace_id == source_video.workspace_id,
                MediaAsset.storage_key == logical_key,
            )
        )
        if existing is not None:
            if existing.source_video_id != source_video.id:
                raise RenderPipelineError(
                    RenderPipelineErrorCode.PERSISTENCE_FAILED,
                    "Rendered output storage key belongs to another source video",
                )
            existing.asset_type = asset_type
            existing.status = MediaAssetStatus.AVAILABLE
            existing.is_current = True
            existing.logical_key = logical_key
            existing.relative_path = logical_key
            existing.manifest_group = manifest_group
            existing.created_by_job_id = job_id
            existing.mime_type = mime_type
            existing.size_bytes = metadata.size_bytes
            existing.checksum_sha256 = metadata.checksum_sha256
            existing.metadata_json = {
                **dict(existing.metadata_json or {}),
                "absolute_path": metadata.absolute_path,
            }
            existing.error_message = None
            self.db.flush()
            return existing
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
