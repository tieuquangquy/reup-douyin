from __future__ import annotations

import json
import hashlib
import logging
import time
from dataclasses import replace
from collections import Counter
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from src.audio_pipeline.speech_budget import (
    DEFAULT_VI_UNITS_PER_SECOND,
    SpeechRateSample,
    assess_speech_budget,
    calibrate_units_per_second,
    count_spoken_units,
    extract_protected_tokens,
    speech_rate_samples_from_metadata,
    validate_protected_tokens,
)
from src.audio_pipeline.translation_authority import sha256_json
from src.core.settings import get_settings
from src.enums import JobStatus, JobType, MediaAssetStatus, MediaAssetType, SourceVideoStatus, TranscriptSegmentStatus
from src.models.artifacts import SubtitleSegment
from src.models.ingestion import SourceVideo
from src.models.jobs import Job
from src.models.media import MediaAsset
from src.services.job_service import JobService
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend
from src.storage.path_strategy import VideoStorageContext, asset_logical_key
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.provider_factory import (
    ConfiguredButUnavailableTtsProvider,
    build_default_tts_provider,
)
from src.tts_pipeline.providers import TtsProvider
from src.tts_pipeline.services.narration_assembler import (
    NarrationAssembler,
    normalize_wav_bytes,
    trim_wav_silence,
)
from src.tts_pipeline.services.audio_timing import (
    FfmpegWavTimingFitter,
    MAX_ATEMPO_SPEED,
    SOFT_ATEMPO_SPEED,
    plan_timing_adjustment,
    recommended_spoken_unit_limit,
)
from src.tts_pipeline.services.duration_planner import (
    DURATION_PLANNER_VERSION,
    plan_initial_speaking_rate,
)
from src.tts_pipeline.services.input_preflight import (
    build_tts_input_preflight,
    rank_preflight_candidates,
)
from src.tts_pipeline.services.profile_authority import (
    assert_manifest_tts_authority_active,
    bind_active_tts_profile_authority,
    resolve_active_tts_profile_authority,
)
from src.tts_pipeline.services.provider_audio_normalizer import (
    canonicalize_provider_audio,
)
from src.tts_pipeline.services.render_prep_manifest_builder import build_render_prep_manifest
from src.tts_pipeline.services.subtitle_builder import SubtitleBuilder, build_srt
from src.tts_pipeline.services.timing_fit import classify_timing_fit, timing_fit_flags
from src.tts_pipeline.services.translation_input_resolver import TranslationInputResolver
from src.tts_pipeline.services.tts_summary_clips import build_timing_fit_summary, extract_tts_clip_fits
from src.tts_pipeline.services.temporal_dialogue import build_temporal_dialogue_timeline
from src.tts_pipeline.services.speech_text import build_vietnamese_speech_text
from src.tts_pipeline.services.director import build_local_director_plan, build_voice_bible
from src.tts_pipeline.services.emotion_planner import (
    EMOTION_PLANNER_VERSION,
    enforce_emotion_policy,
    plan_emotions,
    planner_enabled,
)
from src.tts_pipeline.services.performance_chunker import build_performance_chunks, PERFORMANCE_CHUNKER_VERSION
from src.tts_pipeline.services.provider_adapter import compile_provider_instruction, PROVIDER_LOWERING_VERSION
from src.tts_pipeline.services.prosody_qa import assess_prosody_continuity, PROSODY_QA_VERSION
from src.tts_pipeline.services.prosody_audio_qa import analyze_prosody_audio
from src.tts_pipeline.services.emotion_acceptance import build_emotion_acceptance_report
from src.tts_pipeline.services.gemini_whole_video import (
    GEMINI_WHOLE_VIDEO_VERSION,
    boundary_pause_tag,
    build_gemini_narration_blocks,
    resolve_gemini_synthesis_strategy,
    select_whole_video_candidates,
)
from src.tts_pipeline.services.whole_video_alignment import (
    WHOLE_VIDEO_ALIGNMENT_VERSION,
    split_whole_video_wav,
)
from src.tts_pipeline.provider_capabilities import resolve_provider_capabilities
from src.tts_pipeline.services.waveform_qa import analyze_waveform, apply_edge_fades
from src.tts_pipeline.types import (
    TTS_PIPELINE_VERSION,
    RenderPrepResult,
    SubtitleDraftSegment,
    SynthesizedSegment,
    TimingFitStatus,
    ProsodySegment,
    TtsProviderInput,
    TtsProviderOutput,
    TtsRequest,
    VoiceConfig,
)

logger = logging.getLogger(__name__)

TTS_SEGMENT_CACHE_SCHEMA = "tts_segment_cache_v3"
TTS_ACOUSTIC_CACHE_SCHEMA = "tts_acoustic_cache_v2"
TTS_PROVIDER_BATCH_SIZE = 4
TTS_MAX_CANDIDATE_SYNTHESIS_PER_SEGMENT = 2
TTS_MAX_PROVIDER_SYNTHESIS_PER_SEGMENT = 3
TTS_DIRECTOR_SOURCE_CONTEXT_VERSION = "tts-director-source-context-v1"


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
        self.tts_provider = tts_provider or ConfiguredButUnavailableTtsProvider(
            "unbound",
            "Production TTS provider is not bound to the one setup currently On.",
        )
        self.subtitle_builder = SubtitleBuilder()
        self.narration_assembler = NarrationAssembler()
        self.timing_fitter = FfmpegWavTimingFitter()

    def _workspace_tts_config(
        self, workspace_id: UUID, runtime_authority: dict | None = None
    ):
        workspace_tts, verified = resolve_active_tts_profile_authority(
            self.db,
            workspace_id,
            runtime_authority,
        )
        self._runtime_tts_authority = verified
        self._workspace_tts = workspace_tts
        return workspace_tts

    def _provider_for_workspace(
        self, workspace_id: UUID, runtime_authority: dict | None = None
    ) -> TtsProvider:
        if self._tts_provider_override is not None:
            return self._tts_provider_override
        workspace_tts = self._workspace_tts_config(workspace_id, runtime_authority)
        return build_default_tts_provider(
            workspace_tts=workspace_tts,
            allow_fallback=False,
        )

    def _voice_config_for_request(self, request: TtsRequest, workspace_id: UUID) -> VoiceConfig:
        workspace_tts = self._workspace_tts_config(
            workspace_id, request.runtime_authority
        )
        # Production never falls back to client or ENV voice fields. The
        # active On setup is the only voice authority for every clip.
        voice_id = str(workspace_tts.voice_id or "").strip()
        language = str(workspace_tts.language_code or "vi").strip() or "vi"
        try:
            rate = float(workspace_tts.speaking_rate)
        except (TypeError, ValueError):
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED,
                "The active TTS setup has an invalid speaking rate.",
            )
        rate = max(0.5, min(2.0, rate))
        return VoiceConfig(voice_id=voice_id, language_code=language, speaking_rate=rate)

    def create_tts_job(self, request: TtsRequest, *, commit: bool = True):
        source_video = self._load_source_video(request.source_video_id)
        runtime_authority = bind_active_tts_profile_authority(
            self.db,
            source_video.workspace_id,
        )
        request = TtsRequest(
            source_video_id=request.source_video_id,
            voice_config=request.voice_config,
            force_refresh=request.force_refresh,
            runtime_authority=runtime_authority,
        )
        voice_config = self._voice_config_for_request(request, source_video.workspace_id)
        input_segments = TranslationInputResolver(self.db).resolve(source_video.id)
        translation_input_sha256 = _translation_input_sha256(input_segments)
        translation_authority_sha256 = _translation_authority_sha256(source_video)
        pronunciation_glossary = _pronunciation_glossary(
            getattr(self, "_workspace_tts", None)
        )
        timeline_duration_ms = int(
            round(float(getattr(source_video, "duration_seconds", None) or 0.0) * 1000.0)
        ) or max((segment.end_ms for segment in input_segments), default=0)
        preflight = build_tts_input_preflight(
            input_segments,
            source_video_id=source_video.id,
            timeline_duration_ms=timeline_duration_ms,
            translation_input_sha256=translation_input_sha256,
            translation_authority_sha256=translation_authority_sha256,
            voice_config=voice_config,
            voice_authority=runtime_authority,
            units_per_second=DEFAULT_VI_UNITS_PER_SECOND * float(voice_config.speaking_rate),
            pronunciation_glossary=pronunciation_glossary,
        )
        if not bool(preflight.get("admission_ready")):
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_INPUT_PREFLIGHT_BLOCKED,
                "TTS input preflight found blocked or review-required segments. Approve/fix the Translation Draft before synthesis.",
            )
        idempotency_key = (
            None
            if request.force_refresh
            else _tts_idempotency_key(
                source_video_id=source_video.id,
                translation_input_sha256=translation_input_sha256,
                voice_config=voice_config,
                runtime_authority=request.runtime_authority,
            )
        )
        job_service = JobService(self.db)
        active_job = self.db.scalar(
            select(Job)
            .where(
                Job.source_video_id == source_video.id,
                Job.job_type == JobType.SYNTHESIZE_TTS,
                Job.status.in_(
                    [
                        JobStatus.QUEUED,
                        JobStatus.RUNNING,
                        JobStatus.RETRYABLE,
                    ]
                ),
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        if active_job is not None:
            active_payload = dict(active_job.payload_json or {})
            active_metadata = dict(active_job.metadata_json or {})
            active_runtime = str(
                active_metadata.get("runtime_version")
                or dict(
                    active_payload.get("frontend_stage_runtime") or {}
                ).get("stage_version")
                or ""
            )
            if active_runtime and active_runtime != TTS_PIPELINE_VERSION:
                raise TtsPipelineError(
                    TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                    "An active TTS job is bound to stale runtime "
                    f"{active_runtime}; cancel it, then Generate TTS again with "
                    f"{TTS_PIPELINE_VERSION}.",
                )
            active_authority = dict(active_payload.get("runtime_authority") or {})
            if not _same_tts_authority(active_authority, runtime_authority):
                raise TtsPipelineError(
                    TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                    "A TTS job for this video is still active but belongs to another or legacy voice setup. Cancel/wait for that job, then run Generate TTS again; it will not be reused.",
                )
            if not _same_translation_snapshot(
                active_payload,
                translation_input_sha256=translation_input_sha256,
                translation_authority_sha256=translation_authority_sha256,
            ):
                raise TtsPipelineError(
                    TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                    "A TTS job for this video is still active but its Translation Draft snapshot is stale or legacy. Cancel/wait for that job, then run Generate TTS again.",
                )
            logger.info(
                "tts_job_active_source_hit",
                extra={"job_id": str(active_job.id), "source_video_id": str(source_video.id)},
            )
            return job_service.get_job(active_job.id)
        if idempotency_key is not None:
            existing = self.db.scalar(
                select(Job).where(
                    Job.workspace_id == source_video.workspace_id,
                    Job.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                existing_payload = dict(existing.payload_json or {})
                existing_metadata = dict(existing.metadata_json or {})
                existing_runtime = str(
                    existing_metadata.get("runtime_version")
                    or dict(
                        existing_payload.get("frontend_stage_runtime") or {}
                    ).get("stage_version")
                    or ""
                )
                if (
                    existing.status == JobStatus.FAILED
                    and bool(existing.retryable)
                    and existing_runtime == TTS_PIPELINE_VERSION
                ):
                    logger.info(
                        "tts_job_operator_retry",
                        extra={
                            "job_id": str(existing.id),
                            "source_video_id": str(source_video.id),
                        },
                    )
                    return job_service.retry_job(existing.id)
                if existing.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
                    # The unique idempotency key belongs to a terminal job that
                    # cannot be resumed. An explicit Generate action creates a
                    # fresh durable job rather than returning a dead one.
                    idempotency_key = None
                else:
                    logger.info(
                        "tts_job_idempotency_hit",
                        extra={"job_id": str(existing.id), "source_video_id": str(source_video.id)},
                    )
                    return job_service.get_job(existing.id)
        job = job_service.create_job(
            job_type=JobType.SYNTHESIZE_TTS,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "voice_config": voice_config.__dict__,
                "runtime_authority": dict(request.runtime_authority or {}) or None,
                "translation_input_sha256": translation_input_sha256,
                "translation_authority_sha256": translation_authority_sha256,
                "tts_input_preflight": preflight,
                "force_refresh": request.force_refresh,
            },
            idempotency_key=idempotency_key,
            commit=commit,
        )
        logger.info("tts_job_created", extra={"job_id": str(job.id), "source_video_id": str(source_video.id)})
        return job

    def run_pipeline(
        self,
        request: TtsRequest,
        *,
        job_id: UUID | None = None,
        on_progress: Callable[[str, int | None], None] | None = None,
    ) -> RenderPrepResult:
        pipeline_started_at = time.perf_counter()
        source_video = self._load_source_video(request.source_video_id)
        runtime_authority = request.runtime_authority or bind_active_tts_profile_authority(
            self.db,
            source_video.workspace_id,
        )
        self._runtime_tts_authority = dict(runtime_authority)
        voice_config = self._voice_config_for_request(
            replace(request, runtime_authority=runtime_authority),
            source_video.workspace_id,
        )
        request = TtsRequest(
            source_video_id=request.source_video_id,
            voice_config=voice_config,
            force_refresh=request.force_refresh,
            runtime_authority=runtime_authority,
            translation_input_sha256=request.translation_input_sha256,
            translation_authority_sha256=request.translation_authority_sha256,
        )
        context = self._storage_context(source_video)
        input_segments = TranslationInputResolver(self.db).resolve(source_video.id)
        _assert_translation_snapshot_current(
            request,
            source_video=source_video,
            input_segments=input_segments,
        )
        # Provider construction is deliberately after the immutable input
        # check so stale queued work cannot reach a paid/remote boundary.
        self.tts_provider = self._provider_for_workspace(
            source_video.workspace_id, runtime_authority
        )
        self._pronunciation_glossary = _pronunciation_glossary(
            getattr(self, "_workspace_tts", None)
        )
        speech_rate_calibration = self._speech_rate_calibration(
            source_video.workspace_id,
            request.voice_config,
        )
        timeline_duration_seconds = float(
            getattr(source_video, "duration_seconds", None)
            or (max((segment.end_ms for segment in input_segments), default=0) / 1000.0)
        )
        if timeline_duration_seconds <= 0:
            raise TtsPipelineError(
                TtsPipelineErrorCode.NARRATION_ASSEMBLY_FAILED,
                "Source video duration authority is required for full-duration narration",
            )
        timeline_segments, dialogue_graph = build_temporal_dialogue_timeline(
            input_segments,
            timeline_duration_ms=int(round(timeline_duration_seconds * 1000.0)),
            units_per_second=speech_rate_calibration.units_per_second,
        )
        # Build the provider-neutral performance plan once.  This is intentionally
        # local/deterministic so providers can still be called in bounded batches.
        workspace_tts = getattr(self, "_workspace_tts", None)
        tts_options = dict(getattr(workspace_tts, "options_json", None) or {})
        voice_bible = build_voice_bible(
            voice_config=request.voice_config,
            runtime_authority=runtime_authority,
            options=tts_options,
        )
        source_context = self._tts_director_source_context(source_video)
        provider_name = str(
            getattr(workspace_tts, "provider", "")
            or getattr(self.tts_provider, "provider_name", "")
        ).strip().lower()
        provider_capabilities = resolve_provider_capabilities(
            provider_name,
            model_id=str(
                getattr(workspace_tts, "model_id", "")
                or getattr(self.tts_provider, "model_id", "")
            ),
            options=tts_options,
        )
        emotion_config = dict(tts_options.get("emotion_planner") or {})
        emotion_enabled = planner_enabled(
            provider=provider_name,
            options=tts_options,
            capabilities=provider_capabilities.to_dict(),
        )
        try:
            emotion_min_confidence = max(
                0.5,
                min(0.95, float(emotion_config.get("min_confidence", 0.70))),
            )
        except (TypeError, ValueError):
            emotion_min_confidence = 0.70
        emotion_decisions = (
            plan_emotions(
                timeline_segments,
                min_confidence=emotion_min_confidence,
            )
            if emotion_enabled
            else {}
        )
        emotion_policy_report = None
        if emotion_enabled:
            try:
                max_strong_emotion_ratio = max(
                    0.05,
                    min(
                        1.0,
                        float(emotion_config.get("max_strong_emotion_ratio", 0.20)),
                    ),
                )
            except (TypeError, ValueError):
                max_strong_emotion_ratio = 0.20
            emotion_decisions, emotion_policy_report = enforce_emotion_policy(
                emotion_decisions,
                timeline_segments,
                min_confidence=emotion_min_confidence,
                allow_excited=bool(emotion_config.get("allow_excited", True)),
                max_strong_emotion_ratio=max_strong_emotion_ratio,
            )
        director_plan = build_local_director_plan(
            timeline_segments,
            source_video_id=source_video.id,
            voice_bible=voice_bible,
            source_context=source_context,
            emotion_decisions=emotion_decisions,
            emotion_enabled=emotion_enabled,
        )
        performance_chunks, performance_chunk_report = build_performance_chunks(
            timeline_segments,
            director_plan=director_plan,
        )
        prosody_qa = assess_prosody_continuity(director_plan.prosody_segments)
        prosody_by_segment_id = {
            str(row.translation_segment_id): row
            for row in director_plan.prosody_segments
        }
        chunk_by_segment_id = {
            str(member_id): chunk
            for chunk in performance_chunks
            for member_id in chunk.member_translation_segment_ids
        }
        director_payload = director_plan.to_dict()
        self._tts_director_plan_sha256 = str(director_payload.get("plan_sha256") or "")
        self._tts_voice_bible_sha256 = str(director_payload.get("voice_bible_sha256") or "")
        self._tts_provider_capabilities = provider_capabilities
        self._tts_director_plan = director_plan
        self._tts_emotion_decisions = emotion_decisions
        self._tts_emotion_planner_enabled = emotion_enabled
        self._tts_emotion_planner_version = EMOTION_PLANNER_VERSION if emotion_enabled else None
        self._tts_emotion_policy_report = emotion_policy_report
        self._tts_chunk_by_segment_id = {
            key: value.chunk_id for key, value in chunk_by_segment_id.items()
        }
        self._tts_sample_context = str(tts_options.get("sample_context") or "").strip() or None
        expressive_options = tts_options.get("expressive_tts")
        expressive_options = expressive_options if isinstance(expressive_options, dict) else {}
        self._tts_expressive_mode = str(
            expressive_options.get("mode")
            or tts_options.get("expressive_mode")
            or ("required" if str(getattr(workspace_tts, "provider", "")).lower() == "google" else "best_effort")
        ).strip().lower()
        if self._tts_expressive_mode not in {"off", "best_effort", "required"}:
            self._tts_expressive_mode = "best_effort"
        self._tts_synthesis_strategy = resolve_gemini_synthesis_strategy(
            provider=provider_name,
            expressive_options=expressive_options,
        )
        try:
            configured_max_tempo = float(expressive_options.get("max_tempo_correction", 1.08))
        except (TypeError, ValueError):
            configured_max_tempo = 1.08
        self._tts_max_expressive_atempo = max(
            1.03,
            min(
                float(MAX_ATEMPO_SPEED),
                configured_max_tempo,
            ),
        ) if self._tts_expressive_mode == "required" else float(MAX_ATEMPO_SPEED)
        try:
            self._tts_review_atempo_limit = max(
                1.03,
                min(
                    float(MAX_ATEMPO_SPEED),
                    float(expressive_options.get("max_review_atempo", 1.10)),
                ),
            )
        except (TypeError, ValueError):
            self._tts_review_atempo_limit = 1.10
        self._tts_director_version = director_plan.director_version
        self._tts_performance_chunker_version = PERFORMANCE_CHUNKER_VERSION
        prosody_degraded_features = sorted(
            {
                feature
                for prosody in director_plan.prosody_segments
                for feature in compile_provider_instruction(
                    "",
                    voice_bible=voice_bible,
                    prosody=prosody,
                    capabilities=provider_capabilities,
                    sample_context=self._tts_sample_context,
                ).degraded_features
            }
        )
        logger.info(
            "tts_director_plan_built",
            extra={
                "source_video_id": str(source_video.id),
                "prosody_segments": len(director_plan.prosody_segments),
                "performance_chunks": len(performance_chunks),
                "provider": provider_capabilities.provider,
                "expressive": provider_capabilities.expressive,
            },
        )
        if on_progress is not None:
            on_progress("repair_dialogue_timeline", 1)
        logger.info(
            "tts_input_resolved",
            extra={
                "source_video_id": str(source_video.id),
                "segments": len(input_segments),
                "dialogue_groups": len(timeline_segments),
            },
        )

        subtitle_version = self._next_subtitle_version(source_video.id)
        try:
            self._mark_previous_outputs_non_current(source_video.id)
            synthesized: list[SynthesizedSegment] = []
            assets: list[MediaAsset] = []
            warnings: list[str] = []
            if not prosody_qa["passed"]:
                warnings.append("tts_prosody_state_continuity_review_recommended")
            duration_gate_statuses: list[str] = []
            probe_timeline: list[dict] = []
            fit_decisions: list[dict] = []
            performance: dict[str, object] = {
                "schema_version": "tts_runtime_performance_v1",
                "pipeline_version": TTS_PIPELINE_VERSION,
                "fitted_cache_hit_count": 0,
                "acoustic_cache_hit_count": 0,
                "provider_synthesis_clip_count": 0,
                "provider_synthesis_call_count": 0,
                "provider_batch_call_count": 0,
                "selective_correction_count": 0,
                "provider_elapsed_ms": 0,
                "provider_audio_normalization_elapsed_ms": 0,
                "local_fit_qa_elapsed_ms": 0,
                "whole_video_block_fit_count": 0,
                "whole_video_block_refit_count": 0,
                "whole_video_repair_batch_count": 0,
                "whole_video_repaired_segment_count": 0,
                "whole_video_gap_borrow_count": 0,
                "whole_video_gap_borrowed_ms": 0,
                "max_provider_synthesis_per_segment": TTS_MAX_PROVIDER_SYNTHESIS_PER_SEGMENT,
                "max_expressive_atempo": float(self._tts_max_expressive_atempo),
                "synthesis_strategy": self._tts_synthesis_strategy,
                "whole_video_version": (
                    GEMINI_WHOLE_VIDEO_VERSION
                    if self._tts_synthesis_strategy in {"whole_video", "auto_blocks"}
                    else None
                ),
            }
            subtitle_input_segments = list(timeline_segments)
            total = max(1, len(timeline_segments))
            prefetched_probes: dict[str, tuple[TranslationInputSegment, object]] = {}
            provider_batch_size = max(
                1,
                min(
                    TTS_PROVIDER_BATCH_SIZE,
                    int(getattr(self.tts_provider, "preferred_batch_size", 1) or 1),
                ),
            )
            batch_method = (
                getattr(self.tts_provider, "synthesize_batch", None)
                if provider_batch_size > 1
                else None
            )

            warmup = (
                getattr(self.tts_provider, "warmup", None)
                if callable(getattr(type(self.tts_provider), "warmup", None))
                else None
            )
            if callable(warmup):
                if on_progress is not None:
                    on_progress("warm_tts_engine", 2)
                warm_started_at = time.perf_counter()
                warm_metadata = warmup()
                performance["warmup_elapsed_ms"] = int(
                    round((time.perf_counter() - warm_started_at) * 1000.0)
                )
                performance["warmup"] = dict(warm_metadata or {})

            def _candidate_runtime(text: str, budget_seconds: float):
                speech = build_vietnamese_speech_text(
                    text,
                    pronunciation_glossary=self._pronunciation_glossary,
                )
                plan = plan_initial_speaking_rate(
                    speech.speech_text,
                    slot_seconds=budget_seconds,
                    units_per_second=speech_rate_calibration.units_per_second,
                    base_speaking_rate=request.voice_config.speaking_rate,
                )
                voice = replace(
                    request.voice_config,
                    speaking_rate=plan.speaking_rate,
                )
                return speech, plan, voice

            def _provider_input(
                *,
                speech_text: str,
                voice: VoiceConfig,
                budget_seconds: float,
                segment: TranslationInputSegment,
            ) -> TtsProviderInput:
                """Compile one neutral prosody segment for the active provider.

                The display/translation text is never changed here.  Only the
                provider request receives tags, direction, SSML, or context that
                its declared capability matrix explicitly supports.
                """
                prosody = prosody_by_segment_id.get(str(segment.translation_segment_id))
                chunk = chunk_by_segment_id.get(str(segment.translation_segment_id))
                if prosody is None:
                    # Legacy/edge-case rows remain synthesizable with a neutral
                    # state; this keeps old Translation Drafts backwards-safe.
                    prosody = ProsodySegment(
                        translation_segment_id=segment.translation_segment_id,
                        segment_index=segment.segment_index,
                        start_ms=segment.start_ms,
                        end_ms=segment.end_ms,
                    )
                instruction = compile_provider_instruction(
                    speech_text,
                    voice_bible=voice_bible,
                    prosody=prosody,
                    capabilities=provider_capabilities,
                    sample_context=self._tts_sample_context,
                    base_speaking_rate=voice.speaking_rate,
                )
                requested_features = tuple(
                    feature
                    for feature, requested in (
                        ("emotion", prosody.emotion != "neutral"),
                        ("pace", abs(float(prosody.pace) - 1.0) >= 0.01),
                        ("pause", bool(prosody.pause_before_ms or prosody.pause_after_ms)),
                        ("emphasis", bool(prosody.emphasis)),
                    )
                    if requested
                )
                if self._tts_expressive_mode == "off":
                    neutral_prosody = replace(
                        prosody,
                        emotion="neutral",
                        intensity=0.4,
                        pace=1.0,
                        pause_before_ms=0,
                        pause_after_ms=0,
                        emphasis=(),
                        audio_tags=(),
                    )
                    instruction = compile_provider_instruction(
                        speech_text,
                        voice_bible=voice_bible,
                        prosody=neutral_prosody,
                        capabilities=provider_capabilities,
                        base_speaking_rate=voice.speaking_rate,
                    )
                elif (
                    self._tts_expressive_mode == "required"
                    and requested_features
                    and any(
                        feature in {"emotion", "pause", "emphasis"}
                        for feature in requested_features
                    )
                    and instruction.degraded_features
                ):
                    raise TtsPipelineError(
                        TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                        "Expressive TTS is required but the active provider cannot apply: "
                        + ", ".join(instruction.degraded_features),
                    )
                provider_text = (
                    instruction.rendered_text
                    if instruction.audio_tags
                    else instruction.speech_text
                )
                return TtsProviderInput(
                    text=provider_text,
                    language_code=voice.language_code,
                    voice_config=voice,
                    target_duration_seconds=budget_seconds,
                    voice_direction=instruction.voice_direction,
                    sample_context=instruction.sample_context,
                    audio_tags=instruction.audio_tags,
                    prosody_state=instruction.prosody_state,
                    performance_chunk_id=chunk.chunk_id if chunk else None,
                    ssml_text=instruction.ssml_text,
                    expressive_mode=self._tts_expressive_mode,
                    requested_features=requested_features,
                )

            def _director_metadata(segment: TranslationInputSegment) -> dict:
                prosody = prosody_by_segment_id.get(str(segment.translation_segment_id))
                chunk = chunk_by_segment_id.get(str(segment.translation_segment_id))
                emotion_decision = emotion_decisions.get(int(segment.segment_index))
                compiled = (
                    compile_provider_instruction(
                        "",
                        voice_bible=voice_bible,
                        prosody=prosody,
                        capabilities=provider_capabilities,
                        sample_context=self._tts_sample_context,
                    )
                    if prosody is not None
                    else None
                )
                return {
                    "director_version": director_plan.director_version,
                    "director_plan_sha256": self._tts_director_plan_sha256,
                    "voice_bible_sha256": self._tts_voice_bible_sha256,
                    "provider_capabilities": provider_capabilities.to_dict(),
                    "prosody_degraded_features": prosody_degraded_features,
                    "expressive_mode": self._tts_expressive_mode,
                    "provider_lowering_version": PROVIDER_LOWERING_VERSION,
                    "applied_features": list(compiled.applied_features if compiled else ()),
                    "degraded_features": list(compiled.degraded_features if compiled else ()),
                    "performance_chunker_version": PERFORMANCE_CHUNKER_VERSION,
                    "performance_chunk_id": chunk.chunk_id if chunk else None,
                    "prosody": prosody.to_dict() if prosody else None,
                    "emotion_planner": {
                        "enabled": bool(emotion_enabled),
                        "version": EMOTION_PLANNER_VERSION if emotion_enabled else None,
                        "provider_scope": "google_gemini",
                        "decision": (
                            emotion_decision.to_dict()
                            if emotion_decision is not None
                            else None
                        ),
                        "policy_report": (
                            emotion_policy_report.to_dict()
                            if emotion_policy_report is not None
                            else None
                        ),
                        "skipped_reason": (
                            None if emotion_enabled else "provider_or_profile_not_enabled"
                        ),
                    },
                }

            def _correction_voice(initial_voice: VoiceConfig) -> VoiceConfig:
                faster_rate = min(
                    2.0,
                    max(
                        float(initial_voice.speaking_rate) * 1.08,
                        float(request.voice_config.speaking_rate) * 1.12,
                    ),
                )
                return replace(request.voice_config, speaking_rate=faster_rate)

            def _canonicalize_provider_output(
                output: TtsProviderOutput,
            ) -> TtsProviderOutput:
                verified_metadata = self._verified_provider_metadata(
                    output.provider_metadata,
                    output.warnings,
                )
                normalization_started_at = time.perf_counter()
                audio_bytes, duration_seconds, normalization = (
                    canonicalize_provider_audio(
                        output.audio_bytes,
                        mime_type=output.mime_type,
                        file_extension=output.file_extension,
                    )
                )
                performance["provider_audio_normalization_elapsed_ms"] = int(
                    performance["provider_audio_normalization_elapsed_ms"]
                ) + int(
                    round(
                        (time.perf_counter() - normalization_started_at) * 1000.0
                    )
                )
                return replace(
                    output,
                    audio_bytes=audio_bytes,
                    duration_seconds=duration_seconds,
                    mime_type="audio/wav",
                    file_extension="wav",
                    provider_metadata={
                        **verified_metadata,
                        "audio_normalization": normalization,
                    },
                )

            def _synthesize_provider(provider_input: TtsProviderInput):
                started_at = time.perf_counter()
                try:
                    output = self.tts_provider.synthesize(provider_input)
                finally:
                    performance["provider_synthesis_call_count"] = int(
                        performance["provider_synthesis_call_count"]
                    ) + 1
                    performance["provider_synthesis_clip_count"] = int(
                        performance["provider_synthesis_clip_count"]
                    ) + 1
                    performance["provider_elapsed_ms"] = int(
                        performance["provider_elapsed_ms"]
                    ) + int(round((time.perf_counter() - started_at) * 1000.0))
                internal_calls = int(
                    dict(output.provider_metadata or {}).get("provider_http_call_count") or 1
                )
                if internal_calls > 1:
                    performance["provider_synthesis_call_count"] = int(
                        performance["provider_synthesis_call_count"]
                    ) + (internal_calls - 1)
                    performance["provider_synthesis_clip_count"] = int(
                        performance["provider_synthesis_clip_count"]
                    ) + (internal_calls - 1)
                return _canonicalize_provider_output(output)

            def _prefetch_batch(start_index: int) -> None:
                """Prefetch only the next bounded batch so progress stays live."""

                if not callable(batch_method):
                    return
                batch_rows: list[tuple[TranslationInputSegment, str, TtsProviderInput]] = []
                for row in timeline_segments[start_index:]:
                    row_key = str(row.translation_segment_id)
                    if row_key in prefetched_probes:
                        continue
                    first_candidate = _rank_tts_candidates(
                        row,
                        row.duration_budget_ms / 1000.0,
                        speech_rate_calibration.units_per_second,
                        pronunciation_glossary=self._pronunciation_glossary,
                    )[0]
                    first_segment = replace(row, translated_text=first_candidate)
                    speech, _, effective_voice = _candidate_runtime(
                        first_candidate,
                        row.duration_budget_ms / 1000.0,
                    )
                    fitted_key = self._segment_cache_key(
                        first_segment,
                        voice_config=effective_voice,
                        runtime_authority=request.runtime_authority,
                    )
                    if not request.force_refresh and self._load_segment_cache(
                        source_video,
                        first_segment,
                        cache_key=fitted_key,
                    ) is not None:
                        continue
                    acoustic_key = self._acoustic_cache_key(
                        speech.speech_text,
                        voice_config=effective_voice,
                        runtime_authority=request.runtime_authority,
                        segment=first_segment,
                    )
                    cached_acoustic = (
                        None
                        if request.force_refresh
                        else self._load_acoustic_cache(
                            source_video,
                            cache_key=acoustic_key,
                        )
                    )
                    if cached_acoustic is not None:
                        prefetched_probes[row_key] = (
                            first_segment,
                            cached_acoustic,
                        )
                        continue
                    batch_rows.append(
                        (
                            row,
                            first_candidate,
                            _provider_input(
                                speech_text=speech.speech_text,
                                voice=effective_voice,
                                budget_seconds=row.duration_budget_ms / 1000.0,
                                segment=first_segment,
                            ),
                        )
                    )
                    if len(batch_rows) >= provider_batch_size:
                        break
                if not batch_rows:
                    return
                try:
                    batch_started_at = time.perf_counter()
                    outputs = list(batch_method([item[2] for item in batch_rows]))
                    performance["provider_batch_call_count"] = int(
                        performance["provider_batch_call_count"]
                    ) + 1
                    performance["provider_synthesis_call_count"] = int(
                        performance["provider_synthesis_call_count"]
                    ) + 1
                    performance["provider_synthesis_clip_count"] = int(
                        performance["provider_synthesis_clip_count"]
                    ) + len(batch_rows)
                    performance["provider_elapsed_ms"] = int(
                        performance["provider_elapsed_ms"]
                    ) + int(round((time.perf_counter() - batch_started_at) * 1000.0))
                except Exception as exc:
                    logger.warning(
                        "tts_batch_probe_failed_fallback_segmentwise",
                        extra={
                            "source_video_id": str(source_video.id),
                            "error_type": type(exc).__name__,
                        },
                    )
                    return
                if len(outputs) != len(batch_rows):
                    logger.warning(
                        "tts_batch_probe_count_mismatch_fallback_segmentwise",
                        extra={"expected": len(batch_rows), "actual": len(outputs)},
                    )
                    return
                for (row, candidate, _), output in zip(batch_rows, outputs, strict=True):
                    prefetched_probes[str(row.translation_segment_id)] = (
                        replace(row, translated_text=candidate),
                        _canonicalize_provider_output(output),
                    )

            whole_video_strategy = self._tts_synthesis_strategy in {
                "whole_video",
                "auto_blocks",
            }
            if whole_video_strategy:
                try:
                    compact_trigger_ratio = float(
                        expressive_options.get("compact_trigger_ratio", 0.88)
                    )
                except (TypeError, ValueError):
                    compact_trigger_ratio = 0.88
                subtitle_input_segments = select_whole_video_candidates(
                    timeline_segments,
                    units_per_second=speech_rate_calibration.units_per_second,
                    pronunciation_glossary=self._pronunciation_glossary,
                    compact_trigger_ratio=compact_trigger_ratio,
                )
                try:
                    max_whole_video_seconds = float(
                        expressive_options.get("max_whole_video_seconds", 180.0)
                    )
                except (TypeError, ValueError):
                    max_whole_video_seconds = 180.0
                try:
                    max_block_seconds = float(
                        expressive_options.get("max_block_seconds", 45.0)
                    )
                except (TypeError, ValueError):
                    max_block_seconds = 45.0
                try:
                    max_request_chars = int(
                        expressive_options.get("max_request_chars", 6000)
                    )
                except (TypeError, ValueError):
                    max_request_chars = 6000
                narration_blocks = build_gemini_narration_blocks(
                    subtitle_input_segments,
                    strategy=self._tts_synthesis_strategy,
                    max_whole_video_seconds=max_whole_video_seconds,
                    max_block_seconds=max_block_seconds,
                    max_request_chars=max_request_chars,
                )
                performance["narration_block_count"] = len(narration_blocks)
                performance["single_request_video"] = len(narration_blocks) == 1
                logger.info(
                    "tts_gemini_whole_video_plan",
                    extra={
                        "source_video_id": str(source_video.id),
                        "strategy": self._tts_synthesis_strategy,
                        "block_count": len(narration_blocks),
                        "translation_segment_count": len(subtitle_input_segments),
                    },
                )
                for block in narration_blocks:
                    if on_progress is not None:
                        on_progress(
                            f"synthesize_narration_block|{block.block_index + 1}|{len(narration_blocks)}",
                            min(
                                90,
                                5
                                + int(
                                    (block.block_index / max(1, len(narration_blocks)))
                                    * 82
                                ),
                            ),
                        )
                    provider_parts: list[str] = []
                    block_inputs: list[TtsProviderInput] = []
                    block_plain_texts: list[str] = []
                    for part_index, part in enumerate(block.segments):
                        speech, _, effective_voice = _candidate_runtime(
                            part.translated_text,
                            part.duration_budget_ms / 1000.0,
                        )
                        part_input = _provider_input(
                            speech_text=speech.speech_text,
                            voice=effective_voice,
                            budget_seconds=part.duration_budget_ms / 1000.0,
                            segment=part,
                        )
                        block_inputs.append(part_input)
                        block_plain_texts.append(speech.speech_text)
                        provider_parts.append(part_input.text)
                        if part_index < len(block.segments) - 1:
                            next_part = block.segments[part_index + 1]
                            pause_tag = boundary_pause_tag(next_part.start_ms - part.end_ms)
                            if pause_tag:
                                provider_parts.append(pause_tag)
                    first = block.segments[0]
                    last = block.segments[-1]
                    member_translation_ids = tuple(
                        member_id
                        for row in block.segments
                        for member_id in (
                            row.member_translation_segment_ids
                            or (row.translation_segment_id,)
                        )
                    )
                    member_transcript_ids = tuple(
                        member_id
                        for row in block.segments
                        for member_id in (
                            row.member_transcript_segment_ids
                            or (row.transcript_segment_id,)
                        )
                    )
                    member_indices = tuple(
                        member_index
                        for row in block.segments
                        for member_index in (
                            row.member_segment_indices or (row.segment_index,)
                        )
                    )
                    aggregate_segment = replace(
                        first,
                        end_ms=last.end_ms,
                        translated_text=" ".join(
                            row.translated_text for row in block.segments
                        ),
                        duration_budget_ms=max(1, last.end_ms - first.start_ms),
                        source_text=" ".join(
                            row.source_text for row in block.segments if row.source_text
                        ),
                        member_translation_segment_ids=member_translation_ids,
                        member_transcript_segment_ids=member_transcript_ids,
                        member_segment_indices=member_indices,
                        candidate_texts=(),
                        repair_actions=tuple(
                            dict.fromkeys(
                                action
                                for row in block.segments
                                for action in (
                                    *row.repair_actions,
                                    "gemini_whole_video_block",
                                )
                            )
                        ),
                    )
                    provider_text = "\n\n".join(provider_parts)
                    requested_features = tuple(
                        dict.fromkeys(
                            feature
                            for item in block_inputs
                            for feature in item.requested_features
                        )
                    )
                    audio_tags = tuple(
                        dict.fromkeys(
                            tag for item in block_inputs for tag in item.audio_tags
                        )
                    )
                    direction = (
                        "Use exactly one narrator identity throughout this entire video. "
                        "Read only the Vietnamese transcript, never read bracketed Audio Tags aloud. "
                        "Apply each local emotion and pause tag naturally while preserving the same "
                        "voice timbre, age, accent, microphone character and persona. "
                        f"Complete the block naturally within {block.duration_seconds:.2f} seconds. "
                        "Do not add, omit, repeat or paraphrase any words. "
                        + str(block_inputs[0].voice_direction or "")
                    ).strip()
                    whole_input = TtsProviderInput(
                        text=provider_text,
                        language_code=request.voice_config.language_code,
                        voice_config=request.voice_config,
                        target_duration_seconds=block.duration_seconds,
                        voice_direction=direction,
                        sample_context=self._tts_sample_context,
                        audio_tags=audio_tags,
                        prosody_state=block_inputs[0].prosody_state,
                        performance_chunk_id=f"whole-video-block-{block.block_index + 1}",
                        expressive_mode="required",
                        requested_features=requested_features,
                    )
                    acoustic_cache_key = self._acoustic_cache_key(
                        provider_text,
                        voice_config=request.voice_config,
                        runtime_authority=request.runtime_authority,
                        segment=aggregate_segment,
                    )
                    provider_output = (
                        None
                        if request.force_refresh
                        else self._load_acoustic_cache(
                            source_video,
                            cache_key=acoustic_cache_key,
                        )
                    )
                    synthesis_source = "acoustic_cache_hit"
                    if provider_output is None:
                        synthesis_source = "provider_synthesis"
                        provider_output = _synthesize_provider(whole_input)
                        trimmed_audio, trimmed_duration, trim_metadata = trim_wav_silence(
                            provider_output.audio_bytes
                        )
                        provider_output = replace(
                            provider_output,
                            audio_bytes=trimmed_audio,
                            duration_seconds=trimmed_duration,
                            provider_metadata={
                                **dict(provider_output.provider_metadata or {}),
                                "silence_trim": trim_metadata,
                                "acoustic_cache": {
                                    "status": "miss_written",
                                    "cache_key": acoustic_cache_key,
                                },
                            },
                        )
                        provider_output = replace(
                            provider_output,
                            provider_metadata=self._verified_provider_metadata(
                                provider_output.provider_metadata,
                                provider_output.warnings,
                            ),
                        )
                        try:
                            self._write_acoustic_cache(
                                source_video,
                                provider_output,
                                cache_key=acoustic_cache_key,
                            )
                        except Exception as exc:
                            logger.warning(
                                "tts_whole_video_cache_write_failed",
                                extra={
                                    "source_video_id": str(source_video.id),
                                    "block_index": block.block_index,
                                    "error_type": type(exc).__name__,
                                },
                            )
                    else:
                        performance["acoustic_cache_hit_count"] = int(
                            performance["acoustic_cache_hit_count"]
                        ) + 1
                        provider_output = replace(
                            provider_output,
                            provider_metadata=self._verified_provider_metadata(
                                provider_output.provider_metadata,
                                provider_output.warnings,
                            ),
                        )
                    block_adjustment = plan_timing_adjustment(
                        float(provider_output.duration_seconds),
                        block.duration_seconds,
                        max_atempo_speed=self._tts_max_expressive_atempo,
                    )
                    if block_adjustment.action == "block":
                        raise TtsPipelineError(
                            TtsPipelineErrorCode.TIMING_FIT_BLOCKED,
                            "Whole-video Gemini narration cannot fit safely: "
                            f"block_index={block.block_index} "
                            f"ratio={block_adjustment.ratio:.3f} "
                            f"segments={len(block.segments)} "
                            f"reason={block_adjustment.blocked_reason}",
                        )
                    block_fit_started_at = time.perf_counter()
                    alignment_audio, block_adjustment_metadata = self.timing_fitter.fit(
                        provider_output.audio_bytes,
                        block_adjustment,
                    )
                    alignment_audio, alignment_duration = normalize_wav_bytes(
                        alignment_audio
                    )
                    performance["local_fit_qa_elapsed_ms"] = int(
                        performance["local_fit_qa_elapsed_ms"]
                    ) + int(round((time.perf_counter() - block_fit_started_at) * 1000.0))
                    if block_adjustment.action == "atempo":
                        performance["whole_video_block_fit_count"] = int(
                            performance["whole_video_block_fit_count"]
                        ) + 1
                    aligned_slices = split_whole_video_wav(
                        alignment_audio,
                        block.segments,
                    )
                    peak_effective_ratio = 0.0
                    for diagnostic_index, diagnostic_slice in enumerate(aligned_slices):
                        _, diagnostic_duration, _ = trim_wav_silence(
                            diagnostic_slice.audio_bytes,
                            preserve_edge_ms=35,
                        )
                        diagnostic_next_start = (
                            block.segments[diagnostic_index + 1].start_ms
                            if diagnostic_index + 1 < len(block.segments)
                            else diagnostic_slice.segment.end_ms
                        )
                        diagnostic_budget = max(
                            0.001,
                            (
                                max(
                                    diagnostic_slice.segment.end_ms,
                                    diagnostic_next_start,
                                )
                                - diagnostic_slice.segment.start_ms
                            )
                            / 1000.0,
                        )
                        peak_effective_ratio = max(
                            peak_effective_ratio,
                            diagnostic_duration / diagnostic_budget,
                        )
                    if peak_effective_ratio > self._tts_max_expressive_atempo:
                        refinement_factor = (
                            peak_effective_ratio / self._tts_max_expressive_atempo
                        )
                        initial_factor = float(block_adjustment.speed_factor or 1.0)
                        combined_factor = initial_factor * refinement_factor
                        if combined_factor <= float(MAX_ATEMPO_SPEED) + 1e-9:
                            refinement = plan_timing_adjustment(
                                alignment_duration,
                                alignment_duration / refinement_factor,
                                max_atempo_speed=MAX_ATEMPO_SPEED,
                            )
                            alignment_audio, refinement_metadata = self.timing_fitter.fit(
                                alignment_audio,
                                refinement,
                            )
                            alignment_audio, alignment_duration = normalize_wav_bytes(
                                alignment_audio
                            )
                            aligned_slices = split_whole_video_wav(
                                alignment_audio,
                                block.segments,
                            )
                            block_adjustment_metadata = {
                                **dict(block_adjustment_metadata),
                                "adaptive_refinement": refinement_metadata,
                                "peak_effective_ratio_before_refinement": round(
                                    peak_effective_ratio, 6
                                ),
                                "combined_atempo_factor": round(combined_factor, 6),
                            }
                            performance["whole_video_block_refit_count"] = int(
                                performance["whole_video_block_refit_count"]
                            ) + 1
                    repair_slice_by_id: dict[str, object] = {}
                    repair_provider_by_id: dict[str, TtsProviderOutput] = {}
                    repair_speech_by_id: dict[str, str] = {}
                    repair_cache_key_by_id: dict[str, str] = {}
                    repair_source_by_id: dict[str, str] = {}
                    repair_alignment_duration_by_id: dict[str, float] = {}
                    repair_adjustment_metadata_by_id: dict[str, dict] = {}
                    unsafe_slices: list[tuple[int, object, float, float]] = []
                    for diagnostic_index, diagnostic_slice in enumerate(aligned_slices):
                        _, diagnostic_duration, _ = trim_wav_silence(
                            diagnostic_slice.audio_bytes,
                            preserve_edge_ms=35,
                        )
                        diagnostic_next_start = (
                            block.segments[diagnostic_index + 1].start_ms
                            if diagnostic_index + 1 < len(block.segments)
                            else diagnostic_slice.segment.end_ms
                        )
                        diagnostic_budget = max(
                            0.001,
                            (
                                max(
                                    diagnostic_slice.segment.end_ms,
                                    diagnostic_next_start,
                                )
                                - diagnostic_slice.segment.start_ms
                            )
                            / 1000.0,
                        )
                        diagnostic_ratio = diagnostic_duration / diagnostic_budget
                        if diagnostic_ratio > self._tts_max_expressive_atempo:
                            unsafe_slices.append(
                                (
                                    diagnostic_index,
                                    diagnostic_slice,
                                    diagnostic_budget,
                                    diagnostic_ratio,
                                )
                            )

                    repair_rows: list[tuple[TranslationInputSegment, TranslationInputSegment]] = []
                    repair_cursor_ms = 0
                    for _, unsafe_slice, unsafe_budget, _ in unsafe_slices:
                        unsafe_segment = unsafe_slice.segment
                        approved_candidates = list(
                            dict.fromkeys(
                                [
                                    str(unsafe_segment.translated_text or "").strip(),
                                    *[
                                        str(value or "").strip()
                                        for value in unsafe_segment.candidate_texts
                                    ],
                                ]
                            )
                        )
                        approved_candidates = [
                            value for value in approved_candidates if value
                        ]
                        compact = min(
                            approved_candidates,
                            key=lambda value: (
                                count_spoken_units(value),
                                len(value),
                                approved_candidates.index(value),
                            ),
                        )
                        if compact == str(unsafe_segment.translated_text or "").strip():
                            continue
                        repaired_original = replace(
                            unsafe_segment,
                            translated_text=compact,
                            repair_actions=tuple(
                                dict.fromkeys(
                                    [
                                        *unsafe_segment.repair_actions,
                                        "gemini_whole_video_compact_repair",
                                    ]
                                )
                            ),
                        )
                        repair_budget_ms = max(1, int(round(unsafe_budget * 1000.0)))
                        repaired_synthetic = replace(
                            repaired_original,
                            start_ms=repair_cursor_ms,
                            end_ms=repair_cursor_ms + repair_budget_ms,
                            duration_budget_ms=repair_budget_ms,
                        )
                        repair_rows.append((repaired_original, repaired_synthetic))
                        repair_cursor_ms = repaired_synthetic.end_ms + 200

                    if repair_rows:
                        repair_parts: list[str] = []
                        repair_inputs: list[TtsProviderInput] = []
                        repair_plain_texts: list[str] = []
                        for repair_index, (_, repair_segment) in enumerate(repair_rows):
                            repair_speech, _, repair_voice = _candidate_runtime(
                                repair_segment.translated_text,
                                repair_segment.duration_budget_ms / 1000.0,
                            )
                            repair_part_input = _provider_input(
                                speech_text=repair_speech.speech_text,
                                voice=repair_voice,
                                budget_seconds=repair_segment.duration_budget_ms / 1000.0,
                                segment=repair_segment,
                            )
                            repair_inputs.append(repair_part_input)
                            repair_plain_texts.append(repair_speech.speech_text)
                            repair_parts.append(repair_part_input.text)
                            if repair_index < len(repair_rows) - 1:
                                repair_parts.append("[short pause]")
                        repair_first = repair_rows[0][1]
                        repair_last = repair_rows[-1][1]
                        repair_aggregate = replace(
                            repair_first,
                            end_ms=repair_last.end_ms,
                            duration_budget_ms=max(1, repair_last.end_ms - repair_first.start_ms),
                            translated_text=" ".join(
                                row.translated_text for _, row in repair_rows
                            ),
                            member_translation_segment_ids=tuple(
                                value
                                for original, _ in repair_rows
                                for value in (
                                    original.member_translation_segment_ids
                                    or (original.translation_segment_id,)
                                )
                            ),
                            member_transcript_segment_ids=tuple(
                                value
                                for original, _ in repair_rows
                                for value in (
                                    original.member_transcript_segment_ids
                                    or (original.transcript_segment_id,)
                                )
                            ),
                            member_segment_indices=tuple(
                                value
                                for original, _ in repair_rows
                                for value in (
                                    original.member_segment_indices
                                    or (original.segment_index,)
                                )
                            ),
                        )
                        repair_provider_text = "\n\n".join(repair_parts)
                        repair_duration_seconds = max(
                            0.001,
                            (repair_last.end_ms - repair_first.start_ms) / 1000.0,
                        )
                        repair_direction = (
                            "Use exactly the same narrator identity and Voice ID as the main video. "
                            "This is one compact timing-repair batch. Read only the Vietnamese "
                            "transcript, never read bracketed Audio Tags aloud. Do not add, omit, "
                            "repeat or paraphrase any words. Keep pauses short and complete the "
                            f"batch naturally within {repair_duration_seconds:.2f} seconds. "
                            + str(repair_inputs[0].voice_direction or "")
                        ).strip()
                        repair_input = TtsProviderInput(
                            text=repair_provider_text,
                            language_code=request.voice_config.language_code,
                            voice_config=request.voice_config,
                            target_duration_seconds=repair_duration_seconds,
                            voice_direction=repair_direction,
                            sample_context=self._tts_sample_context,
                            audio_tags=tuple(
                                dict.fromkeys(
                                    tag
                                    for item in repair_inputs
                                    for tag in item.audio_tags
                                )
                            ),
                            prosody_state=repair_inputs[0].prosody_state,
                            performance_chunk_id=(
                                f"whole-video-repair-{block.block_index + 1}"
                            ),
                            expressive_mode="required",
                            requested_features=tuple(
                                dict.fromkeys(
                                    feature
                                    for item in repair_inputs
                                    for feature in item.requested_features
                                )
                            ),
                        )
                        repair_cache_key = self._acoustic_cache_key(
                            repair_provider_text,
                            voice_config=request.voice_config,
                            runtime_authority=request.runtime_authority,
                            segment=repair_aggregate,
                        )
                        repair_output = (
                            None
                            if request.force_refresh
                            else self._load_acoustic_cache(
                                source_video,
                                cache_key=repair_cache_key,
                            )
                        )
                        repair_source = "compact_repair_cache_hit"
                        if repair_output is None:
                            repair_source = "compact_repair_provider_synthesis"
                            repair_output = _synthesize_provider(repair_input)
                            repair_audio, repair_duration, repair_trim = trim_wav_silence(
                                repair_output.audio_bytes
                            )
                            repair_output = replace(
                                repair_output,
                                audio_bytes=repair_audio,
                                duration_seconds=repair_duration,
                                provider_metadata={
                                    **dict(repair_output.provider_metadata or {}),
                                    "silence_trim": repair_trim,
                                    "whole_video_compact_repair": True,
                                },
                            )
                            repair_output = replace(
                                repair_output,
                                provider_metadata=self._verified_provider_metadata(
                                    repair_output.provider_metadata,
                                    repair_output.warnings,
                                ),
                            )
                            try:
                                self._write_acoustic_cache(
                                    source_video,
                                    repair_output,
                                    cache_key=repair_cache_key,
                                )
                            except Exception as exc:
                                logger.warning(
                                    "tts_whole_video_repair_cache_write_failed",
                                    extra={
                                        "source_video_id": str(source_video.id),
                                        "block_index": block.block_index,
                                        "error_type": type(exc).__name__,
                                    },
                                )
                        else:
                            performance["acoustic_cache_hit_count"] = int(
                                performance["acoustic_cache_hit_count"]
                            ) + 1
                            repair_output = replace(
                                repair_output,
                                provider_metadata=self._verified_provider_metadata(
                                    repair_output.provider_metadata,
                                    repair_output.warnings,
                                ),
                            )
                        repair_block_adjustment = plan_timing_adjustment(
                            float(repair_output.duration_seconds),
                            repair_duration_seconds,
                            max_atempo_speed=MAX_ATEMPO_SPEED,
                        )
                        if repair_block_adjustment.action == "block":
                            raise TtsPipelineError(
                                TtsPipelineErrorCode.TIMING_FIT_BLOCKED,
                                "Compact whole-video repair batch cannot fit safely: "
                                f"block_index={block.block_index} "
                                f"ratio={repair_block_adjustment.ratio:.3f}",
                            )
                        repair_aligned_audio, repair_block_metadata = self.timing_fitter.fit(
                            repair_output.audio_bytes,
                            repair_block_adjustment,
                        )
                        repair_aligned_audio, repair_aligned_duration = normalize_wav_bytes(
                            repair_aligned_audio
                        )
                        repair_slices = split_whole_video_wav(
                            repair_aligned_audio,
                            [synthetic for _, synthetic in repair_rows],
                        )
                        for repair_index, repair_slice in enumerate(repair_slices):
                            repaired_original, _ = repair_rows[repair_index]
                            repair_id = str(repaired_original.translation_segment_id)
                            repair_slice_by_id[repair_id] = replace(
                                repair_slice,
                                segment=repaired_original,
                            )
                            repair_provider_by_id[repair_id] = repair_output
                            repair_speech_by_id[repair_id] = repair_plain_texts[repair_index]
                            repair_cache_key_by_id[repair_id] = repair_cache_key
                            repair_source_by_id[repair_id] = repair_source
                            repair_alignment_duration_by_id[repair_id] = repair_aligned_duration
                            repair_adjustment_metadata_by_id[repair_id] = {
                                **dict(repair_block_metadata),
                                "repair_batch": True,
                                "repaired_segment_count": len(repair_rows),
                            }
                        repaired_by_id = {
                            str(original.translation_segment_id): original
                            for original, _ in repair_rows
                        }
                        subtitle_input_segments = [
                            repaired_by_id.get(str(row.translation_segment_id), row)
                            for row in subtitle_input_segments
                        ]
                        performance["whole_video_repair_batch_count"] = int(
                            performance["whole_video_repair_batch_count"]
                        ) + 1
                        performance["whole_video_repaired_segment_count"] = int(
                            performance["whole_video_repaired_segment_count"]
                        ) + len(repair_rows)
                    performance["alignment_slice_count"] = int(
                        performance.get("alignment_slice_count") or 0
                    ) + len(aligned_slices)
                    for part_index, aligned in enumerate(aligned_slices):
                        segment_key = str(aligned.segment.translation_segment_id)
                        aligned = repair_slice_by_id.get(segment_key, aligned)
                        selected_segment = aligned.segment
                        slice_provider_output = repair_provider_by_id.get(
                            segment_key, provider_output
                        )
                        slice_synthesis_source = repair_source_by_id.get(
                            segment_key, synthesis_source
                        )
                        slice_cache_key = repair_cache_key_by_id.get(
                            segment_key, acoustic_cache_key
                        )
                        slice_alignment_duration = repair_alignment_duration_by_id.get(
                            segment_key, alignment_duration
                        )
                        slice_block_adjustment_metadata = (
                            repair_adjustment_metadata_by_id.get(
                                segment_key, block_adjustment_metadata
                            )
                        )
                        source_budget_seconds = (
                            selected_segment.duration_budget_ms / 1000.0
                        )
                        next_start_ms = (
                            block.segments[part_index + 1].start_ms
                            if part_index + 1 < len(block.segments)
                            else selected_segment.end_ms
                        )
                        available_end_ms = max(selected_segment.end_ms, next_start_ms)
                        borrowed_gap_ms = max(
                            0, available_end_ms - selected_segment.end_ms
                        )
                        budget_seconds = max(
                            source_budget_seconds,
                            (available_end_ms - selected_segment.start_ms) / 1000.0,
                        )
                        assembly_segment = (
                            replace(
                                selected_segment,
                                end_ms=available_end_ms,
                                duration_budget_ms=max(
                                    1, available_end_ms - selected_segment.start_ms
                                ),
                            )
                            if borrowed_gap_ms > 0
                            else selected_segment
                        )
                        if borrowed_gap_ms > 0:
                            performance["whole_video_gap_borrow_count"] = int(
                                performance["whole_video_gap_borrow_count"]
                            ) + 1
                            performance["whole_video_gap_borrowed_ms"] = int(
                                performance["whole_video_gap_borrowed_ms"]
                            ) + int(borrowed_gap_ms)
                        aligned_audio, aligned_duration, aligned_trim = trim_wav_silence(
                            aligned.audio_bytes,
                            preserve_edge_ms=35,
                        )
                        adjustment = plan_timing_adjustment(
                            aligned_duration,
                            budget_seconds,
                            max_atempo_speed=self._tts_max_expressive_atempo,
                        )
                        if adjustment.action == "block":
                            raise TtsPipelineError(
                                TtsPipelineErrorCode.TIMING_FIT_BLOCKED,
                                "Whole-video aligned TTS segment cannot fit safely: "
                                f"segment_index={selected_segment.segment_index} "
                                f"block_index={block.block_index} "
                                f"ratio={adjustment.ratio:.3f} "
                                f"alignment_confidence={aligned.boundary_confidence:.3f} "
                                f"reason={adjustment.blocked_reason}",
                            )
                        local_fit_started_at = time.perf_counter()
                        fitted_audio, adjustment_metadata = self.timing_fitter.fit(
                            aligned_audio,
                            adjustment,
                        )
                        fitted_audio, actual_duration = normalize_wav_bytes(fitted_audio)
                        fitted_audio, edge_fade_metadata = apply_edge_fades(fitted_audio)
                        waveform_qa = analyze_waveform(fitted_audio)
                        selected_prosody = prosody_by_segment_id.get(
                            str(selected_segment.translation_segment_id)
                        )
                        prosody_audio_qa = analyze_prosody_audio(
                            fitted_audio,
                            prosody=selected_prosody,
                            provider_metadata=slice_provider_output.provider_metadata,
                        )
                        emotion_acceptance = build_emotion_acceptance_report(
                            planner_enabled=bool(emotion_enabled),
                            policy_report=(
                                emotion_policy_report.to_dict()
                                if emotion_policy_report is not None
                                else None
                            ),
                            provider_metadata=slice_provider_output.provider_metadata,
                            prosody_audio_qa=prosody_audio_qa,
                            waveform_valid=bool(waveform_qa.valid_speech_audio),
                            timing_ratio=float(adjustment.ratio),
                            review_atempo_limit=float(self._tts_review_atempo_limit),
                        )
                        if len(narration_blocks) > 1:
                            emotion_acceptance = {
                                **emotion_acceptance,
                                "single_voice_verified": False,
                                "voice_identity_verification": "multi_block_not_verified",
                                "passed": False,
                                "warnings": list(
                                    dict.fromkeys(
                                        [
                                            *list(emotion_acceptance.get("warnings") or []),
                                            "emotion_single_voice_not_verified",
                                        ]
                                    )
                                ),
                            }
                        performance["local_fit_qa_elapsed_ms"] = int(
                            performance["local_fit_qa_elapsed_ms"]
                        ) + int(
                            round((time.perf_counter() - local_fit_started_at) * 1000.0)
                        )
                        if not waveform_qa.valid_speech_audio:
                            raise TtsPipelineError(
                                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                                "Whole-video Gemini waveform QA rejected invalid audio: "
                                f"segment_index={selected_segment.segment_index}",
                            )
                        actual_duration = float(waveform_qa.duration_seconds)
                        fit_status, fit_ratio = classify_timing_fit(
                            actual_duration,
                            budget_seconds,
                        )
                        speech_text = repair_speech_by_id.get(
                            segment_key, block_plain_texts[part_index]
                        )
                        speech_budget = assess_speech_budget(
                            speech_text,
                            slot_seconds=budget_seconds,
                            units_per_second=speech_rate_calibration.units_per_second,
                        )
                        duration_gate_statuses.append(speech_budget.status)
                        speech_budget_metadata = {
                            **speech_budget.to_dict(),
                            "calibration": speech_rate_calibration.to_dict(),
                            "observed_audio_duration_seconds": round(
                                float(aligned_duration), 6
                            ),
                            "actual_timing_ratio": round(float(adjustment.ratio), 6),
                            "source_slot_seconds": round(source_budget_seconds, 6),
                            "fit_slot_seconds": round(budget_seconds, 6),
                            "borrowed_gap_ms": int(borrowed_gap_ms),
                            "timing_quality_band": adjustment.quality_band,
                        }
                        alignment_warning = (
                            ["whole_video_alignment_low_confidence"]
                            if aligned.boundary_confidence < 0.35
                            else []
                        )
                        if alignment_warning:
                            performance["alignment_low_confidence_count"] = int(
                                performance.get("alignment_low_confidence_count") or 0
                            ) + 1
                        all_warnings = list(
                            dict.fromkeys(
                                [
                                    *slice_provider_output.warnings,
                                    *alignment_warning,
                                    *waveform_qa.warnings,
                                    *prosody_audio_qa["warnings"],
                                    *emotion_acceptance["warnings"],
                                    *(
                                        ["timing_adjusted_atempo"]
                                        if adjustment.action == "atempo"
                                        else []
                                    ),
                                    *timing_fit_flags(fit_status),
                                ]
                            )
                        )
                        provider_metadata = {
                            **dict(slice_provider_output.provider_metadata or {}),
                            **adjustment_metadata,
                            "provider_reported_duration_seconds": aligned_duration,
                            "whole_provider_duration_seconds": slice_provider_output.duration_seconds,
                            "whole_aligned_duration_seconds": slice_alignment_duration,
                            "whole_block_timing_adjustment": slice_block_adjustment_metadata,
                            "speech_budget": speech_budget_metadata,
                            "timing_quality_band": adjustment.quality_band,
                            "effective_voice_config": request.voice_config.__dict__,
                            "edge_fade": edge_fade_metadata,
                            "waveform_qa": waveform_qa.to_dict(),
                            "prosody_audio_qa": prosody_audio_qa,
                            "emotion_acceptance": emotion_acceptance,
                            "whole_video_synthesis": {
                                "schema_version": GEMINI_WHOLE_VIDEO_VERSION,
                                "alignment_version": WHOLE_VIDEO_ALIGNMENT_VERSION,
                                "strategy": self._tts_synthesis_strategy,
                                "block_index": block.block_index,
                                "block_count": len(narration_blocks),
                                "source_segment_count": len(block.segments),
                                "single_request_video": len(narration_blocks) == 1,
                                "synthesis_source": slice_synthesis_source,
                                "alignment": {
                                    "boundary_confidence": aligned.boundary_confidence,
                                    "boundary_shift_ms": aligned.boundary_shift_ms,
                                    "slice_start_frame": aligned.start_frame,
                                    "slice_end_frame": aligned.end_frame,
                                    "trim": aligned_trim,
                                },
                                "gap_borrow": {
                                    "borrowed_ms": int(borrowed_gap_ms),
                                    "source_end_ms": int(selected_segment.end_ms),
                                    "assembly_end_ms": int(assembly_segment.end_ms),
                                },
                            },
                        }
                        synthesized_segment = SynthesizedSegment(
                            input_segment=assembly_segment,
                            audio_bytes=fitted_audio,
                            duration_seconds=actual_duration,
                            mime_type="audio/wav",
                            file_extension="wav",
                            provider_metadata=provider_metadata,
                            warnings=all_warnings,
                            fit_status=fit_status,
                            fit_ratio=fit_ratio,
                        )
                        synthesized.append(synthesized_segment)
                        warnings.extend(all_warnings)
                        part_member_ids = (
                            selected_segment.member_translation_segment_ids
                            or (selected_segment.translation_segment_id,)
                        )
                        part_member_indices = (
                            selected_segment.member_segment_indices
                            or (selected_segment.segment_index,)
                        )
                        fit_decisions.append(
                            {
                                "segment_index": selected_segment.segment_index,
                                "member_segment_indices": list(part_member_indices),
                                "member_translation_segment_ids": [
                                    str(value) for value in part_member_ids
                                ],
                                "decision": adjustment.action,
                                "fit_status": fit_status.value,
                                "fit_ratio": round(float(fit_ratio), 6),
                                "timing_quality_band": adjustment.quality_band,
                                "repair_actions": list(selected_segment.repair_actions),
                                "candidate_attempt_count": 1,
                                "whole_video_block_index": block.block_index,
                                "alignment_confidence": aligned.boundary_confidence,
                            }
                        )
                        probe_timeline.append(
                            {
                                "segment_index": selected_segment.segment_index,
                                "member_segment_indices": list(part_member_indices),
                                "start_ms": selected_segment.start_ms,
                                "end_ms": selected_segment.end_ms,
                                "target_duration_ms": selected_segment.duration_budget_ms,
                                "fit_target_duration_ms": int(round(budget_seconds * 1000.0)),
                                "borrowed_gap_ms": int(borrowed_gap_ms),
                                "attempts": [
                                    {
                                        "candidate_index": "whole_video_aligned_slice",
                                        "synthesis_source": slice_synthesis_source,
                                        "duration_seconds": round(aligned_duration, 6),
                                        "target_seconds": round(budget_seconds, 6),
                                        "ratio": round(float(adjustment.ratio), 6),
                                        "decision": adjustment.action,
                                    }
                                ],
                                "selected_ratio": round(float(adjustment.ratio), 6),
                                "whole_video_block_index": block.block_index,
                                "alignment_confidence": aligned.boundary_confidence,
                                "alignment_shift_ms": aligned.boundary_shift_ms,
                            }
                        )
                        assets.append(
                            self._persist_asset(
                                source_video,
                                context,
                                MediaAssetType.TTS_AUDIO_CLIP,
                                fitted_audio,
                                filename=(
                                    f"{subtitle_version}_segment_{selected_segment.segment_index}.wav"
                                ),
                                mime_type="audio/wav",
                                manifest_group="tts_segment_clips",
                                job_id=job_id,
                                metadata={
                                    "translation_segment_id": str(
                                        selected_segment.translation_segment_id
                                    ),
                                    "translation_segment_ids": [
                                        str(value) for value in part_member_ids
                                    ],
                                    "member_segment_indices": list(part_member_indices),
                                    "duration_seconds": actual_duration,
                                    "fit_status": fit_status.value,
                                    "fit_ratio": fit_ratio,
                                    "provider": provider_metadata,
                                    "speech_budget": speech_budget_metadata,
                                    "warnings": all_warnings,
                                    "tts_segment_cache_key": slice_cache_key,
                                    "tts_segment_cache_status": slice_synthesis_source,
                                },
                            )
                        )

            segmentwise_timeline = [] if whole_video_strategy else timeline_segments
            for index, segment in enumerate(segmentwise_timeline):
                if on_progress is not None:
                    # Reserve headroom for join/subtitle/persist phases after the loop.
                    on_progress(
                        f"synthesize_segment|{index + 1}|{total}",
                        min(90, int((index / total) * 90)),
                    )
                budget_seconds = segment.duration_budget_ms / 1000.0
                ranked_candidate_texts = _rank_tts_candidates(
                    segment,
                    budget_seconds,
                    speech_rate_calibration.units_per_second,
                    pronunciation_glossary=self._pronunciation_glossary,
                )
                candidate_texts = _select_tts_probe_candidates(
                    ranked_candidate_texts,
                    expressive_required=self._tts_expressive_mode == "required",
                )
                primary_speech = build_vietnamese_speech_text(
                    candidate_texts[0],
                    pronunciation_glossary=self._pronunciation_glossary,
                )
                budget_assessment = assess_speech_budget(
                    primary_speech.speech_text,
                    slot_seconds=budget_seconds,
                    units_per_second=speech_rate_calibration.units_per_second,
                )
                duration_gate_statuses.append(budget_assessment.status)
                cached_segment = None
                segment_cache_key = ""
                if not request.force_refresh:
                    # Search the same ranked candidate/rate plans used below.
                    # This makes the fitted cache a complete authority instead
                    # of accidentally keying a corrected clip as base-rate audio.
                    for cache_candidate in candidate_texts:
                        cache_segment = replace(
                            segment,
                            translated_text=cache_candidate,
                        )
                        _, _, cache_voice = _candidate_runtime(
                            cache_candidate,
                            budget_seconds,
                        )
                        for fitted_voice in (
                            cache_voice,
                            _correction_voice(cache_voice),
                        ):
                            cache_key = self._segment_cache_key(
                                cache_segment,
                                voice_config=fitted_voice,
                                runtime_authority=request.runtime_authority,
                            )
                            cached_segment = self._load_segment_cache(
                                source_video,
                                cache_segment,
                                cache_key=cache_key,
                            )
                            if cached_segment is not None:
                                segment_cache_key = cache_key
                                break
                        if cached_segment is not None:
                            break
                if cached_segment is not None:
                    cached_segment = replace(
                        cached_segment,
                        provider_metadata=self._verified_provider_metadata(
                            cached_segment.provider_metadata,
                            cached_segment.warnings,
                        ),
                    )
                    performance["fitted_cache_hit_count"] = int(
                        performance["fitted_cache_hit_count"]
                    ) + 1
                    cached_input = cached_segment.input_segment
                    synthesized.append(cached_segment)
                    warnings.extend(cached_segment.warnings)
                    cached_provider = dict(cached_segment.provider_metadata or {})
                    cached_speech_budget = dict(cached_provider.get("speech_budget") or {})
                    assets.append(
                        self._persist_asset(
                            source_video,
                            context,
                            MediaAssetType.TTS_AUDIO_CLIP,
                            cached_segment.audio_bytes,
                            filename=f"{subtitle_version}_segment_{cached_input.segment_index}.wav",
                            mime_type="audio/wav",
                            manifest_group="tts_segment_clips",
                            job_id=job_id,
                            metadata={
                                "translation_segment_id": str(cached_input.translation_segment_id),
                                "translation_segment_ids": [
                                    str(value) for value in cached_input.member_translation_segment_ids
                                ],
                                "member_segment_indices": list(cached_input.member_segment_indices),
                                "duration_seconds": cached_segment.duration_seconds,
                                "fit_status": cached_segment.fit_status.value,
                                "fit_ratio": cached_segment.fit_ratio,
                                "provider": cached_provider,
                                "speech_budget": cached_speech_budget,
                                "warnings": list(cached_segment.warnings),
                                "tts_segment_cache_key": segment_cache_key,
                                "tts_segment_cache_status": "hit",
                            },
                        )
                    )
                    logger.info(
                        "tts_segment_cache_hit",
                        extra={
                            "source_video_id": str(source_video.id),
                            "segment_index": int(cached_input.segment_index),
                            "cache_key": segment_cache_key[:12],
                        },
                    )
                    fit_decisions.append(
                        {
                            "segment_index": cached_input.segment_index,
                            "member_segment_indices": list(cached_input.member_segment_indices),
                            "member_translation_segment_ids": [
                                str(value) for value in cached_input.member_translation_segment_ids
                            ],
                            "decision": "segment_cache_hit",
                            "fit_status": cached_segment.fit_status.value,
                            "fit_ratio": round(float(cached_segment.fit_ratio), 6),
                            "repair_actions": list(cached_input.repair_actions),
                            "candidate_attempt_count": 0,
                        }
                    )
                    probe_timeline.append(
                        {
                            "segment_index": cached_input.segment_index,
                            "member_segment_indices": list(cached_input.member_segment_indices),
                            "start_ms": cached_input.start_ms,
                            "end_ms": cached_input.end_ms,
                            "target_duration_ms": cached_input.duration_budget_ms,
                            "attempts": [],
                            "selected_text_sha256": hashlib.sha256(
                                cached_input.translated_text.encode("utf-8")
                            ).hexdigest(),
                            "selected_ratio": round(float(cached_segment.fit_ratio), 6),
                            "cache_status": "fitted_cache_hit",
                        }
                    )
                    continue
                _prefetch_batch(index)
                selected_segment = segment
                selected_speech = build_vietnamese_speech_text(
                    segment.translated_text,
                    pronunciation_glossary=self._pronunciation_glossary,
                )
                selected_duration_plan = None
                selected_voice_config = request.voice_config
                best_probe = None
                best_adjustment = None
                candidate_attempts: list[dict] = []
                for candidate_index, candidate_text in enumerate(candidate_texts):
                    probe_segment = replace(segment, translated_text=candidate_text)
                    speech, duration_plan, effective_voice = _candidate_runtime(
                        candidate_text,
                        budget_seconds,
                    )
                    acoustic_cache_key = self._acoustic_cache_key(
                        speech.speech_text,
                        voice_config=effective_voice,
                        runtime_authority=request.runtime_authority,
                        segment=probe_segment,
                    )
                    prefetched = prefetched_probes.get(str(segment.translation_segment_id))
                    synthesis_source = "provider_synthesis"
                    if candidate_index == 0 and prefetched is not None:
                        provider_output = prefetched[1]
                        synthesis_source = (
                            "acoustic_cache_hit"
                            if dict(provider_output.provider_metadata or {}).get(
                                "acoustic_cache", {}
                            ).get("status")
                            == "hit"
                            else "batch_provider_synthesis"
                        )
                        provider_output = replace(
                            provider_output,
                            provider_metadata={
                                **dict(provider_output.provider_metadata or {}),
                                "batch_probe": True,
                            },
                        )
                    else:
                        provider_output = (
                            None
                            if request.force_refresh
                            else self._load_acoustic_cache(
                                source_video,
                                cache_key=acoustic_cache_key,
                            )
                        )
                        if provider_output is None:
                            provider_output = _synthesize_provider(
                                _provider_input(
                                    speech_text=speech.speech_text,
                                    voice=effective_voice,
                                    budget_seconds=budget_seconds,
                                    segment=probe_segment,
                                )
                            )
                        else:
                            synthesis_source = "acoustic_cache_hit"
                    acoustic_cache_hit = bool(
                        dict(provider_output.provider_metadata or {}).get("acoustic_cache", {}).get("status")
                        == "hit"
                    )
                    if acoustic_cache_hit:
                        performance["acoustic_cache_hit_count"] = int(
                            performance["acoustic_cache_hit_count"]
                        ) + 1
                    if not acoustic_cache_hit:
                        trimmed_audio, trimmed_duration, trim_metadata = trim_wav_silence(
                            provider_output.audio_bytes
                        )
                        provider_output = replace(
                            provider_output,
                            audio_bytes=trimmed_audio,
                            duration_seconds=trimmed_duration,
                            provider_metadata={
                                **dict(provider_output.provider_metadata or {}),
                                "silence_trim": trim_metadata,
                                "acoustic_cache": {
                                    "status": "miss_written",
                                    "cache_key": acoustic_cache_key,
                                },
                            },
                        )
                        provider_output = replace(
                            provider_output,
                            provider_metadata=self._verified_provider_metadata(
                                provider_output.provider_metadata,
                                provider_output.warnings,
                            ),
                        )
                        try:
                            self._write_acoustic_cache(
                                source_video,
                                provider_output,
                                cache_key=acoustic_cache_key,
                            )
                        except Exception as exc:
                            logger.warning(
                                "tts_acoustic_cache_write_failed",
                                extra={
                                    "source_video_id": str(source_video.id),
                                    "segment_index": int(segment.segment_index),
                                    "error_type": type(exc).__name__,
                                },
                            )
                    provider_output = replace(
                        provider_output,
                        provider_metadata={
                            **dict(provider_output.provider_metadata or {}),
                            "speech_input": speech.to_dict(),
                            "duration_plan": duration_plan.to_dict(),
                            "source_prosody": dict(probe_segment.source_prosody or {}),
                            "tts_director": _director_metadata(probe_segment),
                        },
                    )
                    provider_output = replace(
                        provider_output,
                        provider_metadata=self._verified_provider_metadata(
                            provider_output.provider_metadata,
                            provider_output.warnings,
                        ),
                    )
                    measured_duration = float(provider_output.duration_seconds)
                    adjustment = plan_timing_adjustment(
                        measured_duration,
                        budget_seconds,
                        max_atempo_speed=self._tts_max_expressive_atempo,
                    )
                    attempt = {
                        "candidate_index": candidate_index,
                        "text_sha256": hashlib.sha256(candidate_text.encode("utf-8")).hexdigest(),
                        "spoken_units": count_spoken_units(speech.speech_text),
                        "speech_text_sha256": hashlib.sha256(
                            speech.speech_text.encode("utf-8")
                        ).hexdigest(),
                        "speaking_rate": round(float(effective_voice.speaking_rate), 6),
                        "duration_plan": duration_plan.to_dict(),
                        "synthesis_source": synthesis_source,
                        "duration_seconds": round(measured_duration, 6),
                        "target_seconds": round(budget_seconds, 6),
                        "ratio": round(adjustment.ratio, 6),
                        "decision": adjustment.action,
                    }
                    candidate_attempts.append(attempt)
                    if best_adjustment is None or adjustment.ratio < best_adjustment.ratio:
                        best_probe = provider_output
                        best_adjustment = adjustment
                        selected_segment = probe_segment
                        selected_speech = speech
                        selected_duration_plan = duration_plan
                        selected_voice_config = effective_voice
                    if adjustment.action != "block":
                        best_probe = provider_output
                        best_adjustment = adjustment
                        selected_segment = probe_segment
                        selected_speech = speech
                        selected_duration_plan = duration_plan
                        selected_voice_config = effective_voice
                        break

                provider_output = best_probe
                adjustment = best_adjustment
                if provider_output is None or adjustment is None:
                    raise TtsPipelineError(
                        TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                        f"TTS probe produced no usable audio: segment_index={segment.segment_index}",
                    )

                if adjustment.action == "block":
                    faster_voice = _correction_voice(selected_voice_config)
                    faster_rate = float(faster_voice.speaking_rate)
                    corrected_cache_key = self._acoustic_cache_key(
                        selected_speech.speech_text,
                        voice_config=faster_voice,
                        runtime_authority=request.runtime_authority,
                        segment=selected_segment,
                    )
                    corrected = (
                        None
                        if request.force_refresh
                        else self._load_acoustic_cache(
                            source_video,
                            cache_key=corrected_cache_key,
                        )
                    )
                    corrected_cache_hit = corrected is not None
                    if corrected_cache_hit:
                        performance["acoustic_cache_hit_count"] = int(
                            performance["acoustic_cache_hit_count"]
                        ) + 1
                    if corrected is None:
                        corrected = _synthesize_provider(
                            _provider_input(
                                speech_text=selected_speech.speech_text,
                                voice=faster_voice,
                                budget_seconds=budget_seconds,
                                segment=selected_segment,
                            )
                        )
                    if not corrected_cache_hit:
                        corrected_audio, corrected_duration, trim_metadata = trim_wav_silence(corrected.audio_bytes)
                        corrected = replace(
                            corrected,
                            audio_bytes=corrected_audio,
                            duration_seconds=corrected_duration,
                            provider_metadata={
                                **dict(corrected.provider_metadata or {}),
                                "silence_trim": trim_metadata,
                                "selective_correction": "voice_rate_probe",
                                "acoustic_cache": {
                                    "status": "miss_written",
                                    "cache_key": corrected_cache_key,
                                },
                            },
                        )
                        corrected = replace(
                            corrected,
                            provider_metadata=self._verified_provider_metadata(
                                corrected.provider_metadata,
                                corrected.warnings,
                            ),
                        )
                        try:
                            self._write_acoustic_cache(
                                source_video,
                                corrected,
                                cache_key=corrected_cache_key,
                            )
                        except Exception as exc:
                            logger.warning(
                                "tts_acoustic_cache_write_failed",
                                extra={
                                    "source_video_id": str(source_video.id),
                                    "segment_index": int(segment.segment_index),
                                    "error_type": type(exc).__name__,
                                },
                            )
                    corrected = replace(
                        corrected,
                        provider_metadata={
                            **dict(corrected.provider_metadata or {}),
                            "selective_correction": "voice_rate_probe",
                            "speech_input": selected_speech.to_dict(),
                            "source_prosody": dict(selected_segment.source_prosody or {}),
                            "tts_director": _director_metadata(selected_segment),
                        },
                    )
                    corrected = replace(
                        corrected,
                        provider_metadata=self._verified_provider_metadata(
                            corrected.provider_metadata,
                            corrected.warnings,
                        ),
                    )
                    corrected_duration = float(corrected.duration_seconds)
                    corrected_adjustment = plan_timing_adjustment(
                        corrected_duration,
                        budget_seconds,
                        max_atempo_speed=self._tts_max_expressive_atempo,
                    )
                    candidate_attempts.append(
                        {
                            "candidate_index": "voice_rate_correction",
                            "speaking_rate": round(faster_rate, 4),
                            "spoken_units": count_spoken_units(selected_speech.speech_text),
                            "duration_seconds": round(corrected_duration, 6),
                            "target_seconds": round(budget_seconds, 6),
                            "ratio": round(corrected_adjustment.ratio, 6),
                            "decision": corrected_adjustment.action,
                        }
                    )
                    if corrected_adjustment.ratio < adjustment.ratio:
                        provider_output = corrected
                        adjustment = corrected_adjustment
                        selected_voice_config = faster_voice
                        performance["selective_correction_count"] = int(
                            performance["selective_correction_count"]
                        ) + 1

                probe_timeline.append(
                    {
                        "segment_index": selected_segment.segment_index,
                        "member_segment_indices": list(selected_segment.member_segment_indices),
                        "start_ms": selected_segment.start_ms,
                        "end_ms": selected_segment.end_ms,
                        "target_duration_ms": selected_segment.duration_budget_ms,
                        "attempts": candidate_attempts,
                        "selected_text_sha256": hashlib.sha256(selected_segment.translated_text.encode("utf-8")).hexdigest(),
                        "selected_speech_text_sha256": hashlib.sha256(
                            selected_speech.speech_text.encode("utf-8")
                        ).hexdigest(),
                        "selected_speaking_rate": round(
                            float(selected_voice_config.speaking_rate), 6
                        ),
                        "selected_ratio": round(adjustment.ratio, 6),
                    }
                )
                if adjustment.action == "block":
                    selected_spoken_units = count_spoken_units(
                        selected_speech.speech_text
                    )
                    hard_unit_limit = recommended_spoken_unit_limit(
                        selected_spoken_units,
                        provider_output.duration_seconds,
                        budget_seconds,
                        max_speed=MAX_ATEMPO_SPEED,
                    )
                    natural_unit_limit = recommended_spoken_unit_limit(
                        selected_spoken_units,
                        provider_output.duration_seconds,
                        budget_seconds,
                        max_speed=SOFT_ATEMPO_SPEED,
                    )
                    raise TtsPipelineError(
                        TtsPipelineErrorCode.TIMING_FIT_BLOCKED,
                        "TTS segment cannot fit safely: "
                        f"segment_index={segment.segment_index} "
                        f"ratio={adjustment.ratio:.3f} "
                        f"spoken_units={selected_spoken_units} "
                        f"measured_hard_max_spoken_units={hard_unit_limit} "
                        f"measured_natural_max_spoken_units={natural_unit_limit} "
                        f"reason={adjustment.blocked_reason}",
                    )
                local_fit_started_at = time.perf_counter()
                fitted_audio, adjustment_metadata = self.timing_fitter.fit(
                    provider_output.audio_bytes,
                    adjustment,
                )
                fitted_audio, actual_duration = normalize_wav_bytes(fitted_audio)
                fitted_audio, edge_fade_metadata = apply_edge_fades(fitted_audio)
                waveform_qa = analyze_waveform(fitted_audio)
                selected_prosody = prosody_by_segment_id.get(
                    str(selected_segment.translation_segment_id)
                )
                prosody_audio_qa = analyze_prosody_audio(
                    fitted_audio,
                    prosody=selected_prosody,
                    provider_metadata=provider_output.provider_metadata,
                )
                emotion_acceptance = build_emotion_acceptance_report(
                    planner_enabled=bool(emotion_enabled),
                    policy_report=(
                        emotion_policy_report.to_dict()
                        if emotion_policy_report is not None
                        else None
                    ),
                    provider_metadata=provider_output.provider_metadata,
                    prosody_audio_qa=prosody_audio_qa,
                    waveform_valid=bool(waveform_qa.valid_speech_audio),
                    timing_ratio=float(adjustment.ratio),
                    review_atempo_limit=float(self._tts_review_atempo_limit),
                )
                performance["local_fit_qa_elapsed_ms"] = int(
                    performance["local_fit_qa_elapsed_ms"]
                ) + int(
                    round((time.perf_counter() - local_fit_started_at) * 1000.0)
                )
                if not waveform_qa.valid_speech_audio:
                    raise TtsPipelineError(
                        TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                        "TTS waveform QA rejected near-silent or invalid audio: "
                        f"segment_index={segment.segment_index}",
                    )
                actual_duration = float(waveform_qa.duration_seconds)
                budget_assessment = assess_speech_budget(
                    selected_speech.speech_text,
                    slot_seconds=budget_seconds,
                    units_per_second=speech_rate_calibration.units_per_second,
                )
                fit_status, fit_ratio = classify_timing_fit(
                    actual_duration,
                    budget_seconds,
                )
                adjustment_warnings = (
                    ["timing_adjusted_atempo"]
                    if adjustment.action == "atempo"
                    else []
                )
                if adjustment.quality_band == "review_speed_adjustment":
                    adjustment_warnings.append("timing_adjustment_review_recommended")
                if float(adjustment.ratio) > float(self._tts_review_atempo_limit):
                    adjustment_warnings.append("timing_translation_repair_recommended")
                budget_warnings = []
                if budget_assessment.status == "too_long":
                    budget_warnings.append("duration_budget_estimate_too_long")
                elif budget_assessment.status == "too_short":
                    budget_warnings.append("duration_budget_estimate_underfilled")
                all_warnings = list(
                    dict.fromkeys(
                        [
                            *provider_output.warnings,
                            *budget_warnings,
                            *adjustment_warnings,
                            *waveform_qa.warnings,
                            *prosody_audio_qa["warnings"],
                            *emotion_acceptance["warnings"],
                            *timing_fit_flags(fit_status),
                        ]
                    )
                )
                observed_speech_duration_seconds = max(
                    0.1,
                    float(provider_output.duration_seconds)
                    - (budget_assessment.pause_budget_ms / 1000.0),
                )
                observed_units_per_second = (
                    budget_assessment.spoken_units / observed_speech_duration_seconds
                    if budget_assessment.spoken_units > 0
                    and observed_speech_duration_seconds > 0
                    else None
                )
                speech_budget_metadata = {
                    **budget_assessment.to_dict(),
                    "calibration": speech_rate_calibration.to_dict(),
                    "observed_audio_duration_seconds": round(
                        float(provider_output.duration_seconds), 6
                    ),
                    "observed_speech_duration_seconds": round(
                        observed_speech_duration_seconds, 6
                    ),
                    "observed_units_per_second": (
                        round(float(observed_units_per_second), 6)
                        if observed_units_per_second is not None
                        else None
                    ),
                    "actual_timing_ratio": round(float(adjustment.ratio), 6),
                    "timing_quality_band": adjustment.quality_band,
                }
                provider_metadata = {
                    **dict(provider_output.provider_metadata or {}),
                    **adjustment_metadata,
                    "provider_reported_duration_seconds": provider_output.duration_seconds,
                    "speech_budget": speech_budget_metadata,
                    "timing_acceptance": {
                        "review_atempo_limit": float(self._tts_review_atempo_limit),
                        "actual_atempo_ratio": round(float(adjustment.ratio), 6),
                        "passed": float(adjustment.ratio) <= float(self._tts_review_atempo_limit),
                        "action": (
                            "accepted"
                            if float(adjustment.ratio) <= float(self._tts_review_atempo_limit)
                            else "review_translation_repair"
                        ),
                    },
                    "duration_plan": (
                        selected_duration_plan.to_dict()
                        if selected_duration_plan is not None
                        else None
                    ),
                    "effective_voice_config": selected_voice_config.__dict__,
                    "edge_fade": edge_fade_metadata,
                    "waveform_qa": waveform_qa.to_dict(),
                    "prosody_audio_qa": prosody_audio_qa,
                    "emotion_acceptance": emotion_acceptance,
                    "source_prosody": dict(selected_segment.source_prosody or {}),
                }
                synthesized_segment = SynthesizedSegment(
                    input_segment=selected_segment,
                    audio_bytes=fitted_audio,
                    duration_seconds=actual_duration,
                    mime_type="audio/wav",
                    file_extension="wav",
                    provider_metadata=provider_metadata,
                    warnings=all_warnings,
                    fit_status=fit_status,
                    fit_ratio=fit_ratio,
                )
                segment_cache_key = self._segment_cache_key(
                    selected_segment,
                    voice_config=selected_voice_config,
                    runtime_authority=request.runtime_authority,
                )
                try:
                    self._write_segment_cache(
                        source_video,
                        synthesized_segment,
                        cache_key=segment_cache_key,
                    )
                except Exception as exc:  # Cache is an optimization, never output authority.
                    logger.warning(
                        "tts_segment_cache_write_failed",
                        extra={
                            "source_video_id": str(source_video.id),
                            "segment_index": int(segment.segment_index),
                            "error_type": type(exc).__name__,
                        },
                    )
                synthesized.append(synthesized_segment)
                warnings.extend(all_warnings)
                fit_decisions.append(
                    {
                        "segment_index": selected_segment.segment_index,
                        "member_segment_indices": list(selected_segment.member_segment_indices),
                        "member_translation_segment_ids": [
                            str(value) for value in selected_segment.member_translation_segment_ids
                        ],
                        "decision": adjustment.action,
                        "fit_status": fit_status.value,
                        "fit_ratio": round(float(fit_ratio), 6),
                        "timing_quality_band": adjustment.quality_band,
                        "repair_actions": list(selected_segment.repair_actions),
                        "candidate_attempt_count": len(candidate_attempts),
                    }
                )
                assets.append(
                    self._persist_asset(
                        source_video,
                        context,
                        MediaAssetType.TTS_AUDIO_CLIP,
                        fitted_audio,
                        filename=f"{subtitle_version}_segment_{segment.segment_index}.wav",
                        mime_type="audio/wav",
                        manifest_group="tts_segment_clips",
                        job_id=job_id,
                        metadata={
                            "translation_segment_id": str(selected_segment.translation_segment_id),
                            "translation_segment_ids": [
                                str(value) for value in selected_segment.member_translation_segment_ids
                            ],
                            "member_segment_indices": list(selected_segment.member_segment_indices),
                            "duration_seconds": actual_duration,
                            "fit_status": fit_status.value,
                            "fit_ratio": fit_ratio,
                            "provider": provider_metadata,
                            "speech_budget": speech_budget_metadata,
                            "warnings": all_warnings,
                            "tts_segment_cache_key": segment_cache_key,
                            "tts_segment_cache_status": "miss_written",
                        },
                    )
                )

            if on_progress is not None:
                on_progress("assemble_narration", 92)
            joined_audio, joined_metadata = self.narration_assembler.assemble(
                synthesized,
                timeline_duration_seconds=timeline_duration_seconds,
            )
            joined_waveform_qa = analyze_waveform(joined_audio)
            joined_metadata = {
                **dict(joined_metadata or {}),
                "waveform_qa": joined_waveform_qa.to_dict(),
                "tts_authority": dict(getattr(self, "_runtime_tts_authority", {}) or {}),
            }
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

            if on_progress is not None:
                on_progress("persist_subtitles", 95)
            subtitle_inputs = (
                subtitle_input_segments
                if whole_video_strategy
                else [row.input_segment for row in synthesized]
            )
            subtitle_drafts = self.subtitle_builder.build(subtitle_inputs, synthesized)
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

            performance["total_clip_count"] = len(synthesized)
            performance["total_elapsed_ms"] = int(
                round((time.perf_counter() - pipeline_started_at) * 1000.0)
            )
            avoided_provider_clips = min(
                len(synthesized),
                int(performance["fitted_cache_hit_count"])
                + int(performance["acoustic_cache_hit_count"]),
            )
            performance["provider_avoidance_ratio"] = round(
                avoided_provider_clips / max(1, len(synthesized)), 6
            )
            temporal_artifacts = [
                (
                    "phase3_dialogue_graph.json",
                    dialogue_graph,
                    "tts_temporal_dialogue_graph",
                ),
                (
                    "phase3_tts_calibration.json",
                    {
                        "schema_version": "tts_voice_calibration_v1",
                        "pipeline_version": TTS_PIPELINE_VERSION,
                        "provider": self.tts_provider.provider_name,
                        "voice_config": request.voice_config.__dict__,
                        "calibration": speech_rate_calibration.to_dict(),
                    },
                    "tts_temporal_calibration",
                ),
                (
                    "phase3_tts_probe_timeline.json",
                    {
                        "schema_version": "tts_probe_timeline_v1",
                        "pipeline_version": TTS_PIPELINE_VERSION,
                        "segments": probe_timeline,
                    },
                    "tts_temporal_probe",
                ),
                (
                    "phase3_tts_fit_decisions.json",
                    {
                        "schema_version": "tts_global_fit_decisions_v1",
                        "pipeline_version": TTS_PIPELINE_VERSION,
                        "segments": fit_decisions,
                    },
                    "tts_temporal_fit",
                ),
                (
                    "phase3_tts_final_timeline.json",
                    {
                        "schema_version": "tts_final_timeline_v1",
                        "pipeline_version": TTS_PIPELINE_VERSION,
                        "translation_input_sha256": _translation_input_sha256(input_segments),
                        "timing_map": list(joined_metadata.get("timing_map") or []),
                    },
                    "tts_temporal_final",
                ),
                (
                    "phase3_tts_performance.json",
                    performance,
                    "tts_temporal_performance",
                ),
                (
                    "phase4_tts_director_plan.json",
                    {
                        **director_payload,
                        "source_context_schema_version": TTS_DIRECTOR_SOURCE_CONTEXT_VERSION,
                        "provider_capabilities": provider_capabilities.to_dict(),
                    },
                    "tts_director_plan",
                ),
                (
                    "phase4_tts_performance_chunks.json",
                    performance_chunk_report,
                    "tts_performance_chunks",
                ),
                (
                    "phase4_tts_prosody_qa.json",
                    prosody_qa,
                    "tts_prosody_qa",
                ),
            ]
            for filename, payload, manifest_group in temporal_artifacts:
                assets.append(
                    self._persist_json_asset(
                        source_video,
                        context,
                        MediaAssetType.RENDER_DEBUG_JSON,
                        payload,
                        filename=f"{subtitle_version}_{filename}",
                        manifest_group=manifest_group,
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

            if on_progress is not None:
                on_progress("build_render_manifest", 98)
            current_assets = self._assets_for_video(source_video.id)
            manifest = build_render_prep_manifest(
                source_video_id=str(source_video.id),
                source_video_external_id=source_video.source_video_external_id,
                assets=current_assets,
                synthesized_segments=synthesized,
                subtitle_version=subtitle_version,
                provider_summary={
                    "tts_provider": self.tts_provider.provider_name,
                    "voice_config": request.voice_config.__dict__,
                    "director_version": director_plan.director_version,
                    "director_plan_sha256": self._tts_director_plan_sha256,
                    "voice_bible_sha256": self._tts_voice_bible_sha256,
                    "provider_capabilities": provider_capabilities.to_dict(),
                    "prosody_degraded_features": prosody_degraded_features,
                    "expressive_mode": self._tts_expressive_mode,
                    "tts_authority": dict(
                        getattr(self, "_runtime_tts_authority", {}) or {}
                    ),
                },
                warnings=list(dict.fromkeys(warnings)),
                timeline_duration_seconds=timeline_duration_seconds,
                translation_input_sha256=_translation_input_sha256(input_segments),
                background_stem_ref=self._background_stem_ref(source_video),
                duration_gate_summary=dict(Counter(duration_gate_statuses)),
                temporal_summary={
                    "pipeline_version": TTS_PIPELINE_VERSION,
                    "dialogue_group_count": len(timeline_segments),
                    "merged_segment_count": int(
                        dialogue_graph.get("merged_segment_count") or 0
                    ),
                    "selective_correction_count": sum(
                        1
                        for row in probe_timeline
                        if any(
                            attempt.get("candidate_index") == "voice_rate_correction"
                            for attempt in list(row.get("attempts") or [])
                        )
                    ),
                    "final_timeline_ready": True,
                    "director_version": director_plan.director_version,
                    "director_plan_sha256": self._tts_director_plan_sha256,
                    "voice_bible_sha256": self._tts_voice_bible_sha256,
                    "performance_chunker_version": PERFORMANCE_CHUNKER_VERSION,
                    "performance_chunk_count": len(performance_chunks),
                    "provider_capabilities": provider_capabilities.to_dict(),
                    "prosody_degraded_features": prosody_degraded_features,
                    "prosody_qa_version": PROSODY_QA_VERSION,
                    "prosody_qa_passed": bool(prosody_qa["passed"]),
                    "expressive_mode": self._tts_expressive_mode,
                    "performance": performance,
                },
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
            source_video.metadata_json = {
                **dict(source_video.metadata_json or {}),
                "tts_temporal": {
                    "pipeline_version": TTS_PIPELINE_VERSION,
                    "input_segment_count": len(input_segments),
                    "dialogue_group_count": len(timeline_segments),
                    "merged_segment_count": int(dialogue_graph.get("merged_segment_count") or 0),
                    "candidate_probe_count": sum(
                        len(list(row.get("attempts") or [])) for row in probe_timeline
                    ),
                    "selective_correction_count": sum(
                        1
                        for row in probe_timeline
                        if any(
                            attempt.get("candidate_index") == "voice_rate_correction"
                            for attempt in list(row.get("attempts") or [])
                        )
                    ),
                    "background_audio_preserved": self._background_stem_ref(source_video) is not None,
                    "director_version": director_plan.director_version,
                    "director_plan_sha256": self._tts_director_plan_sha256,
                    "voice_bible_sha256": self._tts_voice_bible_sha256,
                    "performance_chunk_count": len(performance_chunks),
                    "prosody_degraded_features": prosody_degraded_features,
                    "tts_authority": dict(
                        getattr(self, "_runtime_tts_authority", {}) or {}
                    ),
                    "performance": performance,
                    "status": "TTS_TEMPORAL_READY",
                },
            }
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

    def _tts_director_source_context(self, source_video: SourceVideo) -> dict:
        """Load already-computed Audio Analysis context without re-decoding audio.

        Audio Analysis publishes the same authority into ``SourceVideo.metadata_json``
        and an ``AUDIO_ANALYSIS_METADATA`` asset.  The metadata snapshot is the fast
        path; the asset is consulted when older jobs lack the denormalized fields.
        Missing context is intentionally non-fatal so TTS remains usable for legacy
        Translation Drafts.
        """
        raw = dict(getattr(source_video, "metadata_json", None) or {})
        context = {
            "audio_event_timeline": raw.get("audio_event_timeline"),
            "target_speech_authority": raw.get("target_speech_authority"),
            "semantic_dialogue_segmentation": raw.get("semantic_dialogue_segmentation"),
            "target_speech_authority_sha256": (
                dict(raw.get("target_speech_authority") or {}).get("authority_sha256")
                or dict(raw.get("audio_analysis_authority") or {}).get("target_speech_authority_sha256")
            ),
        }
        if context["audio_event_timeline"] is None or context["semantic_dialogue_segmentation"] is None:
            asset = self._current_asset(source_video.id, MediaAssetType.AUDIO_ANALYSIS_METADATA)
            if asset is not None and asset.storage_key and self.storage.exists(asset.storage_key):
                try:
                    payload = json.loads(self.storage.read_bytes(asset.storage_key).decode("utf-8"))
                    if isinstance(payload, dict):
                        for key in ("audio_event_timeline", "target_speech_authority", "semantic_dialogue_segmentation"):
                            if context.get(key) is None:
                                context[key] = payload.get(key)
                        if not context.get("target_speech_authority_sha256"):
                            context["target_speech_authority_sha256"] = dict(
                                payload.get("target_speech_authority") or {}
                            ).get("authority_sha256")
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    logger.warning(
                        "tts_director_audio_context_unavailable",
                        extra={"source_video_id": str(source_video.id)},
                    )
        context["schema_version"] = TTS_DIRECTOR_SOURCE_CONTEXT_VERSION
        return context

    def get_render_prep_manifest(self, source_video_id: UUID) -> dict:
        asset = self._current_asset(source_video_id, MediaAssetType.RENDER_PREP_MANIFEST)
        if asset and isinstance(asset.metadata_json, dict) and "manifest" in asset.metadata_json:
            manifest = dict(asset.metadata_json["manifest"] or {})
            source_video = self._load_source_video(source_video_id)
            assert_manifest_tts_authority_active(
                self.db,
                source_video.workspace_id,
                manifest,
            )
            return manifest
        return {"manifest_version": "RENDER_PREP_MANIFEST_V2", "source_video": {"id": str(source_video_id)}, "current_outputs": {}}

    def get_tts_summary(self, source_video_id: UUID) -> dict:
        assets = self._assets_for_video(source_video_id)
        source_video = self._load_source_video(source_video_id)
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
        temporal_artifacts = [
            {
                "id": str(asset.id),
                "manifest_group": asset.manifest_group,
                "storage_key": asset.storage_key,
                "sha256": asset.checksum_sha256,
            }
            for asset in assets
            if asset.asset_type == MediaAssetType.RENDER_DEBUG_JSON
            and asset.is_current
            and str(asset.manifest_group or "").startswith("tts_temporal_")
        ]
        temporal = dict(
            dict(source_video.metadata_json or {}).get("tts_temporal") or {}
        )
        temporal["artifact_count"] = len(temporal_artifacts)
        temporal["final_timing_fit_passed"] = not any(
            clip.get("fit_status") == TimingFitStatus.TOO_LONG.value
            for clip in clips
        ) and bool(tts_assets)
        return {
            "source_video_id": str(source_video_id),
            "tts_asset_count": len(tts_assets),
            "subtitle_count": subtitle_count,
            "warnings": list(dict.fromkeys(warnings)),
            "clips": clips,
            "timing_fit_summary": build_timing_fit_summary(clips),
            "temporal": temporal or None,
            "temporal_artifacts": temporal_artifacts,
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

    def _segment_cache_key(
        self,
        segment,
        *,
        voice_config: VoiceConfig,
        runtime_authority: dict | None,
    ) -> str:
        speech = build_vietnamese_speech_text(
            str(segment.translated_text),
            pronunciation_glossary=getattr(self, "_pronunciation_glossary", None),
        )
        payload = {
            "schema_version": TTS_SEGMENT_CACHE_SCHEMA,
            "pipeline_version": TTS_PIPELINE_VERSION,
            "provider_identity": self._provider_cache_identity(),
            "runtime_authority": dict(runtime_authority or {}),
            "voice": {
                "voice_id": voice_config.voice_id,
                "language_code": voice_config.language_code,
                "speaking_rate": float(voice_config.speaking_rate),
            },
            "display_text": str(segment.translated_text),
            "speech_text": speech.speech_text,
            "speech_text_normalizer": speech.normalizer_version,
            "duration_budget_ms": int(segment.duration_budget_ms),
            "timing_policy": {
                "duration_planner_version": DURATION_PLANNER_VERSION,
                "max_atempo_speed": float(MAX_ATEMPO_SPEED),
                "soft_atempo_speed": float(SOFT_ATEMPO_SPEED),
                "max_expressive_atempo": float(
                    getattr(self, "_tts_max_expressive_atempo", MAX_ATEMPO_SPEED)
                ),
            },
            "performance_direction": self._performance_direction_cache_identity(segment),
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _provider_cache_identity(self) -> dict:
        target = getattr(self.tts_provider, "primary", None) or self.tts_provider
        base_url = str(getattr(target, "base_url", "") or "")
        return {
            "provider": str(getattr(target, "provider_name", "") or ""),
            "model_id": str(getattr(target, "model_id", "") or ""),
            "provider_options": dict(getattr(target, "options", {}) or {}),
            "base_url_sha256": (
                hashlib.sha256(base_url.encode("utf-8")).hexdigest()
                if base_url
                else None
            ),
        }

    def _performance_direction_cache_identity(self, segment) -> dict:
        """Return only deterministic, secret-free direction inputs for cache keys."""
        prosody = None
        plan = getattr(self, "_tts_director_plan", None)
        if plan is not None:
            prosody = next(
                (
                    row.to_dict()
                    for row in plan.prosody_segments
                    if str(row.translation_segment_id) == str(segment.translation_segment_id)
                ),
                None,
            )
        return {
            "director_version": str(getattr(self, "_tts_director_version", "") or ""),
            "voice_bible_sha256": str(getattr(self, "_tts_voice_bible_sha256", "") or ""),
            "performance_chunker_version": str(getattr(self, "_tts_performance_chunker_version", "") or ""),
            "performance_chunk_id": str(
                getattr(self, "_tts_chunk_by_segment_id", {}).get(str(segment.translation_segment_id), "")
                or ""
            ),
            "prosody": prosody,
            "provider_lowering_version": PROVIDER_LOWERING_VERSION,
            "provider_capabilities": (
                getattr(self, "_tts_provider_capabilities", None).to_dict()
                if getattr(self, "_tts_provider_capabilities", None) is not None
                else {}
            ),
        }

    def _verified_provider_metadata(
        self,
        metadata: dict | None,
        warnings: list[str] | tuple[str, ...],
    ) -> dict:
        """Reject any clip that escaped the one active setup authority."""

        row = dict(metadata or {})
        authority = dict(getattr(self, "_runtime_tts_authority", {}) or {})
        if not authority:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                "TTS provider output has no active setup authority.",
            )
        if bool(row.get("fallback_used")) or "tts_used_fallback_provider" in {
            str(value) for value in warnings
        }:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                "TTS provider attempted to use a fallback model. Production allows only the setup currently On.",
            )

        def normalized(value: object) -> str:
            raw = str(value or "").strip().lower().replace("-", "_")
            if raw == "omnivoice_studio":
                return "omnivoice"
            return raw

        expected_provider = normalized(authority.get("provider"))
        actual_provider = normalized(row.get("provider"))
        if actual_provider and actual_provider != expected_provider:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                f"TTS provider mismatch: expected {expected_provider}, received {actual_provider}.",
            )
        expected_model = str(authority.get("model_id") or "").strip()
        actual_model = str(row.get("model_id") or "").strip()
        if expected_model and actual_model and actual_model != expected_model:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                f"TTS model mismatch: expected {expected_model}, received {actual_model}.",
            )
        expected_voice = str(authority.get("voice_id") or "").strip()
        actual_voice = str(row.get("voice_id") or "").strip()
        if actual_voice and actual_voice != expected_voice:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                f"TTS voice mismatch: expected {expected_voice}, received {actual_voice}.",
            )
        return {
            **row,
            "provider": expected_provider,
            "model_id": expected_model,
            "voice_id": expected_voice,
            "tts_authority": authority,
            "fallback_used": False,
        }

    def _acoustic_cache_key(
        self,
        text: str,
        *,
        voice_config: VoiceConfig,
        runtime_authority: dict | None,
        segment=None,
    ) -> str:
        """Cache expensive model inference independently from timeline fitting."""

        payload = {
            "schema_version": TTS_ACOUSTIC_CACHE_SCHEMA,
            "provider_identity": self._provider_cache_identity(),
            "runtime_authority": dict(runtime_authority or {}),
            "voice": {
                "voice_id": voice_config.voice_id,
                "language_code": voice_config.language_code,
                "speaking_rate": float(voice_config.speaking_rate),
            },
            "text": " ".join(str(text or "").split()),
            "performance_direction": self._performance_direction_cache_identity(segment)
            if segment is not None
            else {
                "director_version": str(getattr(self, "_tts_director_version", "") or ""),
                "director_plan_sha256": str(getattr(self, "_tts_director_plan_sha256", "") or ""),
                "voice_bible_sha256": str(getattr(self, "_tts_voice_bible_sha256", "") or ""),
                "provider_lowering_version": PROVIDER_LOWERING_VERSION,
            },
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _acoustic_cache_keys(workspace_id: UUID, cache_key: str) -> tuple[str, str]:
        prefix = f"workspace_{workspace_id}/tts-acoustic-cache/{cache_key[:2]}"
        return f"{prefix}/{cache_key}.wav", f"{prefix}/{cache_key}.json"

    def _load_acoustic_cache(
        self,
        source_video: SourceVideo,
        *,
        cache_key: str,
    ):
        audio_key, meta_key = self._acoustic_cache_keys(
            source_video.workspace_id, cache_key
        )
        if not self.storage.exists(audio_key) or not self.storage.exists(meta_key):
            return None
        try:
            metadata = json.loads(self.storage.read_bytes(meta_key).decode("utf-8"))
            audio_bytes = self.storage.read_bytes(audio_key)
            if (
                not isinstance(metadata, dict)
                or metadata.get("schema_version") != TTS_ACOUSTIC_CACHE_SCHEMA
                or str(metadata.get("cache_key") or "") != cache_key
                or hashlib.sha256(audio_bytes).hexdigest()
                != str(metadata.get("audio_sha256") or "")
                or not audio_bytes.startswith(b"RIFF")
            ):
                return None
            return TtsProviderOutput(
                audio_bytes=audio_bytes,
                duration_seconds=float(metadata["duration_seconds"]),
                mime_type="audio/wav",
                file_extension="wav",
                provider_metadata={
                    **dict(metadata.get("provider_metadata") or {}),
                    "acoustic_cache": {"status": "hit", "cache_key": cache_key},
                },
                warnings=list(metadata.get("warnings") or []),
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning("tts_acoustic_cache_invalid", extra={"cache_key": cache_key})
            return None

    def _write_acoustic_cache(
        self,
        source_video: SourceVideo,
        provider_output,
        *,
        cache_key: str,
    ) -> None:
        audio_key, meta_key = self._acoustic_cache_keys(
            source_video.workspace_id, cache_key
        )
        metadata = {
            "schema_version": TTS_ACOUSTIC_CACHE_SCHEMA,
            "cache_key": cache_key,
            "audio_sha256": hashlib.sha256(provider_output.audio_bytes).hexdigest(),
            "duration_seconds": float(provider_output.duration_seconds),
            "provider_metadata": dict(provider_output.provider_metadata or {}),
            "warnings": list(provider_output.warnings or []),
        }
        self.storage.write_bytes(audio_key, provider_output.audio_bytes)
        self.storage.write_bytes(
            meta_key,
            json.dumps(
                metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8"),
        )

    @staticmethod
    def _segment_cache_keys(workspace_id: UUID, cache_key: str) -> tuple[str, str]:
        prefix = f"workspace_{workspace_id}/tts-segment-cache/{cache_key[:2]}"
        return f"{prefix}/{cache_key}.wav", f"{prefix}/{cache_key}.json"

    def _load_segment_cache(
        self,
        source_video: SourceVideo,
        segment,
        *,
        cache_key: str,
    ) -> SynthesizedSegment | None:
        audio_key, meta_key = self._segment_cache_keys(
            source_video.workspace_id, cache_key
        )
        if not self.storage.exists(audio_key) or not self.storage.exists(meta_key):
            return None
        try:
            metadata = json.loads(self.storage.read_bytes(meta_key).decode("utf-8"))
            audio_bytes = self.storage.read_bytes(audio_key)
            if (
                not isinstance(metadata, dict)
                or metadata.get("schema_version") != TTS_SEGMENT_CACHE_SCHEMA
                or str(metadata.get("cache_key") or "") != cache_key
                or hashlib.sha256(audio_bytes).hexdigest()
                != str(metadata.get("audio_sha256") or "")
                or not audio_bytes.startswith(b"RIFF")
            ):
                return None
            return SynthesizedSegment(
                input_segment=segment,
                audio_bytes=audio_bytes,
                duration_seconds=float(metadata["duration_seconds"]),
                mime_type="audio/wav",
                file_extension="wav",
                provider_metadata={
                    **dict(metadata.get("provider_metadata") or {}),
                    "segment_cache": {
                        "status": "hit",
                        "cache_key": cache_key,
                    },
                },
                warnings=list(metadata.get("warnings") or []),
                fit_status=TimingFitStatus(str(metadata["fit_status"])),
                fit_ratio=float(metadata["fit_ratio"]),
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning(
                "tts_segment_cache_invalid",
                extra={"cache_key": cache_key, "source_video_id": str(source_video.id)},
            )
            return None

    def _write_segment_cache(
        self,
        source_video: SourceVideo,
        synthesized: SynthesizedSegment,
        *,
        cache_key: str,
    ) -> None:
        audio_key, meta_key = self._segment_cache_keys(
            source_video.workspace_id, cache_key
        )
        metadata = {
            "schema_version": TTS_SEGMENT_CACHE_SCHEMA,
            "cache_key": cache_key,
            "audio_sha256": hashlib.sha256(synthesized.audio_bytes).hexdigest(),
            "duration_seconds": float(synthesized.duration_seconds),
            "fit_status": str(synthesized.fit_status),
            "fit_ratio": float(synthesized.fit_ratio),
            "provider_metadata": dict(synthesized.provider_metadata or {}),
            "warnings": list(synthesized.warnings),
        }
        # Audio first, metadata last: the JSON object is the completion marker.
        self.storage.write_bytes(audio_key, synthesized.audio_bytes)
        self.storage.write_bytes(
            meta_key,
            json.dumps(
                metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8"),
        )

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

    def _speech_rate_calibration(
        self,
        workspace_id: UUID,
        voice_config: VoiceConfig,
    ):
        recent_assets = list(
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
        provider_target = getattr(self.tts_provider, "primary", None) or self.tts_provider
        samples = _voice_rate_samples(
            recent_assets,
            provider_name=str(getattr(provider_target, "provider_name", "") or ""),
            model_id=str(getattr(provider_target, "model_id", "") or ""),
            voice_config=voice_config,
        )
        return calibrate_units_per_second(
            samples,
            default_units_per_second=(
                DEFAULT_VI_UNITS_PER_SECOND * float(voice_config.speaking_rate)
            ),
        )

    def _background_stem_ref(self, source_video: SourceVideo) -> dict | None:
        separation = dict(dict(source_video.metadata_json or {}).get("separation") or {})
        metadata = dict(separation.get("metadata") or {})
        storage_key = str(metadata.get("background_storage_key") or "").strip()
        if not storage_key or not self.storage.exists(storage_key):
            return None
        object_metadata = self.storage.metadata(storage_key)
        if not object_metadata.exists or not object_metadata.checksum_sha256:
            return None
        return {
            "storage_key": object_metadata.storage_key,
            "sha256": object_metadata.checksum_sha256,
            "size_bytes": object_metadata.size_bytes,
            "mime_type": "audio/wav",
            "role": "background_without_vocals",
        }

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


def _translation_input_sha256(segments: list) -> str:
    payload = [
        {
            "translation_segment_id": str(segment.translation_segment_id),
            "transcript_segment_id": str(segment.transcript_segment_id),
            "segment_index": int(segment.segment_index),
            "start_ms": int(segment.start_ms),
            "end_ms": int(segment.end_ms),
            "text": str(segment.translated_text),
            "candidate_texts": list(segment.candidate_texts),
            "source_text_sha256": hashlib.sha256(
                str(segment.source_text or "").encode("utf-8")
            ).hexdigest(),
            "speaker_label": segment.speaker_label,
            "duration_budget_ms": int(segment.duration_budget_ms),
            "translation_version": int(segment.translation_version),
            "translation_status": str(
                getattr(segment, "translation_status", "") or ""
            ),
            "source_prosody": dict(getattr(segment, "source_prosody", {}) or {}),
        }
        for segment in segments
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _translation_authority_sha256(source_video: SourceVideo) -> str | None:
    metadata = getattr(source_video, "metadata_json", None)
    if not isinstance(metadata, dict):
        return None
    authority = metadata.get("translation_authority")
    if not isinstance(authority, dict) or not authority:
        return None
    return sha256_json(authority)


def _same_translation_snapshot(
    payload: dict,
    *,
    translation_input_sha256: str,
    translation_authority_sha256: str | None,
) -> bool:
    return (
        "translation_input_sha256" in payload
        and "translation_authority_sha256" in payload
        and
        str(payload.get("translation_input_sha256") or "")
        == str(translation_input_sha256 or "")
        and str(payload.get("translation_authority_sha256") or "")
        == str(translation_authority_sha256 or "")
    )


def _assert_translation_snapshot_current(
    request: TtsRequest,
    *,
    source_video: SourceVideo,
    input_segments: list,
) -> None:
    """Fail closed for bound jobs while keeping legacy direct requests runnable."""

    expected_input = str(request.translation_input_sha256 or "").strip()
    expected_authority = str(request.translation_authority_sha256 or "").strip()
    if not expected_input and not expected_authority:
        return
    actual_input = _translation_input_sha256(input_segments)
    actual_authority = _translation_authority_sha256(source_video) or ""
    if expected_input != actual_input or expected_authority != actual_authority:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
            "Translation Draft changed after this TTS job was created. Create a new TTS job from the current approved draft.",
        )


def _rank_tts_candidates(
    segment,
    budget_seconds: float,
    units_per_second: float,
    *,
    pronunciation_glossary: dict[str, str] | None = None,
) -> list[str]:
    """Rank approved alternatives before paying for a real TTS probe.

    The function is intentionally deterministic and local.  Semantic authority
    remains the approved translation/candidate set; this layer only rejects an
    alternative that loses protected numbers/units and ranks duration fit.
    """

    ranked = rank_preflight_candidates(
        segment,
        slot_seconds=budget_seconds,
        units_per_second=units_per_second,
        pronunciation_glossary=pronunciation_glossary,
    )
    return ranked or [str(segment.translated_text or "").strip()]


def _select_tts_probe_candidates(
    ranked: list[str],
    *,
    expressive_required: bool,
) -> list[str]:
    """Keep the best translation plus one compact, pre-approved timing fallback.

    Expressive synthesis used to probe only the primary candidate. A real voice can
    be slower than the text estimate, so that policy blocked even when Translation V3
    had already approved a semantically safe compact candidate. Probe the compact
    alternative only when the primary measured audio blocks; the caller breaks on the
    first fit, keeping provider cost bounded to two calls.
    """
    candidates = [str(value or "").strip() for value in ranked if str(value or "").strip()]
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) <= TTS_MAX_CANDIDATE_SYNTHESIS_PER_SEGMENT:
        return candidates
    if not expressive_required:
        return candidates[:TTS_MAX_CANDIDATE_SYNTHESIS_PER_SEGMENT]
    primary = candidates[0]
    compact = min(
        candidates[1:],
        key=lambda value: (count_spoken_units(value), candidates.index(value)),
    )
    return [primary, compact]


def _pronunciation_glossary(workspace_tts: object | None) -> dict[str, str]:
    options = getattr(workspace_tts, "options_json", None)
    if not isinstance(options, dict):
        return {}
    raw = options.get("pronunciation_glossary")
    if not isinstance(raw, dict):
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in raw.items()
        if str(key).strip() and str(value).strip()
    }


def _voice_rate_samples(
    assets: list,
    *,
    provider_name: str,
    model_id: str = "",
    voice_config: VoiceConfig,
) -> list[SpeechRateSample]:
    return speech_rate_samples_from_metadata(
        [
            metadata
            for asset in assets
            if isinstance((metadata := getattr(asset, "metadata_json", None) or {}), dict)
        ],
        provider_name=provider_name,
        voice_id=voice_config.voice_id,
        speaking_rate=voice_config.speaking_rate,
        model_id=model_id or None,
        require_quality=True,
    )


def _tts_idempotency_key(
    *,
    source_video_id: UUID,
    translation_input_sha256: str,
    voice_config: VoiceConfig,
    runtime_authority: dict | None = None,
) -> str:
    voice_payload = json.dumps(
        (
            voice_config.__dict__
            if runtime_authority is None
            else {
                "voice_config": voice_config.__dict__,
                "runtime_authority": runtime_authority,
            }
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    voice_hash = hashlib.sha256(voice_payload).hexdigest()
    return (
        f"tts:{TTS_PIPELINE_VERSION}:{source_video_id}:"
        f"{str(translation_input_sha256)[:24]}:{voice_hash[:24]}"
    )


def _same_tts_authority(left: dict, right: dict) -> bool:
    return all(
        str(left.get(field) or "") == str(right.get(field) or "")
        for field in (
            "schema_version",
            "workspace_id",
            "profile_id",
            "provider",
            "model_id",
            "voice_id",
            "config_fingerprint",
        )
    )
