from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.audio_pipeline.caption_asr_consensus import (
    apply_caption_asr_consensus,
    drop_punctuation_only_units,
    should_auto_approve_source,
)
from src.audio_pipeline.audio_mix_quality import analyze_pcm_wav_mix
from src.audio_pipeline.analysis_audio import materialize_analysis_audio
from src.audio_pipeline.asr_evidence import (
    ASR_EVIDENCE_RECIPE_VERSION,
    ASR_EVIDENCE_SCHEMA_VERSION,
    ASR_RECOVERY_SCORE_THRESHOLD,
    compare_asr_stability,
    evaluate_asr_evidence,
    evidence_prefers_candidate,
)
from src.audio_pipeline.canonical_audio import ensure_canonical_audio
from src.audio_pipeline.dialogue_validation import (
    DIALOGUE_VALIDATION_RECIPE_VERSION,
    high_recall_candidate_authority,
    merge_selective_verification,
    validate_dialogue_units,
    verification_authority,
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
from src.audio_pipeline.target_speech_audio import (
    filter_units_to_target_intervals,
    materialize_compact_target_audio,
    materialize_preserved_background,
    remap_compact_transcription_units,
)
from src.audio_pipeline.target_speech_authority import (
    TARGET_SPEECH_RECIPE_VERSION,
    TargetSpeechAuthority,
    TargetSpeechInterval,
    TargetSpeechStatus,
    analyze_target_speech,
    resolve_after_separation,
    unavailable_target_speech_authority,
)
from src.audio_pipeline.yamnet_audio_events import (
    YAMNET_MODEL_SHA256,
    YAMNET_MODEL_VERSION,
)
from src.audio_pipeline.temporal_validation import validate_transcription_timeline
from src.audio_pipeline.translation_temporal_premerge import (
    TRANSLATION_PREMERGE_RECIPE_VERSION,
    merge_translation_premerge_text,
    plan_translation_premerge,
)
from src.audio_pipeline.services.audio_asset_resolver import AudioAssetResolver
from src.audio_pipeline.services.transcript_builder import TranscriptBuilder
from src.audio_pipeline.services.translation_draft_builder import TranslationDraftBuilder
from src.audio_pipeline.semantic_dialogue_segmentation import (
    DEFAULT_SEMANTIC_SEGMENTATION_POLICY,
    SEMANTIC_DIALOGUE_RECIPE_VERSION,
    segment_semantic_dialogue,
)
from src.audio_pipeline.speech_budget import (
    DEFAULT_VI_UNITS_PER_SECOND,
    calibrate_units_per_second,
    speech_rate_samples_from_metadata,
)
from src.audio_pipeline.stt_funasr import fit_funasr_units_to_duration
from src.audio_pipeline.types import (
    AUTHORITY_MANIFEST_SCHEMA_VERSION,
    AUDIO_ANALYSIS_RECIPE_VERSION,
    AUDIO_ANALYSIS_VERSION,
    AudioAnalysisRequest,
    AudioAnalysisResult,
    AudioAnalysisAuthorityManifest,
    ResolvedAudioInput,
    SourceSeparationResult,
    TranscriptDraftSegment,
    TranslationPreset,
)
from src.audio_pipeline.translation_v3 import (
    DEFAULT_TRANSLATION_V3_POLICY,
    TRANSLATION_V3_RECIPE_VERSION,
    TranslationV3Policy,
    build_translation_quality_contract,
    draft_to_checkpoint,
    translation_provider_identity,
    translation_run_fingerprint,
)
from src.audio_pipeline.translation_authority import (
    build_translation_authority,
    transcript_authority_payload,
    transcript_authority_sha256,
    validate_translation_authority,
)
from src.core.settings import get_settings
from src.enums import JobStatus, JobType, MediaAssetStatus, MediaAssetType, SourceVideoStatus, TranscriptSegmentStatus
from src.models.artifacts import SubtitleSegment, TranscriptSegment, TranslationSegment
from src.models.ingestion import SourceVideo
from src.models.jobs import Job
from src.models.media import MediaAsset
from src.services.job_service import JobService
from src.services.workspace_settings_service import WorkspaceSettingsService
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend, to_windows_long_path
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
        target_speech_analyzer: Callable[..., TargetSpeechAuthority] | None = None,
    ):
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)
        self.separation_provider = separation_provider or build_default_separation_provider()
        self.stt_provider = stt_provider or build_default_stt_provider()
        self._translation_provider_explicit = translation_provider is not None
        self.translation_provider = translation_provider or build_default_translation_provider()
        self.vad_provider = vad_provider or build_default_vad_provider()
        self.target_speech_analyzer = target_speech_analyzer or analyze_target_speech
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

    @staticmethod
    def _translation_drafts(beats) -> list[TranscriptDraftSegment]:
        drafts: list[TranscriptDraftSegment] = []
        for group in plan_translation_premerge(beats):
            members = list(group.members)
            first = members[0]
            flags = list(
                dict.fromkeys(
                    flag
                    for member in members
                    for flag in list((getattr(member, "difficulty_flags_json", None) or {}).get("flags") or [])
                )
            )
            confidences = [
                float(member.confidence)
                for member in members
                if getattr(member, "confidence", None) is not None
            ]
            speakers = [
                str(member.speaker_label).strip()
                for member in members
                if str(getattr(member, "speaker_label", None) or "").strip()
            ]
            drafts.append(
                TranscriptDraftSegment(
                    segment_index=int(first.segment_index),
                    start_seconds=float(first.start_ms) / 1000.0,
                    end_seconds=float(members[-1].end_ms) / 1000.0,
                    source_text=merge_translation_premerge_text(
                        [getattr(member, "text", "") for member in members]
                    ),
                    normalized_source_text=merge_translation_premerge_text(
                        [
                            getattr(member, "normalized_text", None)
                            or getattr(member, "text", "")
                            for member in members
                        ]
                    ),
                    confidence=min(confidences) if confidences else None,
                    speaker_label=speakers[0] if speakers else None,
                    difficulty_flags=flags,
                    metadata={
                        "analysis_version": getattr(first, "analysis_version", None),
                        "transcript_segment_id": str(getattr(first, "id", "")),
                        "translation_premerge_planned": len(members) > 1,
                        "translation_premerge_reasons": list(group.reasons),
                        "translation_premerge_member_indices": [
                            int(member.segment_index) for member in members
                        ],
                    },
                )
            )
        return drafts

    @staticmethod
    def _translation_glossary(source_video: SourceVideo) -> dict[str, str]:
        raw = (source_video.metadata_json or {}).get("translation_glossary") or {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(key).strip(): str(value).strip()
            for key, value in raw.items()
            if str(key).strip() and str(value).strip()
        }

    def _translation_policy(self, workspace_id: UUID) -> tuple[TranslationV3Policy, dict]:
        """Calibrate Translation V3 against measured clips for the active TTS voice."""

        settings = get_settings()
        try:
            tts_config = WorkspaceSettingsService(self.db).get_tts_ai(workspace_id)
        except Exception:
            tts_config = None
        provider_name = str(
            getattr(tts_config, "provider", None)
            or getattr(settings, "audio_tts_provider", "omnivoice")
            or "omnivoice"
        ).strip()
        voice_id = str(
            getattr(tts_config, "voice_id", None)
            or getattr(settings, "audio_tts_voice_id", "instruct:vi_female_north")
            or "instruct:vi_female_north"
        ).strip()
        try:
            speaking_rate = float(
                getattr(tts_config, "speaking_rate", None)
                or getattr(settings, "audio_tts_speaking_rate", 1.0)
                or 1.0
            )
        except (TypeError, ValueError):
            speaking_rate = 1.0
        speaking_rate = max(0.5, min(2.0, speaking_rate))
        assets = list(
            self.db.scalars(
                select(MediaAsset)
                .where(
                    MediaAsset.workspace_id == workspace_id,
                    MediaAsset.asset_type == MediaAssetType.TTS_AUDIO_CLIP,
                    MediaAsset.status == MediaAssetStatus.AVAILABLE,
                )
                .order_by(MediaAsset.created_at.desc())
                .limit(200)
            )
        )
        samples = speech_rate_samples_from_metadata(
            [
                metadata
                for asset in assets
                if isinstance((metadata := getattr(asset, "metadata_json", None) or {}), dict)
            ],
            provider_name=provider_name,
            voice_id=voice_id,
            speaking_rate=speaking_rate,
        )
        calibration = calibrate_units_per_second(
            samples,
            default_units_per_second=DEFAULT_VI_UNITS_PER_SECOND * speaking_rate,
        )
        policy = replace(
            DEFAULT_TRANSLATION_V3_POLICY,
            units_per_second=calibration.units_per_second,
        )
        return policy, {
            **calibration.to_dict(),
            "provider": provider_name,
            "voice_id": voice_id,
            "speaking_rate": speaking_rate,
        }

    def _translation_memory(self, source_video_id: UUID) -> dict[int, str]:
        """Approved/current exact memory is context only, never translation authority."""

        rows = list(
            self.db.scalars(
                select(TranslationSegment)
                .join(
                    TranscriptSegment,
                    TranslationSegment.transcript_segment_id == TranscriptSegment.id,
                )
                .where(
                    TranslationSegment.source_video_id == source_video_id,
                    TranslationSegment.is_current.is_(True),
                    TranscriptSegment.is_current.is_(True),
                )
                .order_by(TranslationSegment.segment_index.asc())
            )
        )
        memory: dict[int, str] = {}
        blocked_flags = {
            "translation_gate_failed",
            "translation_too_long_for_slot",
            "duration_rewrite_no_safe_candidate",
        }
        for row in rows:
            text = str(row.text or "").strip()
            flags = set((row.quality_flags_json or {}).get("flags") or [])
            if text and not flags.intersection(blocked_flags) and row.segment_index is not None:
                memory[int(row.segment_index)] = text
        return memory

    @staticmethod
    def _translation_fingerprint(
        drafts: list[TranscriptDraftSegment],
        *,
        preset: TranslationPreset,
        builder: TranslationDraftBuilder,
        prompt: str | None,
        glossary: dict[str, str],
        policy: TranslationV3Policy = DEFAULT_TRANSLATION_V3_POLICY,
    ) -> str:
        return translation_run_fingerprint(
            drafts,
            preset=preset,
            provider_identity=translation_provider_identity(builder.provider),
            user_prompt=prompt,
            glossary=glossary,
            policy=policy,
        )

    def create_analysis_job(
        self,
        request: AudioAnalysisRequest,
        *,
        idempotency_key: str | None = None,
        commit: bool = True,
    ):
        source_video = self._load_source_video(request.source_video_id)
        effective_key = (idempotency_key or "").strip() or f"audio-analysis:{source_video.id}:active"
        # Single-flight is intentionally based on source + job type, not only on
        # a browser-provided key: reconnects and double-clicks must not start a
        # second ASR while the first one owns the GPU.
        active_job = self.db.scalar(
            select(Job).where(
                Job.workspace_id == source_video.workspace_id,
                Job.source_video_id == source_video.id,
                Job.job_type == JobType.ANALYZE_AUDIO,
                Job.status.in_(
                    [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYABLE, JobStatus.WAITING_FOR_REVIEW]
                ),
            ).order_by(Job.created_at.desc())
        )
        if active_job is not None:
            logger.info(
                "audio_analysis_single_flight_hit",
                extra={"job_id": str(active_job.id), "source_video_id": str(source_video.id)},
            )
            return active_job

        # Reuse a stable active-slot key without making completed reanalysis
        # commands impossible.  Historical jobs retain their original logical
        # key plus a terminal suffix for auditability.
        terminal_slot = self.db.scalar(
            select(Job).where(
                Job.workspace_id == source_video.workspace_id,
                Job.idempotency_key == effective_key,
            )
        )
        if terminal_slot is not None:
            terminal_key_digest = hashlib.sha256(effective_key.encode("utf-8")).hexdigest()[:10]
            terminal_slot.idempotency_key = f"{effective_key[:160]}:terminal:{terminal_key_digest}:{terminal_slot.id}"
            self.db.flush()

        payload = {
            "source_video_id": str(source_video.id),
            "translation_preset": request.translation_preset,
            "force_refresh": request.force_refresh,
            "skip_translation": request.skip_translation,
        }
        try:
            job = JobService(self.db).create_job(
                job_type=JobType.ANALYZE_AUDIO,
                workspace_id=source_video.workspace_id,
                source_video_id=source_video.id,
                payload_json=payload,
                idempotency_key=effective_key,
                metadata_json={"progress_authority": "audio_subphase", "subphase_percent": 0},
                commit=commit,
            )
        except IntegrityError:
            self.db.rollback()
            job = self.db.scalar(
                select(Job).where(
                    Job.workspace_id == source_video.workspace_id,
                    Job.idempotency_key == effective_key,
                )
            )
            if job is None or job.job_type != JobType.ANALYZE_AUDIO or job.source_video_id != source_video.id:
                raise
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
        analysis_started_at = time.perf_counter()
        timings_ms: dict[str, int] = {}
        phase("started", 5)
        stage_started_at = time.perf_counter()
        source_video, resolved_input = AudioAssetResolver(self.db, self.storage).resolve(request.source_video_id)
        context = self._storage_context(source_video)
        timings_ms["resolve_ms"] = int((time.perf_counter() - stage_started_at) * 1000)
        phase("resolved_input", 10)

        stage_started_at = time.perf_counter()
        try:
            resolved_input = ensure_canonical_audio(
                self.db,
                self.storage,
                source_video,
                resolved_input,
                job_id=job_id,
            )
        except Exception as exc:
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.AUDIO_EXTRACT_FAILED,
                f"Could not build canonical audio: {exc}",
            ) from exc
        timings_ms["canonical_extract_ms"] = int((time.perf_counter() - stage_started_at) * 1000)
        phase("audio_extract_ready", 14)
        fingerprint = self._analysis_fingerprint(resolved_input)
        if not request.force_refresh:
            cached = self._cached_result(source_video, fingerprint)
            if cached is not None:
                phase("cache_hit", 95)
                logger.info(
                    "audio_analysis_cache_hit",
                    extra={
                        "source_video_id": str(source_video.id),
                        "fingerprint": fingerprint,
                    },
                )
                return cached

        if isinstance(self.stt_provider, FunasrSttProvider) and self.stt_provider.on_lifecycle is None:
            lifecycle_progress = {
                "funasr_started": 35,
                "funasr_waiting": 45,
                "funasr_timed_out": 50,
                "funasr_finished": 55,
            }

            def _funasr_lifecycle(event: str) -> None:
                progress = lifecycle_progress.get(event)
                parts = event.split("|")
                if len(parts) == 3 and parts[0] == "funasr_chunk":
                    try:
                        current = int(parts[1])
                        total = max(1, int(parts[2]))
                        progress = 30 + int((current / total) * 25)
                    except (TypeError, ValueError):
                        progress = 40
                phase(event, progress)

            self.stt_provider.on_lifecycle = _funasr_lifecycle

        analysis_audio = None
        analysis_audio_key = resolved_input.storage_key
        if isinstance(self.storage, LocalStorageBackend) and resolved_input.canonicalized:
            intermediate_started_at = time.perf_counter()
            try:
                audio_settings = get_settings()
                analysis_audio = materialize_analysis_audio(
                    self.storage,
                    source_storage_key=resolved_input.storage_key,
                    source_checksum_sha256=resolved_input.source_checksum_sha256,
                    cache_max_bytes=max(
                        0,
                        int(
                            getattr(
                                audio_settings,
                                "audio_analysis_cache_max_bytes",
                                5_000_000_000,
                            )
                        ),
                    ),
                    cache_min_age_seconds=max(
                        0.0,
                        float(
                            getattr(
                                audio_settings,
                                "audio_analysis_cache_min_age_hours",
                                24.0,
                            )
                        )
                        * 3600.0,
                    ),
                )
                if analysis_audio is not None:
                    analysis_audio_key = analysis_audio.storage_key
            except Exception:
                logger.warning(
                    "analysis_audio_intermediate_unavailable",
                    extra={"source_video_id": str(source_video.id)},
                    exc_info=True,
                )
            timings_ms["analysis_audio_ms"] = int(
                (time.perf_counter() - intermediate_started_at) * 1000
            )

        stage_started_at = time.perf_counter()
        vad = self.vad_provider.detect(
            analysis_audio_key,
            duration_seconds=resolved_input.source_video_duration_seconds,
            source_caption=resolved_input.source_caption,
        )
        timings_ms["vad_ms"] = int((time.perf_counter() - stage_started_at) * 1000)
        mix_quality: dict | None = None
        semantic_dialogue = {
            "recipe_version": SEMANTIC_DIALOGUE_RECIPE_VERSION,
            "translation_ready": False,
            "reason": "speech_not_processed",
            "input_unit_count": 0,
            "output_utterance_count": 0,
        }
        if isinstance(self.storage, LocalStorageBackend) and getattr(resolved_input, "canonicalized", False):
            mix_started_at = time.perf_counter()
            try:
                audio_path = to_windows_long_path(
                    self.storage.resolve(resolved_input.storage_key).absolute_path
                )
                mix_quality = analyze_pcm_wav_mix(audio_path).to_dict()
            except Exception:
                logger.warning(
                    "audio_mix_quality_unavailable",
                    extra={"source_video_id": str(source_video.id)},
                    exc_info=True,
                )
            timings_ms["mix_quality_ms"] = int((time.perf_counter() - mix_started_at) * 1000)
        logger.info(
            "audio_vad_done",
            extra={
                "source_video_id": str(source_video.id),
                "has_speech": vad.has_speech,
                "provider": self.vad_provider.provider_name,
            },
        )
        phase("vad_done", 15)

        duration_seconds = max(
            0.0, float(resolved_input.source_video_duration_seconds or 0.0)
        )
        target_scan_started_at = time.perf_counter()
        target_speech = self._analyze_target_speech(
            audio_storage_key=analysis_audio_key,
            vad=vad,
            duration_seconds=duration_seconds,
        )
        timings_ms["target_speech_scan_ms"] = int(
            (time.perf_counter() - target_scan_started_at) * 1000
        )
        target_speech_enforced = bool(
            isinstance(self.storage, LocalStorageBackend)
            and getattr(resolved_input, "canonicalized", False)
        )
        phase("target_speech_classified", 23)
        asr_authority = high_recall_candidate_authority(
            target_speech,
            vad=vad,
        )
        target_speech_audio: dict[str, Any] | None = None
        asr_consensus: dict[str, Any] = {
            "selected_source": "none",
            "reason": "asr_not_started",
        }
        asr_evidence_contract: dict[str, Any] = {
            "schema_version": ASR_EVIDENCE_SCHEMA_VERSION,
            "recipe_version": ASR_EVIDENCE_RECIPE_VERSION,
            "primary": None,
            "retry": None,
            "selected": None,
            "selected_source": "none",
            "verification_stability": None,
        }
        dialogue_quality_contract: dict[str, Any] = {
            "schema_version": "dialogue_quality_contract_v1",
            "recipe_version": DIALOGUE_VALIDATION_RECIPE_VERSION,
            "quality_complete": False,
            "translation_ready": False,
            "reason": "asr_not_started",
        }
        verification_units: list = []
        target_gate_uncertain = bool(
            target_speech_enforced
            and target_speech.status
            in {TargetSpeechStatus.UNCERTAIN, TargetSpeechStatus.UNAVAILABLE}
        )

        if vad.has_speech and not target_speech_enforced:
            # Compatibility boundary for non-local adapters and injected test
            # providers. Production local PCM never bypasses local audio evidence,
            # including when the local authority is unavailable: that state is
            # fail-closed and must be reviewed instead of running full-file ASR.
            phase("stt_legacy_adapter_started", 30)
            stage_started_at = time.perf_counter()
            units = self.stt_provider.transcribe(
                resolved_input.storage_key,
                source_caption=resolved_input.source_caption,
                duration_seconds=duration_seconds,
            )
            timings_ms["asr_legacy_adapter_ms"] = int(
                (time.perf_counter() - stage_started_at) * 1000
            )
            legacy_evidence = evaluate_asr_evidence(units)
            asr_evidence_contract.update(
                {
                    "primary": {
                        "source": "legacy_adapter",
                        **legacy_evidence.to_dict(),
                    },
                    "selected": legacy_evidence.to_dict(),
                    "selected_source": "legacy_adapter",
                }
            )
            separation = SourceSeparationResult(
                vocal_asset_id=None,
                background_asset_id=None,
                transcription_storage_key=resolved_input.storage_key,
                fallback_used=True,
                difficulty_flags=["target_speech_non_local_adapter"],
                metadata={
                    "provider": "compatibility_adapter",
                    "reason": "target_speech_authority_unavailable",
                    "mix_quality": mix_quality,
                },
            )
        elif (
            vad.has_speech
            and target_speech.status != TargetSpeechStatus.UNAVAILABLE
            and asr_authority.target_intervals
        ):
            separated_vocal_key: str | None = None
            raw_separation: SourceSeparationResult | None = None
            if target_speech.requires_separation:
                phase("target_speech_separation_started", 32)
                stage_started_at = time.perf_counter()
                raw_separation = self.separation_provider.separate(
                    resolved_input.storage_key
                )
                timings_ms["separation_ms"] = int(
                    (time.perf_counter() - stage_started_at) * 1000
                )
                if not raw_separation.fallback_used:
                    separated_vocal_key = raw_separation.transcription_storage_key
                    vocal_vad = self.vad_provider.detect(
                        separated_vocal_key,
                        duration_seconds=duration_seconds,
                        source_caption=None,
                    )
                    vocal_authority = self._analyze_target_speech(
                        audio_storage_key=separated_vocal_key,
                        vad=vocal_vad,
                        duration_seconds=duration_seconds,
                    )
                    target_speech = resolve_after_separation(
                        target_speech,
                        vocal_authority,
                    )
                    asr_authority = high_recall_candidate_authority(
                        target_speech,
                        vad=vad,
                    )
                else:
                    target_gate_uncertain = True
                phase("target_speech_separation_done", 45)
            if raw_separation is None:
                separation = SourceSeparationResult(
                    vocal_asset_id=None,
                    background_asset_id=None,
                    transcription_storage_key=resolved_input.storage_key,
                    fallback_used=True,
                    difficulty_flags=["separation_deferred_target_speech_clear"],
                    metadata={
                        "provider": "target_speech_gate",
                        "reason": "clear_primary_dialogue",
                        "mix_quality": mix_quality,
                        "analysis_audio": analysis_audio.to_dict() if analysis_audio else None,
                    },
                )
                phase("separation_skipped_clear_audio", 45)
            else:
                background_key = str(
                    dict(raw_separation.metadata or {}).get(
                        "background_storage_key"
                    )
                    or ""
                )
                separation = SourceSeparationResult(
                    vocal_asset_id=raw_separation.vocal_asset_id,
                    background_asset_id=raw_separation.background_asset_id,
                    transcription_storage_key=raw_separation.transcription_storage_key,
                    fallback_used=raw_separation.fallback_used,
                    difficulty_flags=list(raw_separation.difficulty_flags),
                    metadata={
                        **dict(raw_separation.metadata or {}),
                        "adaptive_retry": True,
                        "target_speech_selective": True,
                        "demucs_background_storage_key": background_key or None,
                        "background_storage_key": background_key or None,
                        "background_policy": "demucs_no_vocals_pending_dialogue_validation",
                        "mix_quality": mix_quality,
                        "analysis_audio": analysis_audio.to_dict() if analysis_audio else None,
                    },
                )

            if asr_authority.target_intervals and not (
                target_gate_uncertain and raw_separation is not None and raw_separation.fallback_used
            ):
                phase("target_speech_asr_started", 48)
                stage_started_at = time.perf_counter()
                primary_storage_key = separated_vocal_key or resolved_input.storage_key
                primary_source = (
                    "separated_vocal" if separated_vocal_key else "target_mix"
                )
                primary_units, primary_audio = self._transcribe_target_intervals(
                    audio_storage_key=primary_storage_key,
                    source_caption=(
                        None
                        if separated_vocal_key
                        else resolved_input.source_caption
                    ),
                    source_duration_seconds=duration_seconds,
                    authority=asr_authority,
                )
                timings_ms["asr_primary_ms"] = int(
                    (time.perf_counter() - stage_started_at) * 1000
                )
                primary_evidence = evaluate_asr_evidence(primary_units)
                asr_evidence_contract["primary"] = {
                    "source": primary_source,
                    **primary_evidence.to_dict(),
                }
                # Adaptive fallback: clear target-speech intervals normally use
                # the original mix.  If the measured ASR evidence is weak or
                # the inexpensive mix probe recommends separation, pay the
                # Demucs cost once and retry only the candidate intervals.
                if raw_separation is None and self._needs_separation_retry(
                    primary_units,
                    evidence=primary_evidence,
                    mix_quality=mix_quality,
                    vad_speech_ratio=vad.speech_ratio,
                ):
                    phase("adaptive_separation_retry_started", 51)
                    retry_started_at = time.perf_counter()
                    retry_result = self.separation_provider.separate(
                        resolved_input.storage_key
                    )
                    timings_ms["adaptive_separation_ms"] = int(
                        (time.perf_counter() - retry_started_at) * 1000
                    )
                    raw_separation = retry_result
                    if not retry_result.fallback_used:
                        separated_vocal_key = retry_result.transcription_storage_key
                        retry_metadata = dict(retry_result.metadata or {})
                        separation = SourceSeparationResult(
                            vocal_asset_id=retry_result.vocal_asset_id,
                            background_asset_id=retry_result.background_asset_id,
                            transcription_storage_key=retry_result.transcription_storage_key,
                            fallback_used=False,
                            difficulty_flags=list(retry_result.difficulty_flags),
                            metadata={
                                **retry_metadata,
                                "adaptive_retry": True,
                                "target_speech_selective": True,
                                "background_storage_key": retry_metadata.get("background_storage_key"),
                                "demucs_background_storage_key": retry_metadata.get("background_storage_key"),
                                "background_policy": "demucs_no_vocals_pending_dialogue_validation",
                                "mix_quality": mix_quality,
                            },
                        )
                        vocal_vad = self.vad_provider.detect(
                            separated_vocal_key,
                            duration_seconds=duration_seconds,
                            source_caption=None,
                        )
                        vocal_authority = self._analyze_target_speech(
                            audio_storage_key=separated_vocal_key,
                            vad=vocal_vad,
                            duration_seconds=duration_seconds,
                        )
                        target_speech = resolve_after_separation(
                            target_speech,
                            vocal_authority,
                        )
                        asr_authority = high_recall_candidate_authority(
                            target_speech,
                            vad=vad,
                        )
                        retry_units, retry_audio = self._transcribe_target_intervals(
                            audio_storage_key=separated_vocal_key,
                            source_caption=None,
                            source_duration_seconds=duration_seconds,
                            authority=asr_authority,
                        )
                        retry_evidence = evaluate_asr_evidence(retry_units)
                        asr_evidence_contract["retry"] = {
                            "source": "separated_vocal_adaptive",
                            "gain_vs_primary": round(
                                retry_evidence.overall_score
                                - primary_evidence.overall_score,
                                4,
                            ),
                            **retry_evidence.to_dict(),
                        }
                        if evidence_prefers_candidate(
                            retry_evidence,
                            primary_evidence,
                        ):
                            primary_units = retry_units
                            primary_source = "separated_vocal_adaptive"
                            primary_evidence = retry_evidence
                            primary_audio = {
                                "mode": "adaptive_separated_vocal",
                                "fallback_from": "target_mix",
                                **retry_audio,
                            }
                        phase("adaptive_separation_retry_done", 54)
                    else:
                        phase("adaptive_separation_retry_fallback", 54)
                preliminary = validate_dialogue_units(
                    primary_units,
                    authority=target_speech,
                )
                verify_intervals = list(preliminary.verification_intervals)
                if separated_vocal_key and not primary_units:
                    verify_intervals = list(asr_authority.target_intervals)
                verification_audio = None
                if separated_vocal_key and verify_intervals:
                    phase("selective_asr_verification_started", 53)
                    stage_started_at = time.perf_counter()
                    verification_units, verification_audio = self._transcribe_target_intervals(
                        audio_storage_key=resolved_input.storage_key,
                        source_caption=resolved_input.source_caption,
                        source_duration_seconds=duration_seconds,
                        authority=verification_authority(
                            asr_authority,
                            verify_intervals,
                        ),
                    )
                    timings_ms["asr_selective_verification_ms"] = int(
                        (time.perf_counter() - stage_started_at) * 1000
                    )
                verification_stability = compare_asr_stability(
                    primary_units,
                    verification_units,
                )
                selected_evidence = (
                    evaluate_asr_evidence(
                        primary_units,
                        stability_score=verification_stability,
                    )
                    if verification_stability is not None
                    else primary_evidence
                )
                asr_evidence_contract.update(
                    {
                        "selected": selected_evidence.to_dict(),
                        "selected_source": primary_source,
                        "verification_stability": verification_stability,
                    }
                )
                units = merge_selective_verification(
                    primary_units,
                    verification_units,
                )
                target_speech_audio = {
                    "mode": "primary_asr_selective_verification_v1",
                    "primary_source": primary_source,
                    "primary": primary_audio,
                    "verification": verification_audio,
                }
                asr_consensus = {
                    "recipe_version": "primary-asr-selective-verification-v1",
                    "selected_source": primary_source,
                    "primary_units": len(primary_units),
                    "verification_units": len(verification_units),
                    "verification_interval_count": len(verify_intervals),
                    "candidate_interval_count": len(asr_authority.target_intervals),
                    "candidate_seconds": round(
                        sum(
                            row.duration_seconds
                            for row in asr_authority.target_intervals
                        ),
                        3,
                    ),
                    "full_dual_asr": False,
                    "asr_evidence_recipe_version": ASR_EVIDENCE_RECIPE_VERSION,
                    "selected_evidence_score": selected_evidence.overall_score,
                    "selected_evidence_state": selected_evidence.state.value,
                    "verification_stability": verification_stability,
                }
                logger.info(
                    "audio_asr_evidence_selected",
                    extra={
                        "source_video_id": str(source_video.id),
                        "selected_source": primary_source,
                        "score": selected_evidence.overall_score,
                        "state": selected_evidence.state.value,
                        "recovery_recommended": (
                            selected_evidence.recovery_recommended
                        ),
                        "verification_stability": verification_stability,
                    },
                )
            else:
                units = []
                target_gate_uncertain = True
        else:
            separation = SourceSeparationResult(
                vocal_asset_id=None,
                background_asset_id=None,
                transcription_storage_key=resolved_input.storage_key,
                fallback_used=True,
                difficulty_flags=[
                    "skip_dubbing",
                    "separation_skipped_no_target_speech",
                ],
                metadata={
                    "provider": "target_speech_gate",
                    "reason": (
                        "non_dialogue_vocal_or_music"
                        if vad.has_speech
                        else "no_vad_speech"
                    ),
                },
            )
            units = []
            semantic_dialogue = {
                **semantic_dialogue,
                "reason": (
                    "no_target_dialogue"
                    if vad.has_speech
                    else "no_vad_speech"
                ),
            }
            phase("stt_skipped_no_target_speech", 55)

        if units:
            temporal_started_at = time.perf_counter()
            units = fit_funasr_units_to_duration(
                units,
                duration_seconds=duration_seconds,
            )
            units = apply_caption_asr_consensus(
                units,
                caption=resolved_input.source_caption,
                duration_seconds=duration_seconds,
            )
            units = drop_punctuation_only_units(units)
            validation_intervals = (
                [
                    [row.start_seconds, row.end_seconds]
                    for row in asr_authority.target_intervals
                ]
                if target_speech_enforced
                else (vad.metadata or {}).get("speech_intervals") or []
            )
            units = validate_transcription_timeline(
                units,
                duration_seconds=duration_seconds,
                speech_intervals=validation_intervals,
            )
            dialogue_validation = validate_dialogue_units(
                units,
                authority=target_speech,
                secondary_units=verification_units,
            )
            units = list(dialogue_validation.units)
            dialogue_quality_contract = dict(dialogue_validation.diagnostics)
            if int(dialogue_quality_contract.get("review_unit_count") or 0) > 0:
                target_gate_uncertain = True
            phase("dialogue_quality_validated", 60)
            semantic_started_at = time.perf_counter()
            semantic_result = segment_semantic_dialogue(units)
            units = validate_transcription_timeline(
                list(semantic_result.units),
                duration_seconds=duration_seconds,
                speech_intervals=validation_intervals,
            )
            semantic_dialogue = dict(semantic_result.diagnostics)
            timings_ms["semantic_segmentation_ms"] = int(
                (time.perf_counter() - semantic_started_at) * 1000
            )
            timings_ms["temporal_validation_ms"] = int(
                (time.perf_counter() - temporal_started_at) * 1000
            )
            phase("primary_asr_selective_verification_done", 61)
            phase("semantic_dialogue_segmented", 63)

        demucs_background_key = str(
            dict(separation.metadata or {}).get(
                "demucs_background_storage_key"
            )
            or ""
        )
        if demucs_background_key and units:
            validated_dialogue_intervals = [
                TargetSpeechInterval(
                    start_seconds=max(0.0, float(row.start_seconds) - 0.12),
                    end_seconds=min(duration_seconds, float(row.end_seconds) + 0.12),
                    decision="VALIDATED_DIALOGUE_BACKGROUND_REPLACEMENT",
                    confidence=float(row.confidence or 0.75),
                    speech_score=1.0,
                    music_score=0.0,
                    singing_score=0.0,
                    reasons=("dialogue_validation_v1",),
                )
                for row in units
                if row.end_seconds > row.start_seconds
            ]
            validated_background_key = materialize_preserved_background(
                self.storage,
                original_storage_key=resolved_input.storage_key,
                demucs_background_storage_key=demucs_background_key,
                target_intervals=validated_dialogue_intervals,
            )
            if validated_background_key:
                separation = SourceSeparationResult(
                    vocal_asset_id=separation.vocal_asset_id,
                    background_asset_id=separation.background_asset_id,
                    transcription_storage_key=separation.transcription_storage_key,
                    fallback_used=separation.fallback_used,
                    difficulty_flags=list(separation.difficulty_flags),
                    metadata={
                        **dict(separation.metadata or {}),
                        "background_storage_key": validated_background_key,
                        "background_policy": (
                            "original_outside_validated_dialogue_no_vocals_inside"
                        ),
                        "validated_dialogue_interval_count": len(
                            validated_dialogue_intervals
                        ),
                    },
                )

        target_dialogue_expected = bool(
            asr_authority.target_intervals
            if target_speech_enforced
            else vad.has_speech
        )
        empty_asr_after_speech_gate = bool(target_dialogue_expected and not units)
        vad_measured_speech = bool(
            vad.has_speech
            and "silero_vad_executed" in (vad.difficulty_flags or [])
        )
        dialogue_uncertain = bool(
            target_gate_uncertain
            or (empty_asr_after_speech_gate and vad_measured_speech)
        )
        if empty_asr_after_speech_gate or target_gate_uncertain:
            # Never fill DialogueBeats from Douyin caption/title/hashtags.
            extra_flags = (
                (
                    {
                        "target_speech_or_asr_uncertain",
                        "needs_operator_review",
                    }
                    | ({"no_asr_dialogue"} if not units else {"target_speech_partial_uncertain"})
                )
                if dialogue_uncertain
                else {"skip_dubbing", "no_asr_dialogue", "caption_not_dialogue", "dialogue_unverified"}
            )
            separation = SourceSeparationResult(
                vocal_asset_id=separation.vocal_asset_id,
                background_asset_id=separation.background_asset_id,
                transcription_storage_key=separation.transcription_storage_key,
                fallback_used=separation.fallback_used,
                difficulty_flags=list({*separation.difficulty_flags, *extra_flags}),
                metadata={
                    **separation.metadata,
                    "reason": (
                        "target_speech_or_asr_uncertain"
                        if dialogue_uncertain
                        else "empty_asr_no_caption_dialogue"
                    ),
                    "vad_speech_ratio": vad.speech_ratio,
                    "source_caption_present": bool((resolved_input.source_caption or "").strip()),
                },
            )

        logger.info(
            "audio_transcription_done",
            extra={"source_video_id": str(source_video.id), "unit_count": len(units), "provider": self.stt_provider.provider_name},
        )
        phase("stt_done", 65)

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
        flags_summary.update(
            {
                "asr_non_dialogue_rejected": int(
                    dialogue_quality_contract.get("dropped_unit_count") or 0
                ),
                "dialogue_validation_review": int(
                    dialogue_quality_contract.get("review_unit_count") or 0
                ),
            }
        )
        if dialogue_uncertain:
            flags_summary.update(
                [
                    "target_speech_or_asr_uncertain",
                    "needs_operator_review",
                    *(
                        ["asr_empty_despite_vad_speech"]
                        if not units and vad_measured_speech
                        else []
                    ),
                ]
            )
        elif empty_asr_after_speech_gate:
            flags_summary.update(["skip_dubbing", "caption_not_dialogue", "dialogue_unverified"])
        elif (
            target_speech_enforced
            and target_speech.status == TargetSpeechStatus.NO_TARGET_SPEECH
        ):
            flags_summary.update(
                ["skip_dubbing", "non_dialogue_vocal_or_music"]
            )
        elif not vad.has_speech:
            flags_summary.update(["skip_dubbing", "caption_not_dialogue"])

        target_speech_payload = target_speech.to_dict()
        target_speech_sha256 = hashlib.sha256(
            json.dumps(
                target_speech_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        target_speech_summary = {
            "schema_version": target_speech_payload.get("schema_version"),
            "recipe_version": target_speech_payload.get("recipe_version"),
            "status": target_speech_payload.get("status"),
            "provider": target_speech_payload.get("provider"),
            "requires_separation": target_speech_payload.get(
                "requires_separation"
            ),
            "target_intervals": target_speech_payload.get("target_intervals"),
            "ambiguous_intervals": target_speech_payload.get(
                "ambiguous_intervals"
            ),
            "rejected_intervals": target_speech_payload.get(
                "rejected_intervals"
            ),
            "diagnostics": target_speech_payload.get("diagnostics"),
            "authority_sha256": target_speech_sha256,
        }

        phase("persist_outputs", 88)
        version = self._next_analysis_version(source_video.id)
        persist_started_at = time.perf_counter()
        try:
            self._mark_previous_non_current(source_video.id)
            self._invalidate_downstream_authority(
                source_video,
                new_analysis_version=version,
                job_id=job_id,
            )
            separation_assets = self._persist_separation_assets(
                source_video,
                resolved_input,
                separation,
                job_id=job_id,
            )
            if separation_assets:
                separation_metadata = dict(separation.metadata or {})
                for asset in separation_assets:
                    role = (asset.metadata_json or {}).get("role")
                    if role == "demucs_vocals":
                        separation_metadata["vocal_asset_id"] = str(asset.id)
                    elif role in {
                        "demucs_no_vocals",
                        "target_speech_preserved_background",
                    }:
                        separation_metadata["background_asset_id"] = str(asset.id)
                separation = SourceSeparationResult(
                    vocal_asset_id=separation.vocal_asset_id,
                    background_asset_id=separation.background_asset_id,
                    transcription_storage_key=separation.transcription_storage_key,
                    fallback_used=separation.fallback_used,
                    difficulty_flags=list(separation.difficulty_flags),
                    metadata=separation_metadata,
                )
            transcript_rows = self._persist_transcripts(source_video, transcript_drafts, version, job_id)
            translation_rows = self._persist_translations(source_video, transcript_rows, translations, job_id)
            transcript_authority_payload = [
                {
                    "segment_index": int(row.segment_index),
                    "start_ms": int(row.start_ms),
                    "end_ms": int(row.end_ms),
                    "text": str(row.text or ""),
                    "normalized_text": str(row.normalized_text or ""),
                    "confidence": row.confidence,
                    "speaker_label": getattr(row, "speaker_label", None),
                    "flags": list((row.difficulty_flags_json or {}).get("flags") or []),
                }
                for row in transcript_rows
            ]
            transcript_sha256 = hashlib.sha256(
                json.dumps(
                    transcript_authority_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            semantic_authority_sha256 = str(semantic_dialogue.get("authority_sha256") or "") or None
            dialogue_quality_complete = bool(dialogue_quality_contract.get("quality_complete"))
            semantic_translation_ready = bool(semantic_dialogue.get("translation_ready"))
            operator_review_required = bool(
                dialogue_uncertain
                or int(dialogue_quality_contract.get("review_unit_count") or 0) > 0
                or any(
                    "needs_operator_review" in (row.difficulty_flags_json or {}).get("flags", [])
                    for row in transcript_rows
                )
            )
            machine_approval_state = (
                "uncertain_review_required"
                if dialogue_uncertain
                else "machine_approved_risk"
                if transcript_rows and any(
                    (row.difficulty_flags_json or {}).get("flags")
                    for row in transcript_rows
                )
                else "machine_approved"
                if transcript_rows
                else "no_dialogue"
            )
            authority_manifest_payload = AudioAnalysisAuthorityManifest(
                schema_version=AUTHORITY_MANIFEST_SCHEMA_VERSION,
                analysis_version=version,
                analysis_fingerprint=fingerprint,
                source_audio_checksum_sha256=resolved_input.source_checksum_sha256,
                canonical_audio_checksum_sha256=(
                    resolved_input.source_checksum_sha256
                    if resolved_input.canonicalized
                    else None
                ),
                transcript_sha256=transcript_sha256,
                target_speech_authority_sha256=target_speech_sha256,
                semantic_dialogue_authority_sha256=semantic_authority_sha256,
                dialogue_quality_complete=dialogue_quality_complete,
                semantic_translation_ready=semantic_translation_ready,
                machine_approval_state=machine_approval_state,
                operator_review_required=operator_review_required,
                translation_ready=bool(
                    semantic_translation_ready
                    and dialogue_quality_complete
                    and not operator_review_required
                ),
            ).to_dict()
            # Keep the two existing readiness producers explicit in one
            # persisted contract.  Translation/TTS must never infer readiness
            # from segmentation alone when dialogue validation still requests
            # review.
            authority_manifest_payload["dialogue_quality_translation_ready"] = bool(
                dialogue_quality_contract.get("translation_ready")
            )
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
            meta["mix_quality"] = mix_quality
            meta["target_speech_authority"] = target_speech_summary
            meta["target_speech_asr_consensus"] = asr_consensus
            meta["asr_evidence"] = asr_evidence_contract
            meta["dialogue_quality_contract"] = dialogue_quality_contract
            meta["semantic_dialogue_segmentation"] = semantic_dialogue
            meta["audio_analysis_authority"] = authority_manifest_payload
            meta["separation"] = {
                "provider": (
                    self.separation_provider.provider_name if vad.has_speech else "skipped"
                ),
                "fallback_used": separation.fallback_used,
                "difficulty_flags": list(separation.difficulty_flags),
                "metadata": dict(separation.metadata or {}),
            }
            meta["audio_analysis_cache"] = {
                "fingerprint": fingerprint,
                "recipe_version": AUDIO_ANALYSIS_RECIPE_VERSION,
                "source_checksum_sha256": resolved_input.source_checksum_sha256,
                "analysis_version": version,
                "flags_summary": dict(flags_summary),
            }
            source_video.metadata_json = meta
            assets = [*separation_assets,
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
                        "mix_quality": mix_quality,
                        "analysis_audio": analysis_audio.to_dict() if analysis_audio else None,
                        "target_speech_authority": {
                            **target_speech_payload,
                            "authority_sha256": target_speech_sha256,
                        },
                        "target_speech_audio": target_speech_audio,
                        "target_speech_asr_consensus": asr_consensus,
                        "asr_evidence": asr_evidence_contract,
                        "dialogue_quality_contract": dialogue_quality_contract,
                        "semantic_dialogue_segmentation": semantic_dialogue,
                        "audio_analysis_authority": authority_manifest_payload,
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
                        "fingerprint": fingerprint,
                        "recipe_version": AUDIO_ANALYSIS_RECIPE_VERSION,
                        "metrics": dict(timings_ms),
                    },
                    filename=f"{version}_audio_analysis_metadata.json",
                    job_id=job_id,
                ),
                self._persist_json_asset(
                    source_video,
                    context,
                    MediaAssetType.TRANSCRIPT_JSON,
                    {
                        "analysis_version": version,
                        "target_speech_authority_ref": target_speech_summary,
                        "dialogue_quality_contract": dialogue_quality_contract,
                        "semantic_dialogue_segmentation": semantic_dialogue,
                        "audio_analysis_authority": authority_manifest_payload,
                        "segments": [self._transcript_payload(row) for row in transcript_rows],
                    },
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
            timings_ms["persist_ms"] = int((time.perf_counter() - persist_started_at) * 1000)
            timings_ms["total_ms"] = int((time.perf_counter() - analysis_started_at) * 1000)
            selected_asr_evidence = dict(
                asr_evidence_contract.get("selected") or {}
            )
            metrics_payload = {
                **timings_ms,
                "cache_hit": False,
                "adaptive_separation_used": bool((separation.metadata or {}).get("adaptive_retry")),
                "separation_cache_hit": bool((separation.metadata or {}).get("cache_hit")),
                "target_speech_status": target_speech.status.value,
                "target_speech_seconds": dict(target_speech.diagnostics).get(
                    "target_seconds"
                ),
                "target_speech_ratio": dict(target_speech.diagnostics).get(
                    "target_ratio"
                ),
                "target_speech_authority_sha256": target_speech_sha256,
                "asr_evidence_recipe_version": ASR_EVIDENCE_RECIPE_VERSION,
                "asr_evidence_score": selected_asr_evidence.get("overall_score"),
                "asr_evidence_state": selected_asr_evidence.get("state"),
                "asr_evidence_recovery_recommended": selected_asr_evidence.get(
                    "recovery_recommended"
                ),
                "asr_verification_stability": asr_evidence_contract.get(
                    "verification_stability"
                ),
                "dialogue_quality_complete": bool(
                    dialogue_quality_contract.get("quality_complete")
                ),
                "dialogue_units_dropped": int(
                    dialogue_quality_contract.get("dropped_unit_count") or 0
                ),
                "dialogue_units_review": int(
                    dialogue_quality_contract.get("review_unit_count") or 0
                ),
            }
            # Assign a fresh top-level object.  ``meta`` was assigned earlier in
            # this transaction; mutating that same dict is invisible to
            # SQLAlchemy JSONB history tracking.
            source_video.metadata_json = {
                **meta,
                "audio_analysis_metrics": metrics_payload,
            }
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
                "metrics": timings_ms,
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
            metrics=dict(timings_ms),
        )

    def create_translation_job(
        self,
        source_video_id: UUID,
        *,
        translation_preset: TranslationPreset = TranslationPreset.LITERAL_SAFE,
        force_refresh: bool = True,
        require_source_approved: bool = True,
        idempotency_key: str | None = None,
        commit: bool = True,
    ):
        source_video = self._load_source_video(source_video_id)
        self._require_translation_input_ready(
            source_video,
            require_source_approved=require_source_approved,
        )
        beats = self.get_transcript_segments(source_video_id)
        if not beats:
            raise AudioAnalysisError(AudioAnalysisErrorCode.MISSING_SOURCE_ASSET, "No current transcript beats to translate")
        self._assert_current_transcript_authority(source_video, beats)
        semantic_contract = dict(
            (source_video.metadata_json or {}).get("semantic_dialogue_segmentation") or {}
        )
        if (
            semantic_contract.get("recipe_version") == SEMANTIC_DIALOGUE_RECIPE_VERSION
            and not bool(semantic_contract.get("translation_ready"))
        ):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Semantic dialogue segmentation did not preserve a valid non-overlapping token authority",
            )
        if require_source_approved and any(beat.status != TranscriptSegmentStatus.APPROVED for beat in beats):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Approve all source transcript beats before literal translation",
            )
        drafts = self._translation_drafts(beats)
        settings_svc = WorkspaceSettingsService(self.db)
        prompt = settings_svc.get_translation_user_prompt(source_video.workspace_id)
        builder = self._translation_builder_for_workspace(source_video.workspace_id)
        glossary = self._translation_glossary(source_video)
        policy, speech_rate_calibration = self._translation_policy(source_video.workspace_id)
        fingerprint = self._translation_fingerprint(
            drafts,
            preset=translation_preset,
            builder=builder,
            prompt=prompt,
            glossary=glossary,
            policy=policy,
        )
        effective_key = (idempotency_key or "").strip() or (
            f"translation:{source_video.id}:{translation_preset}:{fingerprint[:24]}"
        )
        active_job = self.db.scalar(
            select(Job).where(
                Job.workspace_id == source_video.workspace_id,
                Job.source_video_id == source_video.id,
                Job.job_type == JobType.BUILD_TRANSLATION_DRAFT,
                Job.status.in_(
                    [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYABLE, JobStatus.WAITING_FOR_REVIEW]
                ),
            ).order_by(Job.created_at.desc())
        )
        if active_job is not None:
            logger.info(
                "translation_single_flight_hit",
                extra={"job_id": str(active_job.id), "source_video_id": str(source_video.id)},
            )
            return active_job

        from src.audio_pipeline.translation_provider_preflight import (
            TranslationProviderPreflightResult,
            preflight_translation_provider,
        )

        provider_preflight = (
            TranslationProviderPreflightResult(
                ok=True,
                provider=str(getattr(self.translation_provider, "provider_name", "explicit")),
                detail="explicit_provider",
                cached=True,
            )
            if self._translation_provider_explicit
            else preflight_translation_provider(
                settings_svc.get_translation_ai(source_video.workspace_id)
            )
        )
        if not provider_preflight.ok and not provider_preflight.retryable:
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSLATION_FAILED,
                (
                    "translation_provider_preflight_failed:"
                    f"{provider_preflight.detail[:320]} "
                    "[terminal — open Translation AI settings, run Test Connection, "
                    "then resume this translation stage]"
                ),
            )
        if not provider_preflight.ok:
            logger.warning(
                "translation_provider_preflight_transient",
                extra={
                    "source_video_id": str(source_video.id),
                    "provider": provider_preflight.provider,
                },
            )

        terminal_slot = self.db.scalar(
            select(Job).where(
                Job.workspace_id == source_video.workspace_id,
                Job.idempotency_key == effective_key,
            )
        )
        if terminal_slot is not None:
            digest = hashlib.sha256(effective_key.encode("utf-8")).hexdigest()[:10]
            terminal_slot.idempotency_key = (
                f"{effective_key[:150]}:terminal:{digest}:{terminal_slot.id}"
            )
            self.db.flush()

        payload = {
            "source_video_id": str(source_video.id),
            "translation_preset": translation_preset,
            "force_refresh": force_refresh,
            "require_source_approved": require_source_approved,
            "translation_recipe_version": TRANSLATION_V3_RECIPE_VERSION,
            "translation_fingerprint": fingerprint,
            "speech_rate_calibration": speech_rate_calibration,
        }
        try:
            job = JobService(self.db).create_job(
                job_type=JobType.BUILD_TRANSLATION_DRAFT,
                workspace_id=source_video.workspace_id,
                source_video_id=source_video.id,
                payload_json=payload,
                idempotency_key=effective_key,
                metadata_json={
                    "progress_authority": "translation_v3_subphase",
                    "translation_recipe_version": TRANSLATION_V3_RECIPE_VERSION,
                    "translation_fingerprint": fingerprint,
                    "speech_rate_calibration": speech_rate_calibration,
                    "subphase_percent": 0,
                    "provider_preflight": {
                        "ok": provider_preflight.ok,
                        "provider": provider_preflight.provider,
                        "cached": provider_preflight.cached,
                        "degraded_to_fallback": provider_preflight.degraded_to_fallback,
                    },
                },
                commit=commit,
            )
        except IntegrityError:
            self.db.rollback()
            job = self.db.scalar(
                select(Job).where(
                    Job.workspace_id == source_video.workspace_id,
                    Job.idempotency_key == effective_key,
                )
            )
            if (
                job is None
                or job.job_type != JobType.BUILD_TRANSLATION_DRAFT
                or job.source_video_id != source_video.id
            ):
                raise
        logger.info(
            "translation_draft_job_created",
            extra={
                "job_id": str(job.id),
                "source_video_id": str(source_video.id),
                "preset": str(translation_preset),
                "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
                "fingerprint": fingerprint,
            },
        )
        return job

    def run_translation_only(
        self,
        source_video_id: UUID,
        *,
        translation_preset: TranslationPreset = TranslationPreset.LITERAL_SAFE,
        require_source_approved: bool = True,
        force_refresh: bool = True,
        job_id: UUID | None = None,
        on_progress: AnalysisPhaseHook | None = None,
    ) -> AudioAnalysisResult:
        """Phase B: literal translate current transcript beats. Does not run FunASR."""
        source_video = self._load_source_video(source_video_id)
        self._require_translation_input_ready(
            source_video,
            require_source_approved=require_source_approved,
        )
        context = self._storage_context(source_video)
        beats = self.get_transcript_segments(source_video_id)
        if not beats:
            raise AudioAnalysisError(AudioAnalysisErrorCode.MISSING_SOURCE_ASSET, "No current transcript beats to translate")
        self._assert_current_transcript_authority(source_video, beats)
        semantic_contract = dict(
            (source_video.metadata_json or {}).get("semantic_dialogue_segmentation") or {}
        )
        if (
            semantic_contract.get("recipe_version") == SEMANTIC_DIALOGUE_RECIPE_VERSION
            and not bool(semantic_contract.get("translation_ready"))
        ):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Semantic dialogue segmentation did not preserve a valid non-overlapping token authority",
            )
        if require_source_approved and any(beat.status != TranscriptSegmentStatus.APPROVED for beat in beats):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Approve all source transcript beats before literal translation",
            )

        if on_progress is not None:
            on_progress("premerge_dialogue_beats", 2)
        beats, premerge_summary = self._materialize_translation_premerge(
            source_video,
            beats,
            job_id=job_id,
        )

        draft_segments = self._translation_drafts(beats)
        settings_svc = WorkspaceSettingsService(self.db)
        db_prompt = settings_svc.get_translation_user_prompt(source_video.workspace_id)
        builder = self._translation_builder_for_workspace(source_video.workspace_id)
        max_concurrency = self._translation_concurrency(builder)
        glossary = self._translation_glossary(source_video)
        translation_memory = self._translation_memory(source_video_id)
        policy, speech_rate_calibration = self._translation_policy(source_video.workspace_id)
        fingerprint = self._translation_fingerprint(
            draft_segments,
            preset=translation_preset,
            builder=builder,
            prompt=db_prompt,
            glossary=glossary,
            policy=policy,
        )

        if not force_refresh:
            cached = self._cached_translation_result(
                source_video,
                beats=beats,
                fingerprint=fingerprint,
            )
            if cached is not None:
                if on_progress is not None:
                    on_progress("translation_cache_hit", 100)
                return cached

        checkpoint = self._translation_checkpoint(job_id, fingerprint=fingerprint)

        def _progress(completed: int, total: int, **details: object) -> None:
            if on_progress is None or total <= 0:
                return
            # Reserve 10–90% for translate loop so prepare/finalize stay distinct in UI.
            pct = 10 + int((completed / total) * 80)
            phase = str(details.get("phase") or f"translate_beat_{completed}_of_{total}")
            on_progress(phase, pct)

        def _checkpoint(block_id: str, block_rows, block_number: int, block_total: int) -> None:
            self._persist_translation_checkpoint(
                job_id,
                fingerprint=fingerprint,
                block_id=block_id,
                rows=block_rows,
                block_number=block_number,
                block_total=block_total,
            )

        if on_progress is not None:
            on_progress("build_context_blocks", 5)
        try:
            translations = builder.build(
                draft_segments,
                preset=translation_preset,
                user_prompt=db_prompt,
                max_concurrency=max_concurrency,
                policy=policy,
                glossary=glossary,
                translation_memory=translation_memory,
                checkpoint=checkpoint,
                on_checkpoint=_checkpoint,
                on_progress=_progress,
            )
        except RuntimeError as exc:
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSLATION_FAILED,
                str(exc),
            ) from exc
        if on_progress is not None:
            on_progress("validate_candidates", 91)
        translations = [
            replace(
                row,
                metadata={
                    **row.metadata,
                    "translation_v3": {
                        **dict(row.metadata.get("translation_v3") or {}),
                        "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
                        "run_fingerprint": fingerprint,
                        "speech_policy": policy.to_dict(),
                        "speech_rate_calibration": speech_rate_calibration,
                    },
                },
            )
            for row in translations
        ]
        quality_contract = build_translation_quality_contract(
            translations,
            total_count=len(beats),
        )
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
            if on_progress is not None:
                on_progress("persist_translation_v3", 94)
            self._mark_previous_translations_non_current(source_video_id)
            translation_rows = self._persist_translations(source_video, beats, translations, job_id)
            if not translation_rows:
                raise AudioAnalysisError(
                    AudioAnalysisErrorCode.TRANSLATION_FAILED,
                    "Literal translation persisted 0 segments. Restart worker / check BUILD_TRANSLATION_DRAFT handler.",
                )
            source_transcript_sha256 = self._transcript_authority_sha256(beats)
            translation_authority = build_translation_authority(
                source_video_id=source_video.id,
                analysis_version=analysis_version,
                source_transcript_sha256=source_transcript_sha256,
                translation_fingerprint=fingerprint,
                prompt=db_prompt,
                provider_identity=translation_provider_identity(builder.provider),
                quality_contract=quality_contract,
                translation_rows=translation_rows,
                job_id=job_id,
            )
            row_authority_ref = {
                "schema_version": translation_authority["schema_version"],
                "source_transcript_sha256": source_transcript_sha256,
                "translation_fingerprint": fingerprint,
                "translation_rows_sha256": translation_authority["translation_rows_sha256"],
            }
            for translation_row in translation_rows:
                translation_row.metadata_json = {
                    **dict(getattr(translation_row, "metadata_json", None) or {}),
                    "translation_authority_ref": row_authority_ref,
                }
            meta = dict(source_video.metadata_json or {})
            meta["dialogue_phase"] = (
                "translated_literal_partial" if gated else "translated_literal"
            )
            meta["translation_preset"] = str(translation_preset)
            meta["translation_row_count"] = len(translation_rows)
            meta["translation_filled_count"] = len(non_empty)
            meta["translation_count"] = len(non_empty)
            meta["translation_gate_failed_count"] = len(gated)
            meta["translation_recipe_version"] = TRANSLATION_V3_RECIPE_VERSION
            meta["translation_quality_contract"] = quality_contract
            meta["translation_authority"] = translation_authority
            meta["translation_v3_cache"] = {
                "fingerprint": fingerprint,
                "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
                "analysis_version": analysis_version,
                "job_id": str(job_id) if job_id else None,
                "quality_contract": quality_contract,
                "speech_rate_calibration": speech_rate_calibration,
                "translation_authority": translation_authority,
            }
            source_video.metadata_json = meta
            self._persist_json_asset(
                source_video,
                context,
                MediaAssetType.TRANSLATION_DRAFT_JSON,
                {
                    "analysis_version": analysis_version,
                    "translation_preset": translation_preset,
                    "literal_only": translation_preset == TranslationPreset.LITERAL_SAFE,
                    "translation_recipe_version": TRANSLATION_V3_RECIPE_VERSION,
                    "translation_fingerprint": fingerprint,
                    "translation_authority": translation_authority,
                    "quality_contract": quality_contract,
                    "speech_rate_calibration": speech_rate_calibration,
                    "translation_premerge": premerge_summary,
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
            metrics={
                "cache_hit": False,
                "translation_recipe_version": TRANSLATION_V3_RECIPE_VERSION,
                "translation_fingerprint": fingerprint,
                "quality_contract": quality_contract,
                "speech_rate_calibration": speech_rate_calibration,
                "translation_premerge": premerge_summary,
            },
        )

    def _materialize_translation_premerge(
        self,
        source_video: SourceVideo,
        beats: list,
        *,
        job_id: UUID | None,
    ) -> tuple[list, dict]:
        """Persist immutable merged source beats before the first provider call."""

        groups = plan_translation_premerge(beats)
        merge_groups = [group for group in groups if len(group.members) > 1]
        summary = {
            "recipe_version": TRANSLATION_PREMERGE_RECIPE_VERSION,
            "input_beat_count": len(beats),
            "output_beat_count": len(groups),
            "merged_group_count": len(merge_groups),
            "merged_member_count": sum(len(group.members) for group in merge_groups),
            "materialized": False,
        }
        if not merge_groups:
            return beats, summary
        # Pure unit-test fixtures and compatibility callers may pass duck-typed
        # rows. Planning remains testable, while DB mutation is ORM-only.
        if not all(isinstance(member, TranscriptSegment) for group in groups for member in group.members):
            return beats, {**summary, "skipped_reason": "non_orm_transcript_rows"}

        try:
            materialized: list[TranscriptSegment] = []
            lineage_hashes: list[str] = []
            for group in merge_groups:
                members = list(group.members)
                first = members[0]
                lineage = {
                    "recipe_version": TRANSLATION_PREMERGE_RECIPE_VERSION,
                    "member_ids": [str(member.id) for member in members],
                    "member_indices": [int(member.segment_index) for member in members],
                    "start_ms": int(first.start_ms),
                    "end_ms": int(members[-1].end_ms),
                    "reasons": list(group.reasons),
                }
                lineage_hash = hashlib.sha256(
                    json.dumps(lineage, ensure_ascii=False, sort_keys=True).encode("utf-8")
                ).hexdigest()
                max_version = self.db.scalar(
                    select(func.max(TranscriptSegment.version)).where(
                        TranscriptSegment.source_video_id == source_video.id,
                        TranscriptSegment.segment_index == int(first.segment_index),
                    )
                )
                flags = list(
                    dict.fromkeys(
                        [
                            *(
                                flag
                                for member in members
                                for flag in list((member.difficulty_flags_json or {}).get("flags") or [])
                            ),
                            "translation_temporal_premerge",
                        ]
                    )
                )
                confidences = [
                    float(member.confidence)
                    for member in members
                    if member.confidence is not None
                ]
                speakers = [
                    str(member.speaker_label).strip()
                    for member in members
                    if str(member.speaker_label or "").strip()
                ]
                for member in members:
                    member.is_current = False
                row = TranscriptSegment(
                    workspace_id=source_video.workspace_id,
                    source_video_id=source_video.id,
                    segment_index=int(first.segment_index),
                    version=max(int(max_version or 0) + 1, int(first.version or 1) + 1),
                    start_ms=int(first.start_ms),
                    end_ms=int(members[-1].end_ms),
                    text=merge_translation_premerge_text([member.text for member in members]),
                    normalized_text=merge_translation_premerge_text(
                        [member.normalized_text or member.text for member in members]
                    ),
                    language_code=first.language_code or "zh",
                    status=(
                        TranscriptSegmentStatus.APPROVED
                        if all(member.status == TranscriptSegmentStatus.APPROVED for member in members)
                        else TranscriptSegmentStatus.NEEDS_REVIEW
                    ),
                    confidence=min(confidences) if confidences else None,
                    speaker_label=speakers[0] if speakers else None,
                    difficulty_flags_json={"flags": flags},
                    analysis_version=first.analysis_version,
                    created_by_job_id=job_id,
                    is_current=True,
                    metadata_json={
                        **dict(first.metadata_json or {}),
                        "translation_premerge": {
                            **lineage,
                            "lineage_sha256": lineage_hash,
                            "member_versions": [int(member.version or 1) for member in members],
                            "member_confidences": [member.confidence for member in members],
                        },
                    },
                )
                self.db.add(row)
                materialized.append(row)
                lineage_hashes.append(lineage_hash)
            self.db.flush()
            persisted_summary = {
                **summary,
                "materialized": True,
                "lineage_sha256": lineage_hashes,
            }
            source_meta = dict(source_video.metadata_json or {})
            source_meta["translation_temporal_premerge"] = persisted_summary
            source_video.metadata_json = source_meta
            self.db.commit()
            refreshed = self.get_transcript_segments(source_video.id)
            if not refreshed:
                raise RuntimeError("translation pre-merge persisted no current transcript beats")
            return refreshed, {**persisted_summary, "output_beat_count": len(refreshed)}
        except Exception as exc:
            self.db.rollback()
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.PERSISTENCE_FAILED,
                f"Could not persist translation temporal pre-merge: {exc}",
            ) from exc

    def _cached_translation_result(
        self,
        source_video: SourceVideo,
        *,
        beats: list,
        fingerprint: str,
    ) -> AudioAnalysisResult | None:
        cache = dict((source_video.metadata_json or {}).get("translation_v3_cache") or {})
        if cache.get("fingerprint") != fingerprint or cache.get("recipe_version") != TRANSLATION_V3_RECIPE_VERSION:
            return None
        rows = list(
            self.db.scalars(
                select(TranslationSegment)
                .where(
                    TranslationSegment.source_video_id == source_video.id,
                    TranslationSegment.is_current.is_(True),
                )
                .order_by(TranslationSegment.segment_index.asc())
            )
        )
        if len(rows) != len(beats) or any(
            str((row.metadata_json or {}).get("translation_v3", {}).get("run_fingerprint") or "")
            != fingerprint
            for row in rows
        ):
            return None
        authority = dict((source_video.metadata_json or {}).get("translation_authority") or {})
        if authority:
            valid, _reason = validate_translation_authority(
                authority,
                source_video_id=source_video.id,
                transcript_rows=beats,
                translation_rows=rows,
            )
            if not valid:
                return None
        try:
            summary = self.get_summary(source_video.id)
        except Exception:
            summary = {}
        flags_summary = Counter(
            flag
            for row in rows
            for flag in list((row.quality_flags_json or {}).get("flags") or [])
        )
        contract = dict(cache.get("quality_contract") or {})
        return AudioAnalysisResult(
            source_video_id=source_video.id,
            analysis_version=str(cache.get("analysis_version") or beats[0].analysis_version or ""),
            transcript_count=len(beats),
            translation_count=sum(1 for row in rows if str(row.text or "").strip()),
            asset_count=int(summary.get("asset_count") or 1),
            flags_summary=dict(flags_summary),
            manifest=dict(summary.get("manifest") or {}),
            metrics={
                "cache_hit": True,
                "translation_recipe_version": TRANSLATION_V3_RECIPE_VERSION,
                "translation_fingerprint": fingerprint,
                "quality_contract": {**contract, "cache_hit": True},
            },
        )

    def _translation_checkpoint(self, job_id: UUID | None, *, fingerprint: str) -> dict[str, list[dict]]:
        if job_id is None:
            return {}
        job = self.db.get(Job, job_id)
        if not isinstance(job, Job):
            return {}
        payload = dict(job.metadata_json or {}).get("translation_v3_checkpoint") or {}
        if payload.get("fingerprint") != fingerprint:
            return {}
        blocks = payload.get("blocks") or {}
        return {
            str(block_id): list(rows)
            for block_id, rows in blocks.items()
            if isinstance(rows, list)
        }

    def _persist_translation_checkpoint(
        self,
        job_id: UUID | None,
        *,
        fingerprint: str,
        block_id: str,
        rows: list,
        block_number: int,
        block_total: int,
    ) -> None:
        if job_id is None:
            return
        job = self.db.get(Job, job_id)
        if not isinstance(job, Job):
            return
        metadata = dict(job.metadata_json or {})
        checkpoint = dict(metadata.get("translation_v3_checkpoint") or {})
        if checkpoint.get("fingerprint") not in {None, fingerprint}:
            return
        checkpoint["fingerprint"] = fingerprint
        checkpoint["recipe_version"] = TRANSLATION_V3_RECIPE_VERSION
        checkpoint["block_total"] = int(block_total)
        checkpoint["completed_block_number"] = int(block_number)
        checkpoint.setdefault("blocks", {})[str(block_id)] = [draft_to_checkpoint(row) for row in rows]
        metadata["translation_v3_checkpoint"] = checkpoint
        metadata["translation_fingerprint"] = fingerprint
        metadata["translation_recipe_version"] = TRANSLATION_V3_RECIPE_VERSION
        job.metadata_json = metadata
        self.db.commit()

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
        authority = dict(meta.get("audio_analysis_authority") or {})
        if authority:
            authority.update(
                {
                    "transcript_sha256": self._transcript_authority_sha256(beats),
                    "machine_approval_state": "operator_approved",
                    "operator_review_required": False,
                    "translation_ready": True,
                    "dialogue_quality_translation_ready": True,
                }
            )
            meta["audio_analysis_authority"] = authority
        source_video.metadata_json = meta
        self.db.commit()
        logger.info(
            "source_transcript_approved",
            extra={"source_video_id": str(source_video_id), "beat_count": len(beats)},
        )
        return {"source_video_id": str(source_video_id), "approved_segments": len(beats), "dialogue_phase": "source_approved"}

    @staticmethod
    def _require_translation_input_ready(
        source_video: SourceVideo,
        *,
        require_source_approved: bool,
    ) -> None:
        authority = dict(
            (source_video.metadata_json or {}).get("audio_analysis_authority") or {}
        )
        if not authority:
            return
        if authority.get("schema_version") != AUTHORITY_MANIFEST_SCHEMA_VERSION:
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Audio analysis authority manifest is unsupported or stale",
            )
        quality_ready = authority.get("dialogue_quality_translation_ready")
        if quality_ready is False:
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Audio dialogue quality contract is not translation-ready",
            )
        if bool(authority.get("translation_ready")):
            return
        if require_source_approved and bool(authority.get("operator_review_required")):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Audio transcript requires operator review before translation",
            )
        if not bool(authority.get("semantic_translation_ready")):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Audio semantic timeline is not translation-ready",
            )

    @staticmethod
    def _transcript_authority_payload(rows: list) -> list[dict]:
        return transcript_authority_payload(rows)

    @classmethod
    def _transcript_authority_sha256(cls, rows: list) -> str:
        return transcript_authority_sha256(rows)

    def _assert_current_transcript_authority(
        self,
        source_video: SourceVideo,
        rows: list,
    ) -> None:
        authority = dict((source_video.metadata_json or {}).get("audio_analysis_authority") or {})
        expected = str(authority.get("transcript_sha256") or "").strip()
        if not expected:
            return
        actual = self._transcript_authority_sha256(rows)
        if actual != expected:
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
                "Current transcript no longer matches the audio analysis authority; approve the edited transcript before translation",
            )

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

    def get_translation_quality_contract(self, source_video_id: UUID) -> dict:
        source_video = self._load_source_video(source_video_id)
        return dict((source_video.metadata_json or {}).get("translation_quality_contract") or {})

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
        audio_cache = dict(meta.get("audio_analysis_cache") or {})
        return {
            "source_video_id": str(source_video_id),
            "analysis_version": transcript_segments[0].analysis_version if transcript_segments else None,
            "transcript_count": len(transcript_segments),
            "translation_count": len(translation_segments),
            "asset_count": len([asset for asset in assets if asset.is_current]),
            "manifest": manifest,
            "has_speech": meta.get("has_speech"),
            "dialogue_phase": meta.get("dialogue_phase"),
            "audio_recipe_version": str(
                audio_cache.get("recipe_version") or AUDIO_ANALYSIS_RECIPE_VERSION
            ),
            "analysis_metrics": dict(meta.get("audio_analysis_metrics") or {}),
            "target_speech_authority": dict(
                meta.get("target_speech_authority") or {}
            ),
            "dialogue_quality_contract": dict(
                meta.get("dialogue_quality_contract") or {}
            ),
            "semantic_dialogue_segmentation": dict(
                meta.get("semantic_dialogue_segmentation") or {}
            ),
            "translation_recipe_version": str(
                meta.get("translation_recipe_version") or ""
            ) or None,
            "downstream_authority_invalidations": [
                dict(row)
                for row in list(meta.get("downstream_authority_invalidations") or [])[-5:]
                if isinstance(row, dict)
            ],
        }

    def _analysis_fingerprint(self, resolved_input: ResolvedAudioInput) -> str:
        payload = {
            "recipe_version": AUDIO_ANALYSIS_RECIPE_VERSION,
            "source_sha256": getattr(resolved_input, "source_checksum_sha256", None),
            "source_storage_key": (
                None
                if getattr(resolved_input, "source_checksum_sha256", None)
                else resolved_input.storage_key
            ),
            "canonicalized": bool(getattr(resolved_input, "canonicalized", False)),
            "vad": {
                "provider": str(getattr(self.vad_provider, "provider_name", "unknown")),
                "min_speech_seconds": getattr(self.vad_provider, "min_speech_seconds", None),
            },
            "separation": {
                "provider": str(getattr(self.separation_provider, "provider_name", "unknown")),
                "model": getattr(self.separation_provider, "model_name", None),
            },
            "stt": {
                "provider": str(getattr(self.stt_provider, "provider_name", "unknown")),
                "model": getattr(self.stt_provider, "model_name", None),
                "chunk_seconds": getattr(self.stt_provider, "chunk_seconds", None),
                "chunk_overlap_seconds": getattr(self.stt_provider, "chunk_overlap_seconds", None),
            },
            "asr_evidence": {
                "recipe_version": ASR_EVIDENCE_RECIPE_VERSION,
                "recovery_score_threshold": ASR_RECOVERY_SCORE_THRESHOLD,
            },
            "semantic_dialogue": {
                "recipe_version": SEMANTIC_DIALOGUE_RECIPE_VERSION,
                "policy": DEFAULT_SEMANTIC_SEGMENTATION_POLICY.to_dict(),
            },
            "dialogue_validation": {
                "recipe_version": DIALOGUE_VALIDATION_RECIPE_VERSION,
                "primary_asr_only": True,
                "selective_verification": True,
            },
            "target_speech": {
                "recipe_version": TARGET_SPEECH_RECIPE_VERSION,
                "provider": "local_dsp_silero_demucs_consensus",
                "interval_only_asr": True,
                "event_model_version": YAMNET_MODEL_VERSION,
                "event_model_sha256": YAMNET_MODEL_SHA256,
            },
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _analyze_target_speech(
        self,
        *,
        audio_storage_key: str,
        vad,
        duration_seconds: float,
    ) -> TargetSpeechAuthority:
        if not isinstance(self.storage, LocalStorageBackend):
            return unavailable_target_speech_authority(
                duration_seconds=duration_seconds,
                reason="non_local_storage_adapter",
            )
        path = to_windows_long_path(
            self.storage.resolve(audio_storage_key).absolute_path
        )
        try:
            return self.target_speech_analyzer(
                path,
                vad=vad,
                duration_seconds=duration_seconds,
            )
        except Exception as exc:
            logger.exception(
                "target_speech_authority_failed",
                extra={
                    "audio_storage_key": audio_storage_key,
                    "error": str(exc),
                },
            )
            return unavailable_target_speech_authority(
                duration_seconds=duration_seconds,
                reason=f"target_speech_analysis_failed:{type(exc).__name__}",
            )

    def _transcribe_target_intervals(
        self,
        *,
        audio_storage_key: str,
        source_caption: str | None,
        source_duration_seconds: float,
        authority: TargetSpeechAuthority,
    ) -> tuple[list, dict[str, Any]]:
        compact = materialize_compact_target_audio(
            self.storage,
            input_storage_key=audio_storage_key,
            intervals=authority.target_intervals,
            source_duration_seconds=source_duration_seconds,
        )
        if compact is not None:
            units = self.stt_provider.transcribe(
                compact.storage_key,
                source_caption=source_caption,
                duration_seconds=compact.compact_duration_seconds,
            )
            units = fit_funasr_units_to_duration(
                units,
                duration_seconds=compact.compact_duration_seconds,
            )
            units = remap_compact_transcription_units(units, audio=compact)
            return units, {
                "mode": "compact_target_intervals",
                **compact.to_dict(),
            }
        units = self.stt_provider.transcribe(
            audio_storage_key,
            source_caption=source_caption,
            duration_seconds=source_duration_seconds,
        )
        units = fit_funasr_units_to_duration(
            units,
            duration_seconds=source_duration_seconds,
        )
        return (
            filter_units_to_target_intervals(
                units,
                authority.target_intervals,
            ),
            {
                "mode": "full_audio_fail_closed_postfilter",
                "recipe_version": TARGET_SPEECH_RECIPE_VERSION,
            },
        )

    @staticmethod
    def _asr_quality_score(units) -> float:
        # Compatibility shim for callers/tests that still consume the scalar.
        # New decisions must use the persisted evidence object.
        return evaluate_asr_evidence(units).overall_score

    def _needs_separation_retry(
        self,
        units,
        *,
        evidence=None,
        mix_quality: dict | None = None,
        vad_speech_ratio: float | None = None,
    ) -> bool:
        evidence = evidence or evaluate_asr_evidence(units)
        if evidence.recovery_recommended:
            return True
        if bool((mix_quality or {}).get("separation_recommended")):
            return True
        # Very sparse measured speech over a busy mix is a common music/SFX
        # case where ASR confidence alone can be over-optimistic.
        if vad_speech_ratio is not None and 0.0 < float(vad_speech_ratio) < 0.08:
            return True
        return False

    def _cached_result(self, source_video: SourceVideo, fingerprint: str) -> AudioAnalysisResult | None:
        cache = dict((source_video.metadata_json or {}).get("audio_analysis_cache") or {})
        if cache.get("fingerprint") != fingerprint:
            return None
        authority = dict((source_video.metadata_json or {}).get("audio_analysis_authority") or {})
        if authority and str(authority.get("analysis_fingerprint") or "") != fingerprint:
            return None
        current_assets = list(
            self.db.scalars(
                select(MediaAsset).where(
                    MediaAsset.source_video_id == source_video.id,
                    MediaAsset.status == MediaAssetStatus.AVAILABLE,
                    MediaAsset.is_current.is_(True),
                    MediaAsset.asset_type.in_(
                        [
                            MediaAssetType.AUDIO_ANALYSIS_METADATA,
                            MediaAssetType.TRANSCRIPT_JSON,
                            MediaAssetType.TRANSLATION_DRAFT_JSON,
                        ]
                    ),
                )
            )
        )
        assets_by_type = {
            asset.asset_type: asset
            for asset in current_assets
            if isinstance(asset, MediaAsset)
            and isinstance(asset.storage_key, str)
            and self.storage.exists(asset.storage_key)
        }
        metadata_asset = assets_by_type.get(MediaAssetType.AUDIO_ANALYSIS_METADATA)
        transcript_asset = assets_by_type.get(MediaAssetType.TRANSCRIPT_JSON)
        if metadata_asset is None or transcript_asset is None:
            return None
        expected_version = str(cache.get("analysis_version") or "")
        if expected_version and authority and str(authority.get("analysis_version") or "") != expected_version:
            return None

        current_transcripts = self.get_transcript_segments(source_video.id)
        summary = self.get_summary(source_video.id)
        transcript_count = int(summary.get("transcript_count") or 0)
        if len(current_transcripts) != transcript_count:
            return None
        translation_count = int(summary.get("translation_count") or 0)
        if (
            translation_count > 0
            and MediaAssetType.TRANSLATION_DRAFT_JSON not in assets_by_type
        ):
            return None

        # New authority manifests are validated against both persisted JSON
        # nodes and the current transcript rows. Legacy caches remain readable,
        # but every newly written cache is fail-closed on a partial graph.
        if authority:
            try:
                metadata_payload = json.loads(
                    self.storage.read_bytes(metadata_asset.storage_key).decode("utf-8")
                )
                transcript_payload = json.loads(
                    self.storage.read_bytes(transcript_asset.storage_key).decode("utf-8")
                )
            except (
                OSError,
                TypeError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                AttributeError,
            ):
                return None
            if str(metadata_payload.get("analysis_version") or "") != expected_version:
                return None
            if str(metadata_payload.get("fingerprint") or "") != fingerprint:
                return None
            if str(transcript_payload.get("analysis_version") or "") != expected_version:
                return None
            if len(list(transcript_payload.get("segments") or [])) != transcript_count:
                return None
            embedded = dict(transcript_payload.get("audio_analysis_authority") or {})
            if embedded != authority:
                return None
            transcript_authority_payload = [
                {
                    "segment_index": int(row.segment_index),
                    "start_ms": int(row.start_ms),
                    "end_ms": int(row.end_ms),
                    "text": str(row.text or ""),
                    "normalized_text": str(row.normalized_text or ""),
                    "confidence": row.confidence,
                    "speaker_label": getattr(row, "speaker_label", None),
                    "flags": list((row.difficulty_flags_json or {}).get("flags") or []),
                }
                for row in current_transcripts
            ]
            transcript_sha256 = hashlib.sha256(
                json.dumps(
                    transcript_authority_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if str(authority.get("transcript_sha256") or "") != transcript_sha256:
                return None
        return AudioAnalysisResult(
            source_video_id=source_video.id,
            analysis_version=str(cache.get("analysis_version") or summary.get("analysis_version") or AUDIO_ANALYSIS_VERSION),
            transcript_count=int(summary.get("transcript_count") or 0),
            translation_count=translation_count,
            asset_count=int(summary.get("asset_count") or 0),
            flags_summary=dict(cache.get("flags_summary") or {}),
            manifest=dict(summary.get("manifest") or {}),
            metrics={
                **dict((source_video.metadata_json or {}).get("audio_analysis_metrics") or {}),
                "cache_hit": True,
            },
        )

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
        self._mark_previous_downstream_non_current(source_video_id)

    def _mark_previous_downstream_non_current(self, source_video_id: UUID) -> None:
        """Invalidate derived Translation/TTS rows while retaining their history."""
        self.db.execute(
            update(SubtitleSegment)
            .where(SubtitleSegment.source_video_id == source_video_id)
            .values(is_current=False)
        )
        self.db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type.in_(
                    [
                        MediaAssetType.TRANSLATION_DRAFT_JSON,
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
        self.db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == MediaAssetType.RENDER_DEBUG_JSON,
                MediaAsset.manifest_group.in_(
                    [
                        "tts_temporal_dialogue_graph",
                        "tts_temporal_calibration",
                        "tts_temporal_probe",
                        "tts_temporal_fit",
                        "tts_temporal_final",
                        "tts_temporal_performance",
                    ]
                ),
            )
            .values(is_current=False)
        )

    @staticmethod
    def _invalidate_downstream_authority(
        source_video: SourceVideo,
        *,
        new_analysis_version: str,
        job_id: UUID | None,
    ) -> None:
        """Drop only current Translation/TTS authority after a new ASR run.

        Immutable DB rows and media assets remain available for audit.  This
        source-level projection is rebuilt from the new transcript and must not
        retain counters, cache fingerprints or readiness flags from an older
        transcript authority.
        """

        metadata = dict(source_video.metadata_json or {})
        previous_analysis_version = str(
            dict(metadata.get("audio_analysis_cache") or {}).get("analysis_version")
            or ""
        ) or None
        invalidated_keys = [
            key
            for key in (
                "translation_preset",
                "translation_row_count",
                "translation_filled_count",
                "translation_count",
                "translation_gate_failed_count",
                "translation_recipe_version",
                "translation_quality_contract",
                "translation_v3_cache",
                "translation_temporal_premerge",
                "dialogue_translation_review",
                "tts_temporal",
            )
            if key in metadata
        ]
        for key in invalidated_keys:
            metadata.pop(key, None)

        history_raw = metadata.get("downstream_authority_invalidations") or []
        history = list(history_raw) if isinstance(history_raw, list) else []
        history.append(
            {
                "schema_version": "downstream_authority_invalidation_v1",
                "reason": "source_transcript_superseded",
                "previous_analysis_version": previous_analysis_version,
                "new_analysis_version": new_analysis_version,
                "job_id": str(job_id) if job_id else None,
                "invalidated_at": datetime.now(UTC).isoformat(),
                "invalidated_metadata_keys": invalidated_keys,
                "history_preserved": True,
            }
        )
        # Keep a bounded source projection; the immutable rows/assets are the
        # complete audit history.
        metadata["downstream_authority_invalidations"] = history[-20:]
        source_video.metadata_json = metadata

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

    def _persist_separation_assets(
        self,
        source_video: SourceVideo,
        resolved_input,
        separation: SourceSeparationResult,
        *,
        job_id: UUID | None,
    ) -> list[MediaAsset]:
        """Register Demucs outputs immediately as checksum-bound media assets."""
        if separation.fallback_used or not isinstance(self.storage, LocalStorageBackend):
            return []
        metadata = dict(separation.metadata or {})
        background_role = (
            "target_speech_preserved_background"
            if metadata.get("background_policy")
            == "original_outside_target_no_vocals_inside_target"
            else "demucs_no_vocals"
        )
        specs = (
            (MediaAssetType.AUDIO_VOCAL_STEM, metadata.get("vocal_storage_key"), "demucs_vocals"),
            (MediaAssetType.AUDIO_BACKGROUND_STEM, metadata.get("background_storage_key"), background_role),
        )
        rows: list[MediaAsset] = []
        for asset_type, raw_key, role in specs:
            key = str(raw_key or "").strip()
            if not key or not self.storage.exists(key):
                continue
            storage_meta = self.storage.metadata(key)
            if not storage_meta.exists or not storage_meta.checksum_sha256:
                continue
            existing = self.db.scalar(
                select(MediaAsset).where(
                    MediaAsset.workspace_id == source_video.workspace_id,
                    MediaAsset.storage_key == key,
                )
            )
            provenance = {
                "provider": str(getattr(self.separation_provider, "provider_name", "unknown")),
                "model": metadata.get("model") or getattr(self.separation_provider, "model_name", None),
                "role": role,
                "source_asset_id": str(resolved_input.input_asset_id),
                "source_asset_sha256": resolved_input.source_checksum_sha256,
                "analysis_recipe_version": AUDIO_ANALYSIS_RECIPE_VERSION,
            }
            if existing is not None:
                if existing.source_video_id != source_video.id:
                    raise ValueError("Separation storage key belongs to another source video")
                existing.asset_type = asset_type
                existing.status = MediaAssetStatus.AVAILABLE
                existing.is_current = True
                existing.created_by_job_id = job_id or existing.created_by_job_id
                existing.mime_type = "audio/wav"
                existing.size_bytes = storage_meta.size_bytes
                existing.checksum_sha256 = storage_meta.checksum_sha256
                existing.metadata_json = {**(existing.metadata_json or {}), **provenance}
                rows.append(existing)
                continue
            for old in self.db.scalars(
                select(MediaAsset).where(
                    MediaAsset.source_video_id == source_video.id,
                    MediaAsset.asset_type == asset_type,
                    MediaAsset.is_current.is_(True),
                )
            ):
                old.is_current = False
            max_version = self.db.scalar(
                select(func.max(MediaAsset.version)).where(
                    MediaAsset.source_video_id == source_video.id,
                    MediaAsset.asset_type == asset_type,
                )
            )
            asset = MediaAsset(
                workspace_id=source_video.workspace_id,
                source_video_id=source_video.id,
                asset_type=asset_type,
                status=MediaAssetStatus.AVAILABLE,
                version=int(max_version or 0) + 1,
                storage_provider=self.storage.provider_name,
                storage_key=key,
                logical_key=key,
                relative_path=storage_meta.relative_path,
                manifest_group="audio_separation",
                is_current=True,
                created_by_job_id=job_id,
                mime_type="audio/wav",
                size_bytes=storage_meta.size_bytes,
                checksum_sha256=storage_meta.checksum_sha256,
                metadata_json=provenance,
            )
            self.db.add(asset)
            self.db.flush()
            rows.append(asset)
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
        max_version = self.db.scalar(
            select(func.max(MediaAsset.version)).where(
                MediaAsset.source_video_id == source_video.id,
                MediaAsset.asset_type == asset_type,
            )
        )
        version = int(max_version or 0) + 1
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
