from __future__ import annotations

import math
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np

from src.audio_pipeline.providers import (
    FixedVadProvider,
    PlaceholderVietnameseTranslationProvider,
)
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.target_speech_authority import (
    TargetSpeechAuthority,
    TargetSpeechInterval,
    TargetSpeechStatus,
)
from src.audio_pipeline.types import (
    AudioAnalysisRequest,
    ResolvedAudioInput,
    TranscriptionUnit,
)
from src.enums import MediaAssetType, TranscriptSegmentStatus
from src.storage.local import LocalStorageBackend


class _RecordingStt:
    provider_name = "recording_stt"

    def __init__(self, units: list[TranscriptionUnit]):
        self.units = units
        self.calls: list[tuple[str, float | None]] = []

    def transcribe(self, audio_storage_key, *, source_caption=None, duration_seconds=None):
        del source_caption
        self.calls.append((audio_storage_key, duration_seconds))
        return list(self.units)


def _write_wav(path: Path, seconds: float = 3.0) -> None:
    sample_rate = 16_000
    time = np.arange(int(sample_rate * seconds), dtype=np.float32) / sample_rate
    signal = 0.15 * np.sin(2 * math.pi * 200 * time)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((signal * 32767).astype("<i2").tobytes())


def _interval() -> TargetSpeechInterval:
    return TargetSpeechInterval(
        start_seconds=1.0,
        end_seconds=2.0,
        decision="ACCEPT_DIALOGUE",
        confidence=0.9,
        speech_score=0.9,
        music_score=0.2,
        singing_score=0.1,
        reasons=("test_primary_dialogue",),
    )


def _authority(status: TargetSpeechStatus) -> TargetSpeechAuthority:
    target = (_interval(),) if status == TargetSpeechStatus.READY else ()
    rejected = (
        TargetSpeechInterval(
            start_seconds=0.0,
            end_seconds=3.0,
            decision="REJECT_NON_DIALOGUE",
            confidence=0.95,
            speech_score=0.7,
            music_score=0.9,
            singing_score=0.9,
            reasons=("singing",),
        ),
    ) if status == TargetSpeechStatus.NO_TARGET_SPEECH else ()
    return TargetSpeechAuthority(
        status=status,
        provider="injected_test",
        duration_seconds=3.0,
        target_intervals=target,
        ambiguous_intervals=(),
        rejected_intervals=rejected,
        event_windows=(),
        requires_separation=False,
        diagnostics={
            "target_seconds": 1.0 if target else 0.0,
            "target_ratio": 1 / 3 if target else 0.0,
        },
    )


def _run(tmp_path: Path, *, authority: TargetSpeechAuthority, stt: _RecordingStt):
    storage = LocalStorageBackend(tmp_path)
    audio_key = "audio/source.wav"
    _write_wav(storage.resolve(audio_key).absolute_path)
    source_video_id = uuid4()
    source = SimpleNamespace(
        id=source_video_id,
        workspace_id=uuid4(),
        source_platform="DOUYIN",
        source_video_external_id="target-speech-test",
        caption="metadata is not dialogue",
        duration_seconds=3.0,
        status=None,
        metadata_json={},
        source_profile=SimpleNamespace(
            source_profile_external_id="sec-test",
            handle="demo",
            display_name="Demo",
        ),
    )
    resolved = ResolvedAudioInput(
        source_video_id=source_video_id,
        input_asset_id=uuid4(),
        input_asset_type=MediaAssetType.SOURCE_AUDIO_EXTRACT,
        storage_key=audio_key,
        source_video_duration_seconds=3.0,
        source_caption=source.caption,
        source_checksum_sha256=storage.metadata(audio_key).checksum_sha256,
        canonicalized=True,
    )
    analyzer = MagicMock(return_value=authority)
    service = AudioAnalysisService(
        db=MagicMock(),
        storage=storage,
        stt_provider=stt,
        translation_provider=PlaceholderVietnameseTranslationProvider(),
        vad_provider=FixedVadProvider(has_speech=True, speech_ratio=1.0),
        target_speech_analyzer=analyzer,
        separation_provider=MagicMock(provider_name="unused"),
    )
    persisted = []

    def persist_transcripts(_source, drafts, _version, _job_id):
        persisted.extend(drafts)
        return [
            SimpleNamespace(
                id=uuid4(),
                segment_index=row.segment_index,
                start_ms=int(row.start_seconds * 1000),
                end_ms=int(row.end_seconds * 1000),
                text=row.source_text,
                normalized_text=row.normalized_source_text,
                confidence=row.confidence,
                status=TranscriptSegmentStatus.DRAFT,
                difficulty_flags_json={"flags": row.difficulty_flags},
            )
            for row in drafts
        ]

    with (
        patch("src.audio_pipeline.services.audio_analysis_service.AudioAssetResolver") as resolver_cls,
        patch.object(service, "_cached_result", return_value=None),
        patch.object(service, "_next_analysis_version", return_value="AUDIO_ANALYSIS_V4_RUN_1"),
        patch.object(service, "_mark_previous_non_current"),
        patch.object(service, "_persist_separation_assets", return_value=[]),
        patch.object(service, "_persist_transcripts", side_effect=persist_transcripts),
        patch.object(service, "_persist_translations", return_value=[]),
        patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
        patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
    ):
        resolver_cls.return_value.resolve.return_value = (source, resolved)
        result = service.run_analysis(
            AudioAnalysisRequest(source_video_id=source_video_id)
        )
    return SimpleNamespace(
        result=result,
        source=source,
        persisted=persisted,
        stt=stt,
        analyzer=analyzer,
    )


def test_singing_authority_prevents_asr_and_dialogue_creation(tmp_path: Path) -> None:
    stt = _RecordingStt(
        [TranscriptionUnit("错误歌词", 0.0, 2.0, 0.99)]
    )
    run = _run(
        tmp_path,
        authority=_authority(TargetSpeechStatus.NO_TARGET_SPEECH),
        stt=stt,
    )
    assert run.stt.calls == []
    assert run.persisted == []
    assert run.source.metadata_json["dialogue_phase"] == "no_dialogue"
    assert "non_dialogue_vocal_or_music" in run.result.flags_summary


def test_unavailable_local_authority_fails_closed_without_running_asr(
    tmp_path: Path,
) -> None:
    stt = _RecordingStt(
        [TranscriptionUnit("khong duoc dung", 0.0, 2.0, 0.99)]
    )
    run = _run(
        tmp_path,
        authority=_authority(TargetSpeechStatus.UNAVAILABLE),
        stt=stt,
    )
    assert run.stt.calls == []
    assert run.persisted == []
    assert run.source.metadata_json["dialogue_phase"] == "dialogue_uncertain"
    assert "target_speech_or_asr_uncertain" in run.result.flags_summary
    assert "needs_operator_review" in run.result.flags_summary


def test_only_target_interval_reaches_asr_and_is_remapped(tmp_path: Path) -> None:
    stt = _RecordingStt(
        [
            TranscriptionUnit(
                text="真正对白",
                start_seconds=0.20,
                end_seconds=0.75,
                confidence=0.92,
            )
        ]
    )
    run = _run(
        tmp_path,
        authority=_authority(TargetSpeechStatus.READY),
        stt=stt,
    )
    assert len(run.stt.calls) == 1
    assert ".cache/target-speech/" in run.stt.calls[0][0]
    assert len(run.persisted) == 1
    assert run.persisted[0].start_seconds >= 1.0
    assert run.persisted[0].end_seconds <= 2.0
    assert run.source.metadata_json["target_speech_authority"]["status"] == "READY"
