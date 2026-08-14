from __future__ import annotations

from types import SimpleNamespace
import math
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.audio_pipeline.providers import FixedVadProvider, PlaceholderVietnameseTranslationProvider
from src.audio_pipeline.audio_mix_quality import analyze_pcm_wav_mix
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.semantic_dialogue_segmentation import (
    SEMANTIC_DIALOGUE_RECIPE_VERSION,
    segment_semantic_dialogue,
)
from src.audio_pipeline.stt_funasr import fit_funasr_units_to_duration, merge_chunked_units
from src.audio_pipeline.temporal_validation import validate_transcription_timeline
from src.audio_pipeline.types import AudioAnalysisRequest, TranscriptionUnit
from src.enums import JobStatus, JobStepStatus, JobType
from src.services.job_progress import apply_job_progress


def _unit(text: str, start: float, end: float, confidence: float = 0.8) -> TranscriptionUnit:
    return TranscriptionUnit(
        text=text,
        start_seconds=start,
        end_seconds=end,
        confidence=confidence,
        flags=["funasr"],
    )


def _timed_unit(
    text: str,
    start: float,
    end: float,
    *,
    chunk_index: int = 0,
    confidence: float = 0.8,
) -> TranscriptionUnit:
    compact = "".join(text.split())
    span = (end - start) / max(1, len(compact))
    timestamps = [
        [(start + index * span) * 1000.0, (start + (index + 1) * span) * 1000.0]
        for index in range(len(compact))
    ]
    return TranscriptionUnit(
        text=text,
        start_seconds=start,
        end_seconds=end,
        confidence=confidence,
        flags=["funasr", "funasr_word_timestamps", "funasr_chunked"],
        raw_payload={
            "chunk_index": chunk_index,
            "chunk_start_seconds": 0.0,
            "timestamps": timestamps,
            "timestamps_are_absolute": True,
            "word_timestamp_range": [0, len(compact) - 1],
        },
    )


def test_timed_overrun_clamps_only_offending_tail() -> None:
    units = [_unit("first", 1.0, 2.0), _unit("tail", 9.0, 12.0)]
    fitted = fit_funasr_units_to_duration(units, duration_seconds=10.0)
    assert (fitted[0].start_seconds, fitted[0].end_seconds) == (1.0, 2.0)
    assert (fitted[1].start_seconds, fitted[1].end_seconds) == (9.0, 10.0)
    assert "duration_clamped" in fitted[1].flags


def test_chunk_merge_deduplicates_overlap_and_keeps_best_confidence() -> None:
    merged = merge_chunked_units(
        [
            _unit("你好", 58.8, 60.2, 0.7),
            _unit("你好", 59.0, 60.1, 0.9),
            _unit("下一句", 60.3, 61.5, 0.8),
        ],
        overlap_seconds=0.5,
    )
    assert [unit.text for unit in merged] == ["你好", "下一句"]
    assert merged[0].confidence == 0.9


def test_chunk_merge_aligns_partial_suffix_prefix_and_preserves_timing() -> None:
    left = _timed_unit("自然就立体了这样鼻", 56.0, 60.0, chunk_index=0)
    right = _timed_unit("这样鼻影和眼影", 59.4, 62.2, chunk_index=1)

    merged = merge_chunked_units([left, right], overlap_seconds=1.5)

    assert [unit.text for unit in merged] == ["自然就立体了这样鼻", "影和眼影"]
    assert merged[1].start_seconds >= merged[0].end_seconds
    assert "funasr_chunk_overlap_aligned" in merged[1].flags
    assert merged[1].raw_payload["timestamps_are_absolute"] is True


def test_semantic_segmentation_moves_boundary_off_legacy_cap_and_keeps_lexeme() -> None:
    # The old 8-second safety cap split 鼻影 in half.  A later terminal phrase is
    # a safer semantic boundary and must win even though the utterance is longer.
    units = [
        _timed_unit("首先画一个小v然后顺着鼻", 0.0, 8.0, chunk_index=0),
        _timed_unit("影往上画就行然后画眉骨", 8.05, 15.8, chunk_index=0),
    ]

    result = segment_semantic_dialogue(units)
    texts = [unit.text for unit in result.units]

    assert "".join(texts) == "首先画一个小v然后顺着鼻影往上画就行然后画眉骨"
    assert not any(
        left.endswith("鼻") and right.startswith("影")
        for left, right in zip(texts, texts[1:])
    )
    assert result.diagnostics["recipe_version"] == SEMANTIC_DIALOGUE_RECIPE_VERSION
    assert result.diagnostics["authority_preserved"] is True
    assert result.diagnostics["translation_ready"] is True
    assert result.diagnostics["output_overlap_count"] == 0


def test_temporal_gate_flags_overlap_and_outside_vad_without_moving_clean_unit() -> None:
    validated = validate_transcription_timeline(
        [_unit("a", 1.0, 2.0), _unit("b", 1.7, 2.4), _unit("c", 8.0, 9.0)],
        duration_seconds=10.0,
        speech_intervals=[[0.8, 2.5]],
    )
    assert (validated[0].start_seconds, validated[0].end_seconds) == (1.0, 2.0)
    assert "asr_temporal_overlap" in validated[1].flags
    assert "asr_outside_vad_speech" in validated[2].flags


def test_audio_progress_authority_ignores_placeholder_step_weight() -> None:
    job = SimpleNamespace(
        status=JobStatus.RUNNING,
        progress_percent=0,
        metadata_json={"progress_authority": "audio_subphase", "subphase_percent": 31},
        steps=[
            SimpleNamespace(status=JobStepStatus.COMPLETED, step_key="legacy", step_order=0, progress_percent=100),
            SimpleNamespace(status=JobStepStatus.RUNNING, step_key="persist_outputs", step_order=1, progress_percent=90),
        ],
    )
    apply_job_progress(job)
    assert job.progress_percent == 31


def test_create_analysis_job_returns_existing_active_single_flight() -> None:
    source_id = uuid4()
    workspace_id = uuid4()
    source = SimpleNamespace(id=source_id, workspace_id=workspace_id)
    active = SimpleNamespace(id=uuid4(), job_type=JobType.ANALYZE_AUDIO, status=JobStatus.RUNNING)
    db = MagicMock()
    db.scalar.return_value = active
    service = AudioAnalysisService(
        db,
        storage=MagicMock(),
        vad_provider=FixedVadProvider(),
        stt_provider=MagicMock(provider_name="fake"),
        separation_provider=MagicMock(provider_name="fake"),
        translation_provider=PlaceholderVietnameseTranslationProvider(),
    )
    with patch.object(service, "_load_source_video", return_value=source), patch(
        "src.audio_pipeline.services.audio_analysis_service.JobService"
    ) as job_service:
        result = service.create_analysis_job(AudioAnalysisRequest(source_video_id=source_id))
    assert result is active
    job_service.assert_not_called()


def test_mix_quality_reads_canonical_pcm_without_model(tmp_path: Path) -> None:
    sample_rate = 16_000
    values = [int(math.sin(2 * math.pi * 440 * index / sample_rate) * 10_000) for index in range(sample_rate)]
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(value.to_bytes(2, "little", signed=True) for value in values))
    quality = analyze_pcm_wav_mix(path)
    assert quality.sampled_seconds == 1.0
    assert quality.rms_dbfs < 0
    assert 0.0 <= quality.spectral_flatness <= 1.0
