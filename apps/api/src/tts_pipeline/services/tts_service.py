from __future__ import annotations

import json
import logging
from collections import Counter
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from src.core.settings import get_settings
from src.enums import JobType, MediaAssetStatus, MediaAssetType, SourceVideoStatus, TranscriptSegmentStatus
from src.models.artifacts import SubtitleSegment
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset
from src.services.job_service import JobService
from src.services.workspace_settings_service import WorkspaceSettingsService
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend
from src.storage.path_strategy import VideoStorageContext, asset_logical_key
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.provider_factory import build_default_tts_provider
from src.tts_pipeline.providers import TtsProvider
from src.tts_pipeline.services.narration_assembler import NarrationAssembler
from src.tts_pipeline.services.render_prep_manifest_builder import build_render_prep_manifest
from src.tts_pipeline.services.subtitle_builder import SubtitleBuilder, build_srt
from src.tts_pipeline.services.timing_fit import classify_timing_fit, timing_fit_flags
from src.tts_pipeline.services.translation_input_resolver import TranslationInputResolver
from src.tts_pipeline.services.tts_summary_clips import build_timing_fit_summary, extract_tts_clip_fits
from src.tts_pipeline.types import (
    TTS_PIPELINE_VERSION,
    RenderPrepResult,
    SubtitleDraftSegment,
    SynthesizedSegment,
    TtsProviderInput,
    TtsRequest,
    VoiceConfig,
)

logger = logging.getLogger(__name__)


class TtsPipelineService:
    def __init__(
        self,
        db: Session,
        *,
        storage: StorageBackend | None = None,
        tts_provider: TtsProvider | None = None,
    ):
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)
        self._tts_provider_override = tts_provider
        self.tts_provider = tts_provider or build_default_tts_provider()
        self.subtitle_builder = SubtitleBuilder()
        self.narration_assembler = NarrationAssembler()

    def _provider_for_workspace(self, workspace_id: UUID) -> TtsProvider:
        if self._tts_provider_override is not None:
            return self._tts_provider_override
        workspace_tts = WorkspaceSettingsService(self.db).get_tts_ai(workspace_id)
        return build_default_tts_provider(workspace_tts=workspace_tts)

    def _voice_config_for_request(self, request: TtsRequest, workspace_id: UUID) -> VoiceConfig:
        voice_config = request.voice_config
        workspace_tts = WorkspaceSettingsService(self.db).get_tts_ai(workspace_id)
        settings = get_settings()

        env_voice = (settings.audio_tts_voice_id or "vi-VN-HoaiMyNeural").strip() or "vi-VN-HoaiMyNeural"
        env_rate = float(settings.audio_tts_speaking_rate or 1.0)
        env_lang = "vi"

        # Ops workspace TTS enabled → Ops is authority (Preview/Save match Generate TTS).
        if workspace_tts.enabled:
            voice_id = (workspace_tts.voice_id or "").strip() or env_voice
            language = (workspace_tts.language_code or "").strip() or env_lang
            try:
                rate = float(workspace_tts.speaking_rate or env_rate)
            except (TypeError, ValueError):
                rate = env_rate
            rate = max(0.5, min(2.0, rate))
            return VoiceConfig(voice_id=voice_id, language_code=language, speaking_rate=rate)

        client_voice = (voice_config.voice_id or "").strip()
        if not client_voice or client_voice == "vi_female_placeholder":
            return VoiceConfig(
                voice_id=env_voice,
                language_code=(voice_config.language_code or env_lang).strip() or env_lang,
                speaking_rate=voice_config.speaking_rate if voice_config.speaking_rate else env_rate,
            )
        return VoiceConfig(
            voice_id=client_voice,
            language_code=(voice_config.language_code or env_lang).strip() or env_lang,
            speaking_rate=voice_config.speaking_rate or env_rate,
        )

    def create_tts_job(self, request: TtsRequest):
        source_video = self._load_source_video(request.source_video_id)
        voice_config = self._voice_config_for_request(request, source_video.workspace_id)
        job = JobService(self.db).create_job(
            job_type=JobType.SYNTHESIZE_TTS,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "voice_config": voice_config.__dict__,
                "force_refresh": request.force_refresh,
            },
            idempotency_key=None,
        )
        logger.info("tts_job_created", extra={"job_id": str(job.id), "source_video_id": str(source_video.id)})
        return job

    def run_pipeline(self, request: TtsRequest, *, job_id: UUID | None = None) -> RenderPrepResult:
        source_video = self._load_source_video(request.source_video_id)
        self.tts_provider = self._provider_for_workspace(source_video.workspace_id)
        voice_config = self._voice_config_for_request(request, source_video.workspace_id)
        request = TtsRequest(
            source_video_id=request.source_video_id,
            voice_config=voice_config,
            force_refresh=request.force_refresh,
        )
        context = self._storage_context(source_video)
        input_segments = TranslationInputResolver(self.db).resolve(source_video.id)
        logger.info("tts_input_resolved", extra={"source_video_id": str(source_video.id), "segments": len(input_segments)})

        subtitle_version = self._next_subtitle_version(source_video.id)
        try:
            self._mark_previous_outputs_non_current(source_video.id)
            synthesized: list[SynthesizedSegment] = []
            assets: list[MediaAsset] = []
            warnings: list[str] = []

            for segment in input_segments:
                provider_output = self.tts_provider.synthesize(
                    TtsProviderInput(
                        text=segment.translated_text,
                        language_code=request.voice_config.language_code,
                        voice_config=request.voice_config,
                        target_duration_seconds=segment.duration_budget_ms / 1000,
                    )
                )
                fit_status, fit_ratio = classify_timing_fit(provider_output.duration_seconds, segment.duration_budget_ms / 1000)
                all_warnings = list(dict.fromkeys([*provider_output.warnings, *timing_fit_flags(fit_status)]))
                synthesized_segment = SynthesizedSegment(
                    input_segment=segment,
                    audio_bytes=provider_output.audio_bytes,
                    duration_seconds=provider_output.duration_seconds,
                    mime_type=provider_output.mime_type,
                    file_extension=provider_output.file_extension,
                    provider_metadata=provider_output.provider_metadata,
                    warnings=all_warnings,
                    fit_status=fit_status,
                    fit_ratio=fit_ratio,
                )
                synthesized.append(synthesized_segment)
                warnings.extend(all_warnings)
                assets.append(
                    self._persist_asset(
                        source_video,
                        context,
                        MediaAssetType.TTS_AUDIO_CLIP,
                        provider_output.audio_bytes,
                        filename=f"{subtitle_version}_segment_{segment.segment_index}.{provider_output.file_extension}",
                        mime_type=provider_output.mime_type,
                        manifest_group="tts_segment_clips",
                        job_id=job_id,
                        metadata={
                            "translation_segment_id": str(segment.translation_segment_id),
                            "duration_seconds": provider_output.duration_seconds,
                            "fit_status": fit_status.value,
                            "fit_ratio": fit_ratio,
                            "provider": provider_output.provider_metadata,
                            "warnings": all_warnings,
                        },
                    )
                )

            joined_audio, joined_metadata = self.narration_assembler.assemble(synthesized)
            assets.append(
                self._persist_asset(
                    source_video,
                    context,
                    MediaAssetType.TTS_AUDIO_JOINED,
                    joined_audio,
                    filename=f"{subtitle_version}_joined_narration.wav",
                    mime_type="audio/wav",
                    manifest_group="tts_joined_narration",
                    job_id=job_id,
                    metadata=joined_metadata,
                )
            )

            subtitle_drafts = self.subtitle_builder.build(input_segments, synthesized)
            subtitle_rows = self._persist_subtitles(source_video, subtitle_drafts, subtitle_version, job_id)
            subtitle_json = {"subtitle_version": subtitle_version, "segments": [self._subtitle_payload(row) for row in subtitle_rows]}
            assets.append(
                self._persist_json_asset(
                    source_video,
                    context,
                    MediaAssetType.SUBTITLE_JSON,
                    subtitle_json,
                    filename=f"{subtitle_version}_subtitles.json",
                    manifest_group="subtitle_outputs",
                    job_id=job_id,
                )
            )
            assets.append(
                self._persist_asset(
                    source_video,
                    context,
                    MediaAssetType.SUBTITLE_SRT,
                    build_srt(subtitle_drafts).encode("utf-8"),
                    filename=f"{subtitle_version}_subtitles.srt",
                    mime_type="application/x-subrip",
                    manifest_group="subtitle_outputs",
                    job_id=job_id,
                    metadata={"subtitle_version": subtitle_version},
                )
            )

            current_assets = self._assets_for_video(source_video.id)
            manifest = build_render_prep_manifest(
                source_video_id=str(source_video.id),
                source_video_external_id=source_video.source_video_external_id,
                assets=current_assets + assets,
                synthesized_segments=synthesized,
                subtitle_version=subtitle_version,
                provider_summary={"tts_provider": self.tts_provider.provider_name, "voice_config": request.voice_config.__dict__},
                warnings=list(dict.fromkeys(warnings)),
            )
            manifest_asset = self._persist_json_asset(
                source_video,
                context,
                MediaAssetType.RENDER_PREP_MANIFEST,
                manifest,
                filename=f"{subtitle_version}_render_prep_manifest.json",
                manifest_group="render_prep",
                job_id=job_id,
            )
            assets.append(manifest_asset)
            source_video.status = SourceVideoStatus.READY_FOR_RENDER
            self.db.commit()
        except TtsPipelineError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise TtsPipelineError(TtsPipelineErrorCode.PERSISTENCE_FAILED, f"TTS pipeline failed: {exc}") from exc

        fit_summary = Counter(str(segment.fit_status) for segment in synthesized)
        logger.info(
            "tts_pipeline_completed",
            extra={"source_video_id": str(source_video.id), "clips": len(synthesized), "subtitles": len(subtitle_rows)},
        )
        return RenderPrepResult(
            source_video_id=source_video.id,
            pipeline_version=TTS_PIPELINE_VERSION,
            subtitle_count=len(subtitle_rows),
            tts_clip_count=len(synthesized),
            asset_count=len(assets),
            timing_fit_summary=dict(fit_summary),
            warnings=list(dict.fromkeys(warnings)),
            manifest=manifest,
        )

    def get_subtitle_segments(self, source_video_id: UUID) -> list[SubtitleSegment]:
        return list(
            self.db.scalars(
                select(SubtitleSegment)
                .where(SubtitleSegment.source_video_id == source_video_id, SubtitleSegment.is_current.is_(True))
                .order_by(SubtitleSegment.start_ms.asc(), SubtitleSegment.segment_index.asc())
            )
        )

    def get_render_prep_manifest(self, source_video_id: UUID) -> dict:
        asset = self._current_asset(source_video_id, MediaAssetType.RENDER_PREP_MANIFEST)
        if asset and isinstance(asset.metadata_json, dict) and "manifest" in asset.metadata_json:
            return asset.metadata_json["manifest"]
        return {"manifest_version": "RENDER_PREP_MANIFEST_V1", "source_video": {"id": str(source_video_id)}, "current_outputs": {}}

    def get_tts_summary(self, source_video_id: UUID) -> dict:
        assets = self._assets_for_video(source_video_id)
        tts_assets = [
            asset
            for asset in assets
            if asset.asset_type in {MediaAssetType.TTS_AUDIO_CLIP, MediaAssetType.TTS_AUDIO_JOINED}
            and asset.is_current
        ]
        subtitle_count = len(self.get_subtitle_segments(source_video_id))
        warnings = []
        for asset in tts_assets:
            warnings.extend((asset.metadata_json or {}).get("warnings", []))
        clips = extract_tts_clip_fits(tts_assets)
        return {
            "source_video_id": str(source_video_id),
            "tts_asset_count": len(tts_assets),
            "subtitle_count": subtitle_count,
            "warnings": list(dict.fromkeys(warnings)),
            "clips": clips,
            "timing_fit_summary": build_timing_fit_summary(clips),
            "assets": [
                {
                    "id": str(asset.id),
                    "asset_type": asset.asset_type,
                    "storage_key": asset.storage_key,
                    "metadata_json": asset.metadata_json,
                }
                for asset in tts_assets
            ],
        }

    def _load_source_video(self, source_video_id: UUID) -> SourceVideo:
        source_video = self.db.scalar(
            select(SourceVideo).where(SourceVideo.id == source_video_id).options(selectinload(SourceVideo.source_profile))
        )
        if source_video is None:
            raise TtsPipelineError(TtsPipelineErrorCode.MISSING_TRANSLATION_SEGMENTS, "Source video not found")
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

    def _next_subtitle_version(self, source_video_id: UUID) -> str:
        max_version = self.db.scalar(select(func.max(SubtitleSegment.version)).where(SubtitleSegment.source_video_id == source_video_id))
        return f"{TTS_PIPELINE_VERSION}_RUN_{(max_version or 0) + 1}"

    def _version_number(self, version: str) -> int:
        return int(version.rsplit("_", 1)[-1])

    def _mark_previous_outputs_non_current(self, source_video_id: UUID) -> None:
        self.db.execute(update(SubtitleSegment).where(SubtitleSegment.source_video_id == source_video_id).values(is_current=False))
        self.db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type.in_(
                    [
                        MediaAssetType.TTS_AUDIO_CLIP,
                        MediaAssetType.TTS_AUDIO_JOINED,
                        MediaAssetType.SUBTITLE_JSON,
                        MediaAssetType.SUBTITLE_SRT,
                        MediaAssetType.SUBTITLE_ASS,
                        MediaAssetType.RENDER_PREP_MANIFEST,
                    ]
                ),
            )
            .values(is_current=False)
        )

    def _persist_subtitles(
        self,
        source_video: SourceVideo,
        subtitles: list[SubtitleDraftSegment],
        subtitle_version: str,
        job_id: UUID | None,
    ) -> list[SubtitleSegment]:
        rows: list[SubtitleSegment] = []
        version_number = self._version_number(subtitle_version)
        for segment in subtitles:
            row = SubtitleSegment(
                workspace_id=source_video.workspace_id,
                source_video_id=source_video.id,
                translation_segment_id=segment.translation_segment_id,
                segment_index=segment.segment_index,
                version=version_number,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
                status=TranscriptSegmentStatus.NEEDS_REVIEW if segment.review_flags else TranscriptSegmentStatus.DRAFT,
                style_json={"position": "bottom", "max_chars_per_line": 18},
                layout_mode=segment.layout_mode,
                track_kind=segment.track_kind,
                review_flags_json={"flags": segment.review_flags},
                subtitle_version=subtitle_version,
                created_by_job_id=job_id,
                is_current=True,
                metadata_json=segment.metadata,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def _persist_json_asset(self, source_video: SourceVideo, context: VideoStorageContext, asset_type: MediaAssetType, payload: dict, *, filename: str, manifest_group: str, job_id: UUID | None) -> MediaAsset:
        content = json.dumps(payload, ensure_ascii=True, indent=2, default=str).encode("utf-8")
        metadata = {"manifest": payload} if asset_type == MediaAssetType.RENDER_PREP_MANIFEST else {}
        return self._persist_asset(source_video, context, asset_type, content, filename=filename, mime_type="application/json", manifest_group=manifest_group, job_id=job_id, metadata=metadata)

    def _persist_asset(self, source_video: SourceVideo, context: VideoStorageContext, asset_type: MediaAssetType, content: bytes, *, filename: str, mime_type: str, manifest_group: str, job_id: UUID | None, metadata: dict | None = None) -> MediaAsset:
        if not content:
            raise TtsPipelineError(TtsPipelineErrorCode.CLIP_PERSIST_FAILED, f"Empty asset content for {asset_type}")
        version = self._next_asset_version(source_video.id, asset_type)
        logical_key = asset_logical_key(context, asset_type, filename=f"v{version}_{filename}")
        write_result = self.storage.write_bytes(logical_key, content)
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
        max_version = self.db.scalar(
            select(func.max(MediaAsset.version)).where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == asset_type,
            )
        )
        return (max_version or 0) + 1

    def _current_asset(self, source_video_id: UUID, asset_type: MediaAssetType) -> MediaAsset | None:
        return self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == asset_type,
                MediaAsset.is_current.is_(True),
            )
        )

    def _assets_for_video(self, source_video_id: UUID) -> list[MediaAsset]:
        return list(self.db.scalars(select(MediaAsset).where(MediaAsset.source_video_id == source_video_id)))

    def _subtitle_payload(self, row: SubtitleSegment) -> dict:
        return {
            "id": str(row.id),
            "translation_segment_id": str(row.translation_segment_id) if row.translation_segment_id else None,
            "segment_index": row.segment_index,
            "start_time_seconds": row.start_ms / 1000,
            "end_time_seconds": row.end_ms / 1000,
            "duration_seconds": (row.end_ms - row.start_ms) / 1000,
            "text": row.text,
            "layout_mode": row.layout_mode,
            "track_kind": row.track_kind,
            "review_flags": (row.review_flags_json or {}).get("flags", []),
        }
