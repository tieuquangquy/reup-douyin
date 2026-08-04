from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from src.audio_pipeline.caption_asr_consensus import (
    apply_caption_asr_consensus,
    drop_punctuation_only_units,
    should_auto_approve_source,
)
from src.audio_pipeline.errors import AudioAnalysisError, AudioAnalysisErrorCode
from src.audio_pipeline.provider_factory import build_default_stt_provider, build_default_translation_provider
from src.audio_pipeline.providers import (
    SourceSeparationProvider,
    SttProvider,
    TranslationProvider,
    VadProvider,
    build_default_separation_provider,
    build_default_vad_provider,
)
from src.audio_pipeline.stt_funasr import FunasrSttProvider
from src.audio_pipeline.services.audio_asset_resolver import AudioAssetResolver
from src.audio_pipeline.services.transcript_builder import TranscriptBuilder
from src.audio_pipeline.services.translation_draft_builder import TranslationDraftBuilder
from src.audio_pipeline.stt_funasr import fit_funasr_units_to_duration
from src.audio_pipeline.types import (
    AUDIO_ANALYSIS_VERSION,
    AudioAnalysisRequest,
    AudioAnalysisResult,
    SourceSeparationResult,
    TranscriptDraftSegment,
    TranslationPreset,
)
from src.core.settings import get_settings
from src.enums import JobType, MediaAssetStatus, MediaAssetType, SourceVideoStatus, TranscriptSegmentStatus
from src.models.artifacts import TranscriptSegment, TranslationSegment
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset
from src.services.job_service import JobService
from src.services.workspace_settings_service import WorkspaceSettingsService
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend
from src.storage.manifest import assemble_asset_manifest
from src.storage.path_strategy import VideoStorageContext, asset_logical_key

logger = logging.getLogger(__name__)

AnalysisPhaseHook = Callable[[str, int | None], None]


class AudioAnalysisService:
    def __init__(
        self,
        db: Session,
        *,
        storage: StorageBackend | None = None,
        separation_provider: SourceSeparationProvider | None = None,
        stt_provider: SttProvider | None = None,
        translation_provider: TranslationProvider | None = None,
        vad_provider: VadProvider | None = None,
    ):
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)
        self.separation_provider = separation_provider or build_default_separation_provider()
        self.stt_provider = stt_provider or build_default_stt_provider()
        self._translation_provider_explicit = translation_provider is not None
        self.translation_provider = translation_provider or build_default_translation_provider()
        self.vad_provider = vad_provider or build_default_vad_provider()
        self.transcript_builder = TranscriptBuilder()
        self.translation_builder = TranslationDraftBuilder(self.translation_provider)

    def _translation_builder_for_workspace(self, workspace_id: UUID) -> TranslationDraftBuilder:
        if self._translation_provider_explicit:
            return self.translation_builder
        """Resolve Translation AI (DB override → env) per job so Ops Save applies without restart."""
        workspace_ai = WorkspaceSettingsService(self.db).get_translation_ai(workspace_id)
        provider = build_default_translation_provider(workspace_ai=workspace_ai)
        return TranslationDraftBuilder(provider)

    @staticmethod
    def _translation_concurrency(builder: TranslationDraftBuilder) -> int:
        configured = max(
            1,
            int(getattr(get_settings(), "audio_translation_max_concurrency", 1) or 1),
        )
        primary = getattr(builder.provider, "primary", None)
        provider_name = str(getattr(primary, "provider_name", "") or "").strip().lower()
        if provider_name == "gemini":
            return 1
        return configured

    def create_analysis_job(self, request: AudioAnalysisRequest, *, idempotency_key: str | None = None):
        source_video = self._load_source_video(request.source_video_id)
        job = JobService(self.db).create_job(
            job_type=JobType.ANALYZE_AUDIO,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "translation_preset": request.translation_preset,
                "force_refresh": request.force_refresh,
                "skip_translation": request.skip_translation,
            },
            idempotency_key=idempotency_key,
        )
        logger.info("audio_analysis_job_created", extra={"job_id": str(job.id), "source_video_id": str(source_video.id)})
        return job

    def run_analysis(
        self,
        request: AudioAnalysisRequest,
        *,
        job_id: UUID | None = None,
        on_phase: AnalysisPhaseHook | None = None,
    ) -> AudioAnalysisResult:
        def phase(name: str, progress_percent: int | None = None) -> None:
            logger.info(
                "audio_analysis_phase",
                extra={
                    "source_video_id": str(request.source_video_id),
                    "job_id": str(job_id) if job_id else None,
                    "phase": name,
                    "progress_percent": progress_percent,
                },
            )
            if on_phase is None:
                return
            try:
                on_phase(name, progress_percent)
            except Exception:
                logger.exception(
                    "audio_analysis_phase_hook_failed",
                    extra={"phase": name, "job_id": str(job_id) if job_id else None},
                )

        logger.info("audio_analysis_started", extra={"source_video_id": str(request.source_video_id)})
        phase("started", 5)
        source_video, resolved_input = AudioAssetResolver(self.db, self.storage).resolve(request.source_video_id)
        context = self._storage_context(source_video)
        phase("resolved_input", 10)

        if isinstance(self.stt_provider, FunasrSttProvider) and self.stt_provider.on_lifecycle is None:
            lifecycle_progress = {
                "funasr_started": 35,
                "funasr_waiting": 45,
                "funasr_timed_out": 50,
                "funasr_finished": 55,
            }

            def _funasr_lifecycle(event: str) -> None:
                phase(event, lifecycle_progress.get(event))

            self.stt_provider.on_lifecycle = _funasr_lifecycle

        vad = self.vad_provider.detect(
            resolved_input.storage_key,
            duration_seconds=resolved_input.source_video_duration_seconds,
            source_caption=resolved_input.source_caption,
        )
        logger.info(
            "audio_vad_done",
            extra={
                "source_video_id": str(source_video.id),
                "has_speech": vad.has_speech,
                "provider": self.vad_provider.provider_name,
            },
        )
        phase("vad_done", 15)

        if vad.has_speech:
            separation = self.separation_provider.separate(resolved_input.storage_key)
            logger.info(
                "audio_source_separation_done",
                extra={
                    "source_video_id": str(source_video.id),
                    "fallback_used": separation.fallback_used,
                    "provider": self.separation_provider.provider_name,
                },
            )
            phase("separation_done", 25)
            phase("stt_started", 30)
            units = self.stt_provider.transcribe(
                separation.transcription_storage_key,
                source_caption=resolved_input.source_caption,
                duration_seconds=resolved_input.source_video_duration_seconds,
            )
            # Belt-and-suspenders: providers may ignore duration (stale worker / untimed ASR).
            units = fit_funasr_units_to_duration(
                units,
                duration_seconds=resolved_input.source_video_duration_seconds,
            )
            units = apply_caption_asr_consensus(
                units,
                caption=resolved_input.source_caption,
                duration_seconds=resolved_input.source_video_duration_seconds,
            )
            units = drop_punctuation_only_units(units)
            phase("caption_asr_consensus", 58)
        else:
            separation = SourceSeparationResult(
                vocal_asset_id=None,
                background_asset_id=None,
                transcription_storage_key=resolved_input.storage_key,
                fallback_used=True,
                difficulty_flags=["skip_dubbing", "separation_skipped_no_speech"],
                metadata={"provider": "skipped", "reason": "no_speech"},
            )
            units = []
            phase("stt_skipped_no_speech", 55)

        empty_asr_after_speech_gate = bool(vad.has_speech and not units)
        # Silero measured the waveform, so "ASR heard nothing" contradicts hard evidence
        # instead of merely confirming a guess. That case needs an operator, not a silent skip.
        vad_measured_speech = bool(vad.has_speech and "silero_vad_executed" in (vad.difficulty_flags or []))
        dialogue_uncertain = bool(empty_asr_after_speech_gate and vad_measured_speech)
        if empty_asr_after_speech_gate:
            # Never fill DialogueBeats from Douyin caption/title/hashtags.
            extra_flags = (
                {"asr_empty_despite_vad_speech", "needs_operator_review", "no_asr_dialogue"}
                if dialogue_uncertain
                else {"skip_dubbing", "no_asr_dialogue", "caption_not_dialogue", "dialogue_unverified"}
            )
            separation = SourceSeparationResult(
                vocal_asset_id=separation.vocal_asset_id,
                background_asset_id=separation.background_asset_id,
                transcription_storage_key=separation.transcription_storage_key,
                fallback_used=True,
                difficulty_flags=list({*separation.difficulty_flags, *extra_flags}),
                metadata={
                    **separation.metadata,
                    "reason": "asr_empty_despite_vad_speech" if dialogue_uncertain else "empty_asr_no_caption_dialogue",
                    "vad_speech_ratio": vad.speech_ratio,
                    "source_caption_present": bool((resolved_input.source_caption or "").strip()),
                },
            )

        logger.info(
            "audio_transcription_done",
            extra={"source_video_id": str(source_video.id), "unit_count": len(units), "provider": self.stt_provider.provider_name},
        )
        phase("stt_done", 60)

        transcript_drafts = self.transcript_builder.build(units) if units else []
        phase("transcript_built", 70)
        skip_translation = bool(request.skip_translation)
        if skip_translation or not transcript_drafts:
            translations = []
            phase("translation_skipped_asr_only" if skip_translation else "translation_skipped_no_dialogue", 85)
        else:
            settings_svc = WorkspaceSettingsService(self.db)
            db_prompt = settings_svc.get_translation_user_prompt(source_video.workspace_id)
            builder = self._translation_builder_for_workspace(source_video.workspace_id)
            max_concurrency = self._translation_concurrency(builder)
            try:
                translations = (
                    builder.build(
                        transcript_drafts,
                        preset=request.translation_preset,
                        user_prompt=db_prompt,
                        max_concurrency=max_concurrency,
                    )
                    if transcript_drafts
                    else []
                )
            except RuntimeError as exc:
                raise AudioAnalysisError(
                    AudioAnalysisErrorCode.TRANSLATION_FAILED,
                    str(exc),
                ) from exc
            phase("translation_built", 85)
        flags_summary = Counter(
            flag
            for segment in transcript_drafts
            for flag in [*segment.difficulty_flags, *separation.difficulty_flags]
        )
        flags_summary.update(flag for translation in translations for flag in translation.quality_flags)
        flags_summary.update(vad.difficulty_flags)
        if dialogue_uncertain:
            flags_summary.update(["asr_empty_despite_vad_speech", "needs_operator_review"])
        elif empty_asr_after_speech_gate:
            flags_summary.update(["skip_dubbing", "caption_not_dialogue", "dialogue_unverified"])
        elif not vad.has_speech:
            flags_summary.update(["skip_dubbing", "caption_not_dialogue"])

        version = self._next_analysis_version(source_video.id)
        try:
            self._mark_previous_non_current(source_video.id)
            transcript_rows = self._persist_transcripts(source_video, transcript_drafts, version, job_id)
            translation_rows = self._persist_translations(source_video, transcript_rows, translations, job_id)
            meta = dict(source_video.metadata_json or {})
            meta["has_speech"] = bool(vad.has_speech and (transcript_rows or dialogue_uncertain))
            dialogue_phase = "translated_draft"
            if dialogue_uncertain:
                dialogue_phase = "dialogue_uncertain"
            elif not transcript_rows:
                dialogue_phase = "no_dialogue"
            elif skip_translation:
                dialogue_phase = self._machine_approve_source_beats(
                    transcript_rows,
                    transcript_drafts,
                    flags_summary=flags_summary,
                )
                flags_summary.update(["source_machine_auto_approved"])
            meta["dialogue_phase"] = dialogue_phase
            meta["transcript_count"] = len(transcript_rows)
            meta["vad"] = {
                "provider": self.vad_provider.provider_name,
                "has_speech": vad.has_speech,
                "speech_ratio": vad.speech_ratio,
                "difficulty_flags": vad.difficulty_flags,
                "metadata": vad.metadata,
            }
            meta["separation"] = {
                "provider": (
                    self.separation_provider.provider_name if vad.has_speech else "skipped"
                ),
                "fallback_used": separation.fallback_used,
                "difficulty_flags": list(separation.difficulty_flags),
                "metadata": dict(separation.metadata or {}),
            }
            source_video.metadata_json = meta
            assets = [
                self._persist_json_asset(
                    source_video,
                    context,
                    MediaAssetType.AUDIO_ANALYSIS_METADATA,
                    {
                        "analysis_version": version,
                        "audio_input": resolved_input.__dict__,
                        "dialogue_phase": meta["dialogue_phase"],
                        "skip_translation": skip_translation,
                        "vad": {
                            "provider": self.vad_provider.provider_name,
                            "has_speech": vad.has_speech,
                            "speech_ratio": vad.speech_ratio,
                            "difficulty_flags": vad.difficulty_flags,
                            "metadata": vad.metadata,
                        },
                        "separation": {
                            "provider": self.separation_provider.provider_name if vad.has_speech else "skipped",
                            "fallback_used": separation.fallback_used,
                            "difficulty_flags": separation.difficulty_flags,
                            "metadata": separation.metadata,
                        },
                        "stt_provider": self.stt_provider.provider_name if vad.has_speech else "skipped",
                        "translation_provider": (
                            "skipped_asr_only"
                            if skip_translation
                            else (self.translation_provider.provider_name if vad.has_speech else "skipped")
                        ),
                        "flags_summary": dict(flags_summary),
                    },
                    filename=f"{version}_audio_analysis_metadata.json",
                    job_id=job_id,
                ),
                self._persist_json_asset(
                    source_video,
                    context,
                    MediaAssetType.TRANSCRIPT_JSON,
                    {"analysis_version": version, "segments": [self._transcript_payload(row) for row in transcript_rows]},
                    filename=f"{version}_transcript.json",
                    job_id=job_id,
                ),
            ]
            if not skip_translation:
                assets.append(
                    self._persist_json_asset(
                        source_video,
                        context,
                        MediaAssetType.TRANSLATION_DRAFT_JSON,
                        {
                            "analysis_version": version,
                            "translation_preset": request.translation_preset,
                            "segments": [self._translation_payload(row) for row in translation_rows],
                        },
                        filename=f"{version}_translation_draft.json",
                        job_id=job_id,
                    )
                )
            source_video.status = SourceVideoStatus.AI_ANALYZED
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise AudioAnalysisError(AudioAnalysisErrorCode.PERSISTENCE_FAILED, f"Could not persist analysis: {exc}") from exc

        manifest = self.get_summary(source_video.id)["manifest"]
        phase("completed", 95)
        logger.info(
            "audio_analysis_completed",
            extra={
                "source_video_id": str(source_video.id),
                "transcript_count": len(transcript_rows),
                "translation_count": len(translation_rows),
                "asset_count": len(assets),
                "skip_translation": skip_translation,
            },
        )
        return AudioAnalysisResult(
            source_video_id=source_video.id,
            analysis_version=version,
            transcript_count=len(transcript_rows),
            translation_count=len(translation_rows),
            asset_count=len(assets),
            flags_summary=dict(flags_summary),
            manifest=manifest,
        )

    def create_translation_job(
        self,
        source_video_id: UUID,
        *,
        translation_preset: TranslationPreset = TranslationPreset.LITERAL_SAFE,
        force_refresh: bool = True,
        require_source_approved: bool = True,
        idempotency_key: str | None = None,
    ):
        source_video = self._load_source_video(source_video_id)
        beats = self.get_transcript_segments(source_video_id)
        if not beats:
            raise AudioAnalysisError(AudioAnalysisErrorCode.MISSING_SOURCE_ASSET, "No current transcript beats to translate")
        if require_source_approved and any(beat.status != TranscriptSegmentStatus.APPROVED for beat in beats):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Approve all source transcript beats before literal translation",
            )
        job = JobService(self.db).create_job(
            job_type=JobType.BUILD_TRANSLATION_DRAFT,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "translation_preset": translation_preset,
                "force_refresh": force_refresh,
                "require_source_approved": require_source_approved,
            },
            idempotency_key=idempotency_key,
        )
        logger.info(
            "translation_draft_job_created",
            extra={"job_id": str(job.id), "source_video_id": str(source_video.id), "preset": str(translation_preset)},
        )
        return job

    def run_translation_only(
        self,
        source_video_id: UUID,
        *,
        translation_preset: TranslationPreset = TranslationPreset.LITERAL_SAFE,
        require_source_approved: bool = True,
        job_id: UUID | None = None,
        on_progress: AnalysisPhaseHook | None = None,
    ) -> AudioAnalysisResult:
        """Phase B: literal translate current transcript beats. Does not run FunASR."""
        source_video = self._load_source_video(source_video_id)
        context = self._storage_context(source_video)
        beats = self.get_transcript_segments(source_video_id)
        if not beats:
            raise AudioAnalysisError(AudioAnalysisErrorCode.MISSING_SOURCE_ASSET, "No current transcript beats to translate")
        if require_source_approved and any(beat.status != TranscriptSegmentStatus.APPROVED for beat in beats):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Approve all source transcript beats before literal translation",
            )

        draft_segments = [
            TranscriptDraftSegment(
                segment_index=int(beat.segment_index),
                start_seconds=float(beat.start_ms) / 1000.0,
                end_seconds=float(beat.end_ms) / 1000.0,
                source_text=str(beat.text or ""),
                normalized_source_text=str(beat.normalized_text or beat.text or ""),
                confidence=beat.confidence,
                speaker_label=beat.speaker_label,
                difficulty_flags=list((beat.difficulty_flags_json or {}).get("flags") or []),
                metadata={"analysis_version": beat.analysis_version, "transcript_segment_id": str(beat.id)},
            )
            for beat in beats
        ]
        settings_svc = WorkspaceSettingsService(self.db)
        db_prompt = settings_svc.get_translation_user_prompt(source_video.workspace_id)
        builder = self._translation_builder_for_workspace(source_video.workspace_id)
        max_concurrency = self._translation_concurrency(builder)

        def _progress(completed: int, total: int, **_: object) -> None:
            if on_progress is None or total <= 0:
                return
            # Reserve 10–90% for translate loop so prepare/finalize stay distinct in UI.
            pct = 10 + int((completed / total) * 80)
            on_progress(f"translate_beat_{completed}_of_{total}", pct)

        if on_progress is not None:
            on_progress("translate_start", 5)
        try:
            translations = builder.build(
                draft_segments,
                preset=translation_preset,
                user_prompt=db_prompt,
                max_concurrency=max_concurrency,
                on_progress=_progress,
            )
        except RuntimeError as exc:
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSLATION_FAILED,
                str(exc),
            ) from exc
        if on_progress is not None:
            on_progress("translate_persist", 92)
        gated = [row for row in translations if "translation_gate_failed" in (row.quality_flags or [])]
        non_empty = [row for row in translations if (row.translated_text or "").strip()]
        # Minority gate failures must not discard clean beats — persist partial draft.
        if not translations or not non_empty:
            detail = (
                f" ({len(gated)} segment(s) rejected for leftover Chinese after repair)"
                if gated
                else ""
            )
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSLATION_FAILED,
                "Literal translation produced 0 non-empty segments. Restart worker and check Gemini/Ollama "
                f"translation provider.{detail}",
            )
        analysis_version = beats[0].analysis_version or self._next_analysis_version(source_video_id)
        try:
            self._mark_previous_translations_non_current(source_video_id)
            translation_rows = self._persist_translations(source_video, beats, translations, job_id)
            if not translation_rows:
                raise AudioAnalysisError(
                    AudioAnalysisErrorCode.TRANSLATION_FAILED,
                    "Literal translation persisted 0 segments. Restart worker / check BUILD_TRANSLATION_DRAFT handler.",
                )
            meta = dict(source_video.metadata_json or {})
            meta["dialogue_phase"] = (
                "translated_literal_partial" if gated else "translated_literal"
            )
            meta["translation_preset"] = str(translation_preset)
            meta["translation_row_count"] = len(translation_rows)
            meta["translation_filled_count"] = len(non_empty)
            meta["translation_count"] = len(non_empty)
            meta["translation_gate_failed_count"] = len(gated)
            source_video.metadata_json = meta
            self._persist_json_asset(
                source_video,
                context,
                MediaAssetType.TRANSLATION_DRAFT_JSON,
                {
                    "analysis_version": analysis_version,
                    "translation_preset": translation_preset,
                    "literal_only": translation_preset == TranslationPreset.LITERAL_SAFE,
                    "segments": [self._translation_payload(row) for row in translation_rows],
                },
                filename=f"{analysis_version}_translation_draft.json",
                job_id=job_id,
            )
            self.db.commit()
        except AudioAnalysisError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise AudioAnalysisError(AudioAnalysisErrorCode.PERSISTENCE_FAILED, f"Could not persist translation: {exc}") from exc

        flags_summary = Counter(flag for translation in translations for flag in translation.quality_flags)
        return AudioAnalysisResult(
            source_video_id=source_video.id,
            analysis_version=analysis_version,
            transcript_count=len(beats),
            # Job success authority: beats with non-empty Vietnamese only.
            translation_count=len(non_empty),
            asset_count=1,
            flags_summary=dict(flags_summary),
            manifest=self.get_summary(source_video.id)["manifest"],
        )

    def _machine_approve_source_beats(
        self,
        transcript_rows: list,
        transcript_drafts: list[TranscriptDraftSegment],
        *,
        flags_summary: Counter | None = None,
    ) -> str:
        """
        Machine-first: lock Chinese beats after Phase A so non-Chinese operators can
        go straight to literal translate + Vietnamese review. Risk stays in flags.
        """
        _ = flags_summary
        if not transcript_rows:
            return "source_pending_approve"
        flat_flags: list[str] = []
        for draft in transcript_drafts:
            flat_flags.extend(draft.difficulty_flags)
        confidences = [d.confidence for d in transcript_drafts if d.confidence is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None
        clean = should_auto_approve_source(flat_flags, avg_confidence=avg_confidence)
        for row in transcript_rows:
            row.status = TranscriptSegmentStatus.APPROVED
        phase = "source_auto_approved" if clean else "source_auto_approved_risk"
        logger.info(
            "source_transcript_machine_approved",
            extra={
                "beat_count": len(transcript_rows),
                "dialogue_phase": phase,
                "avg_confidence": avg_confidence,
                "flag_sample": sorted(set(flat_flags))[:12],
            },
        )
        return phase

    def approve_source_transcript(self, source_video_id: UUID) -> dict:
        """Optional manual lock (advanced). Phase A already machine-approves by default."""
        beats = self.get_transcript_segments(source_video_id)
        if not beats:
            raise AudioAnalysisError(AudioAnalysisErrorCode.MISSING_SOURCE_ASSET, "No current transcript beats to approve")
        for beat in beats:
            beat.status = TranscriptSegmentStatus.APPROVED
        source_video = self._load_source_video(source_video_id)
        meta = dict(source_video.metadata_json or {})
        meta["dialogue_phase"] = "source_approved"
        source_video.metadata_json = meta
        self.db.commit()
        logger.info(
            "source_transcript_approved",
            extra={"source_video_id": str(source_video_id), "beat_count": len(beats)},
        )
        return {"source_video_id": str(source_video_id), "approved_segments": len(beats), "dialogue_phase": "source_approved"}

    def get_transcript_segments(self, source_video_id: UUID) -> list[TranscriptSegment]:
        return list(
            self.db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.source_video_id == source_video_id, TranscriptSegment.is_current.is_(True))
                .order_by(TranscriptSegment.start_ms.asc(), TranscriptSegment.segment_index.asc())
            )
        )

    def get_translation_segments(self, source_video_id: UUID) -> list[TranslationSegment]:
        return list(
            self.db.scalars(
                select(TranslationSegment)
                .where(TranslationSegment.source_video_id == source_video_id, TranslationSegment.is_current.is_(True))
                .order_by(TranslationSegment.segment_index.asc())
            )
        )

    def get_summary(self, source_video_id: UUID) -> dict:
        source_video = self._load_source_video(source_video_id)
        assets = list(
            self.db.scalars(
                select(MediaAsset)
                .where(MediaAsset.source_video_id == source_video_id)
                .order_by(MediaAsset.asset_type, MediaAsset.version.desc())
            )
        )
        transcript_segments = self.get_transcript_segments(source_video_id)
        translation_segments = self.get_translation_segments(source_video_id)
        manifest = assemble_asset_manifest(
            source_video=source_video,
            source_profile=source_video.source_profile,
            assets=assets,
            storage_root=str(getattr(self.storage, "root", None)),
        )
        meta = dict(source_video.metadata_json or {})
        return {
            "source_video_id": str(source_video_id),
            "analysis_version": transcript_segments[0].analysis_version if transcript_segments else None,
            "transcript_count": len(transcript_segments),
            "translation_count": len(translation_segments),
            "asset_count": len([asset for asset in assets if asset.is_current]),
            "manifest": manifest,
            "has_speech": meta.get("has_speech"),
            "dialogue_phase": meta.get("dialogue_phase"),
        }

    def _load_source_video(self, source_video_id: UUID) -> SourceVideo:
        source_video = self.db.scalar(
            select(SourceVideo).where(SourceVideo.id == source_video_id).options(selectinload(SourceVideo.source_profile))
        )
        if source_video is None:
            raise AudioAnalysisError(AudioAnalysisErrorCode.MISSING_SOURCE_ASSET, "Source video not found")
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

    def _next_analysis_version(self, source_video_id: UUID) -> str:
        max_version = self.db.scalar(
            select(func.max(TranscriptSegment.version)).where(TranscriptSegment.source_video_id == source_video_id)
        )
        return f"{AUDIO_ANALYSIS_VERSION}_RUN_{(max_version or 0) + 1}"

    def _mark_previous_non_current(self, source_video_id: UUID) -> None:
        self.db.execute(update(TranscriptSegment).where(TranscriptSegment.source_video_id == source_video_id).values(is_current=False))
        self.db.execute(update(TranslationSegment).where(TranslationSegment.source_video_id == source_video_id).values(is_current=False))

    def _mark_previous_translations_non_current(self, source_video_id: UUID) -> None:
        self.db.execute(update(TranslationSegment).where(TranslationSegment.source_video_id == source_video_id).values(is_current=False))

    def _persist_transcripts(
        self,
        source_video: SourceVideo,
        segments,
        analysis_version: str,
        job_id: UUID | None,
    ) -> list[TranscriptSegment]:
        run_number = int(analysis_version.rsplit("_", 1)[-1])
        rows: list[TranscriptSegment] = []
        for segment in segments:
            row = TranscriptSegment(
                workspace_id=source_video.workspace_id,
                source_video_id=source_video.id,
                segment_index=segment.segment_index,
                version=run_number,
                start_ms=int(segment.start_seconds * 1000),
                end_ms=int(segment.end_seconds * 1000),
                text=segment.source_text,
                normalized_text=segment.normalized_source_text,
                language_code="zh",
                status=TranscriptSegmentStatus.NEEDS_REVIEW if segment.difficulty_flags else TranscriptSegmentStatus.DRAFT,
                confidence=segment.confidence,
                speaker_label=segment.speaker_label,
                difficulty_flags_json={"flags": segment.difficulty_flags},
                analysis_version=analysis_version,
                created_by_job_id=job_id,
                is_current=True,
                metadata_json=segment.metadata,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def _persist_translations(
        self,
        source_video: SourceVideo,
        transcripts: list[TranscriptSegment],
        translations,
        job_id: UUID | None,
    ) -> list[TranslationSegment]:
        """Persist immutable VI draft versions; only a retry may update its own row."""
        rows: list[TranslationSegment] = []
        transcript_by_index = {row.segment_index: row for row in transcripts}
        for translation in translations:
            transcript = transcript_by_index[translation.segment_index]
            status = (
                TranscriptSegmentStatus.NEEDS_REVIEW
                if translation.quality_flags
                else TranscriptSegmentStatus.DRAFT
            )
            duration_budget_ms = int(translation.duration_budget_seconds * 1000)
            estimated_tts_duration_ms = (
                int(translation.estimated_tts_duration_seconds * 1000)
                if translation.estimated_tts_duration_seconds is not None
                else None
            )
            retry_row = (
                self.db.scalar(
                    select(TranslationSegment).where(
                        TranslationSegment.transcript_segment_id == transcript.id,
                        TranslationSegment.language_code == "vi",
                        TranslationSegment.created_by_job_id == job_id,
                    )
                )
                if job_id is not None
                else None
            )
            if retry_row is not None:
                retry_row.text = translation.translated_text
                retry_row.status = status
                retry_row.segment_index = translation.segment_index
                retry_row.translation_preset = translation.translation_preset
                retry_row.duration_budget_ms = duration_budget_ms
                retry_row.estimated_tts_duration_ms = estimated_tts_duration_ms
                retry_row.quality_flags_json = {"flags": translation.quality_flags}
                retry_row.created_by_job_id = job_id
                retry_row.is_current = True
                retry_row.metadata_json = translation.metadata
                rows.append(retry_row)
                continue

            max_version = self.db.scalar(
                select(func.max(TranslationSegment.version)).where(
                    TranslationSegment.transcript_segment_id == transcript.id,
                    TranslationSegment.language_code == "vi",
                )
            )
            next_version = max(
                int(transcript.version or 1),
                int(max_version or 0) + 1,
            )

            row = TranslationSegment(
                workspace_id=source_video.workspace_id,
                source_video_id=source_video.id,
                transcript_segment_id=transcript.id,
                language_code="vi",
                version=next_version,
                text=translation.translated_text,
                status=status,
                segment_index=translation.segment_index,
                translation_preset=translation.translation_preset,
                duration_budget_ms=duration_budget_ms,
                estimated_tts_duration_ms=estimated_tts_duration_ms,
                quality_flags_json={"flags": translation.quality_flags},
                created_by_job_id=job_id,
                is_current=True,
                metadata_json=translation.metadata,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def _persist_json_asset(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        asset_type: MediaAssetType,
        payload: dict,
        *,
        filename: str,
        job_id: UUID | None,
    ) -> MediaAsset:
        existing = self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.source_video_id == source_video.id,
                MediaAsset.asset_type == asset_type,
                MediaAsset.is_current.is_(True),
            )
        )
        version = (existing.version + 1) if existing else 1
        if existing:
            existing.is_current = False

        content = json.dumps(payload, ensure_ascii=True, indent=2, default=str).encode("utf-8")
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
            manifest_group="audio_analysis",
            is_current=True,
            created_by_job_id=job_id,
            mime_type="application/json",
            size_bytes=write_result.size_bytes,
            checksum_sha256=write_result.checksum_sha256,
            metadata_json={"absolute_path": write_result.absolute_path},
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def _transcript_payload(self, row: TranscriptSegment) -> dict:
        return {
            "id": str(row.id),
            "segment_index": row.segment_index,
            "start_time_seconds": row.start_ms / 1000,
            "end_time_seconds": row.end_ms / 1000,
            "source_text": row.text,
            "normalized_source_text": row.normalized_text,
            "confidence": row.confidence,
            "difficulty_flags": (row.difficulty_flags_json or {}).get("flags", []),
        }

    def _translation_payload(self, row: TranslationSegment) -> dict:
        raw_status = getattr(row, "status", TranscriptSegmentStatus.NEEDS_REVIEW)
        metadata = getattr(row, "metadata_json", None)
        return {
            "id": str(row.id),
            "transcript_segment_id": str(row.transcript_segment_id),
            "segment_index": row.segment_index,
            "translated_text": row.text,
            "translation_preset": row.translation_preset,
            "duration_budget_seconds": (row.duration_budget_ms or 0) / 1000,
            "estimated_tts_duration_seconds": (row.estimated_tts_duration_ms / 1000) if row.estimated_tts_duration_ms else None,
            "quality_flags": (row.quality_flags_json or {}).get("flags", []),
            "status": getattr(raw_status, "value", str(raw_status)),
            "metadata": dict(metadata or {}),
        }
