from __future__ import annotations

import shutil
import os
import time
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.audio_pipeline.analysis_audio import (
    materialize_analysis_audio,
    prune_analysis_audio_cache,
)
from src.audio_pipeline.canonical_audio import (
    CANONICAL_CHANNELS,
    CANONICAL_SAMPLE_RATE,
    _canonical_asset_is_usable,
)
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.errors import AudioAnalysisError
from src.storage.local import LocalStorageBackend
from src.enums import MediaAssetStatus, MediaAssetType
from src.models.media import MediaAsset


def _wav(path: Path, *, sample_rate: int, channels: int, seconds: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\0\0" * frames * channels)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required for local audio intermediate")
def test_analysis_audio_is_content_addressed_and_reused(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    source_key = "audio/source.wav"
    _wav(storage.resolve(source_key).absolute_path, sample_rate=44_100, channels=2)
    source_sha = storage.metadata(source_key).checksum_sha256

    first = materialize_analysis_audio(
        storage,
        source_storage_key=source_key,
        source_checksum_sha256=source_sha,
    )
    second = materialize_analysis_audio(
        storage,
        source_storage_key=source_key,
        source_checksum_sha256=source_sha,
    )

    assert first is not None and second is not None
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.storage_key == second.storage_key
    with wave.open(str(storage.resolve(first.storage_key).absolute_path), "rb") as handle:
        assert handle.getframerate() == 16_000
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required for local audio intermediate")
def test_corrupt_analysis_audio_cache_is_regenerated(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    source_key = "audio/source.wav"
    _wav(storage.resolve(source_key).absolute_path, sample_rate=44_100, channels=2)
    source_sha = storage.metadata(source_key).checksum_sha256
    first = materialize_analysis_audio(
        storage,
        source_storage_key=source_key,
        source_checksum_sha256=source_sha,
    )
    assert first is not None
    storage.write_bytes(first.storage_key, b"not-a-wav")

    repaired = materialize_analysis_audio(
        storage,
        source_storage_key=source_key,
        source_checksum_sha256=source_sha,
    )

    assert repaired is not None
    assert repaired.cache_hit is False
    with wave.open(str(storage.resolve(repaired.storage_key).absolute_path), "rb") as handle:
        assert handle.getframerate() == 16_000
        assert handle.getnchannels() == 1


def test_analysis_cache_retention_only_deletes_old_files_over_budget(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    old_keys = [
        ".cache/audio-analysis/a/old-1.wav",
        ".cache/audio-analysis/a/old-2.wav",
    ]
    fresh_key = ".cache/audio-analysis/b/fresh.wav"
    for key in [*old_keys, fresh_key]:
        storage.write_bytes(key, b"x" * 10)
    old_timestamp = time.time() - 3600
    for key in old_keys:
        os.utime(storage.resolve(key).absolute_path, (old_timestamp, old_timestamp))

    result = prune_analysis_audio_cache(
        storage,
        max_bytes=15,
        min_age_seconds=60,
    )

    assert result["deleted"] == 2
    assert result["bytes_reclaimed"] == 20
    assert storage.exists(fresh_key)


def test_canonical_asset_probe_rejects_wrong_media_properties(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    key = "audio/wrong.wav"
    _wav(storage.resolve(key).absolute_path, sample_rate=16_000, channels=1)
    asset = SimpleNamespace(
        storage_key=key,
        metadata_json={
            "source_asset_sha256": "source-sha",
            "recipe_version": "canonical-audio-v2-lineage-probe",
        },
    )
    assert not _canonical_asset_is_usable(
        storage,
        asset,
        source_checksum_sha256="source-sha",
        expected_duration_seconds=1.0,
    )


def test_canonical_asset_probe_accepts_exact_pcm_authority(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    key = "audio/canonical.wav"
    _wav(
        storage.resolve(key).absolute_path,
        sample_rate=CANONICAL_SAMPLE_RATE,
        channels=CANONICAL_CHANNELS,
    )
    asset = SimpleNamespace(
        storage_key=key,
        metadata_json={
            "source_asset_sha256": "source-sha",
            "recipe_version": "canonical-audio-v2-lineage-probe",
        },
    )
    assert _canonical_asset_is_usable(
        storage,
        asset,
        source_checksum_sha256="source-sha",
        expected_duration_seconds=1.0,
    )


def test_cache_graph_requires_transcript_json_and_matching_row_count(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    source_id = uuid4()
    workspace_id = uuid4()
    source = SimpleNamespace(
        id=source_id,
        metadata_json={
            "audio_analysis_cache": {
                "fingerprint": "fp",
                "analysis_version": "AUDIO_ANALYSIS_V5_RUN_1",
                "flags_summary": {},
            },
            "audio_analysis_authority": {
                "schema_version": "audio-analysis-authority-manifest-v1",
                "analysis_fingerprint": "fp",
                "analysis_version": "AUDIO_ANALYSIS_V5_RUN_1",
                "transcript_sha256": "does-not-match",
            },
        },
    )
    metadata_key = "analysis/metadata.json"
    transcript_key = "analysis/transcript.json"
    storage.write_bytes(metadata_key, b'{"analysis_version":"AUDIO_ANALYSIS_V5_RUN_1","fingerprint":"fp"}')
    storage.write_bytes(transcript_key, b'{"analysis_version":"AUDIO_ANALYSIS_V5_RUN_1","segments":[],"audio_analysis_authority":{}}')

    def asset(asset_type: MediaAssetType, key: str) -> MediaAsset:
        return MediaAsset(
            workspace_id=workspace_id,
            source_video_id=source_id,
            asset_type=asset_type,
            status=MediaAssetStatus.AVAILABLE,
            version=1,
            storage_key=key,
            is_current=True,
        )

    db = MagicMock()
    db.scalars.return_value = [
        asset(MediaAssetType.AUDIO_ANALYSIS_METADATA, metadata_key),
        asset(MediaAssetType.TRANSCRIPT_JSON, transcript_key),
    ]
    service = AudioAnalysisService(db=db, storage=storage)
    service.get_transcript_segments = MagicMock(return_value=[])
    service.get_summary = MagicMock(
        return_value={"transcript_count": 1, "translation_count": 0, "asset_count": 2}
    )

    assert service._cached_result(source, "fp") is None


def test_translation_readiness_requires_dialogue_quality_contract() -> None:
    source = SimpleNamespace(
        metadata_json={
            "audio_analysis_authority": {
                "schema_version": "audio-analysis-authority-manifest-v1",
                "translation_ready": True,
                "semantic_translation_ready": True,
                "dialogue_quality_translation_ready": False,
                "operator_review_required": False,
            }
        }
    )
    with pytest.raises(AudioAnalysisError, match="dialogue quality contract"):
        AudioAnalysisService._require_translation_input_ready(
            source,
            require_source_approved=False,
        )


def test_translation_boundary_rejects_transcript_hash_drift() -> None:
    beat = SimpleNamespace(
        segment_index=0,
        start_ms=0,
        end_ms=1000,
        text="原文",
        normalized_text="原文",
        confidence=0.9,
        speaker_label=None,
        difficulty_flags_json={"flags": []},
    )
    source = SimpleNamespace(
        metadata_json={
            "audio_analysis_authority": {
                "transcript_sha256": AudioAnalysisService._transcript_authority_sha256([beat]),
            }
        }
    )
    service = AudioAnalysisService(db=MagicMock(), storage=MagicMock())
    service._assert_current_transcript_authority(source, [beat])
    beat.text = "đã sửa"
    with pytest.raises(AudioAnalysisError, match="no longer matches"):
        service._assert_current_transcript_authority(source, [beat])


def test_operator_approval_rebinds_authority_to_edited_transcript() -> None:
    beat = SimpleNamespace(
        segment_index=0,
        start_ms=0,
        end_ms=1000,
        text="đã chỉnh",
        normalized_text="đã chỉnh",
        confidence=0.9,
        speaker_label=None,
        difficulty_flags_json={"flags": ["edited_in_transcript_editor"]},
        status=None,
    )
    source = SimpleNamespace(
        id=uuid4(),
        metadata_json={
            "audio_analysis_authority": {
                "schema_version": "audio-analysis-authority-manifest-v1",
                "translation_ready": False,
                "operator_review_required": True,
            },
            "dialogue_phase": "dialogue_uncertain",
        }
    )
    service = AudioAnalysisService(db=MagicMock(), storage=MagicMock())
    service.get_transcript_segments = MagicMock(return_value=[beat])
    service._load_source_video = MagicMock(return_value=source)

    result = service.approve_source_transcript(source.id)

    assert result["approved_segments"] == 1
    authority = source.metadata_json["audio_analysis_authority"]
    assert authority["machine_approval_state"] == "operator_approved"
    assert authority["operator_review_required"] is False
    assert authority["translation_ready"] is True
    assert authority["transcript_sha256"] == AudioAnalysisService._transcript_authority_sha256([beat])
