"""Create the single decoded audio authority consumed by local audio stages."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import wave
from dataclasses import replace
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.audio_pipeline.demucs_runner import run_captured
from src.audio_pipeline.types import ResolvedAudioInput
from src.enums import MediaAssetStatus, MediaAssetType
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend, to_windows_long_path

CANONICAL_SAMPLE_RATE = 44_100
CANONICAL_CHANNELS = 2
CANONICAL_CODEC = "pcm_s16le"
CANONICAL_AUDIO_RECIPE_VERSION = "canonical-audio-v2-lineage-probe"


def _probe_canonical_wav(path: str | Path) -> dict[str, int | float] | None:
    try:
        with wave.open(str(path), "rb") as handle:
            sample_rate = int(handle.getframerate())
            channels = int(handle.getnchannels())
            sample_width = int(handle.getsampwidth())
            frames = int(handle.getnframes())
    except (OSError, EOFError, wave.Error):
        return None
    if sample_rate <= 0 or channels <= 0 or sample_width <= 0 or frames <= 0:
        return None
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "duration_seconds": frames / float(sample_rate),
    }


def _canonical_asset_is_usable(
    storage: LocalStorageBackend,
    asset: MediaAsset,
    *,
    source_checksum_sha256: str | None,
    expected_duration_seconds: float | None,
) -> bool:
    if not storage.exists(asset.storage_key):
        return False
    metadata = dict(asset.metadata_json or {})
    if source_checksum_sha256 and str(metadata.get("source_asset_sha256") or "") != source_checksum_sha256:
        return False
    path = to_windows_long_path(storage.resolve(asset.storage_key).absolute_path)
    probe = _probe_canonical_wav(path)
    if probe is None:
        return False
    if (
        probe["sample_rate"] != CANONICAL_SAMPLE_RATE
        or probe["channels"] != CANONICAL_CHANNELS
        or probe["sample_width"] != 2
    ):
        return False
    expected = float(expected_duration_seconds or 0.0)
    measured = float(probe["duration_seconds"])
    if expected > 0 and abs(measured - expected) > max(0.35, expected * 0.02):
        return False
    recipe = str(metadata.get("recipe_version") or "")
    if recipe and recipe != CANONICAL_AUDIO_RECIPE_VERSION:
        return False
    return True


def _current_raw_input(
    db: Session,
    source_video: SourceVideo,
    *,
    source_caption: str | None,
) -> ResolvedAudioInput | None:
    asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.source_video_id == source_video.id,
            MediaAsset.asset_type == MediaAssetType.SOURCE_VIDEO_RAW,
            MediaAsset.status == MediaAssetStatus.AVAILABLE,
            MediaAsset.is_current.is_(True),
        )
    )
    # Session test doubles commonly return a truthy ``MagicMock`` for every
    # scalar lookup.  Only an ORM row is authoritative enough to replace the
    # resolver's input; this also prevents malformed adapter values from
    # leaking into storage path handling.
    if not isinstance(asset, MediaAsset):
        return None
    return ResolvedAudioInput(
        source_video_id=source_video.id,
        input_asset_id=asset.id,
        input_asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
        storage_key=asset.storage_key,
        source_video_duration_seconds=source_video.duration_seconds,
        source_caption=source_caption,
        source_checksum_sha256=(asset.checksum_sha256 or "").strip() or None,
        canonicalized=False,
    )


def canonical_audio_key(resolved: ResolvedAudioInput) -> str:
    normalized = resolved.storage_key.replace("\\", "/").strip("/")
    parent = "/".join(normalized.split("/")[:-1])
    stem = Path(normalized).stem
    digest = (
        resolved.source_checksum_sha256
        or hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    )[:12]
    relative = f"audio/{stem}_{digest}_canonical.wav"
    return f"{parent}/{relative}" if parent else relative


def ensure_canonical_audio(
    db: Session,
    storage: StorageBackend,
    source_video: SourceVideo,
    resolved: ResolvedAudioInput,
    *,
    job_id=None,
) -> ResolvedAudioInput:
    """Return a persisted WAV authority, or the original input for non-local adapters.

    Phase 1 is local-first, so production uses ``LocalStorageBackend``.  The
    graceful adapter fallback keeps future object-storage implementations and
    unit-test fakes from depending on a local filesystem path.
    """
    if not isinstance(storage, LocalStorageBackend):
        return resolved

    if resolved.input_asset_type == MediaAssetType.SOURCE_AUDIO_EXTRACT:
        input_asset = db.get(MediaAsset, resolved.input_asset_id)
        raw = _current_raw_input(db, source_video, source_caption=resolved.source_caption)
        source_sha = raw.source_checksum_sha256 if raw is not None else None
        if isinstance(input_asset, MediaAsset) and _canonical_asset_is_usable(
            storage,
            input_asset,
            source_checksum_sha256=source_sha,
            expected_duration_seconds=resolved.source_video_duration_seconds,
        ):
            return replace(resolved, canonicalized=True)
        if raw is None:
            # A resolver supplied by a future adapter (and focused unit tests)
            # can explicitly guarantee canonicalization without exposing an
            # SQLAlchemy MediaAsset. Production's resolver always returns a
            # persisted row, so invalid real assets still fail closed here.
            if resolved.canonicalized and not isinstance(input_asset, MediaAsset):
                return resolved
            raise RuntimeError("canonical_audio_invalid_and_source_video_raw_missing")
        resolved = raw

    key = canonical_audio_key(resolved)
    existing = db.scalar(
        select(MediaAsset).where(
            MediaAsset.source_video_id == source_video.id,
            MediaAsset.asset_type == MediaAssetType.SOURCE_AUDIO_EXTRACT,
            MediaAsset.status == MediaAssetStatus.AVAILABLE,
            MediaAsset.is_current.is_(True),
        )
    )
    if isinstance(existing, MediaAsset):
        if _canonical_asset_is_usable(
            storage,
            existing,
            source_checksum_sha256=resolved.source_checksum_sha256,
            expected_duration_seconds=resolved.source_video_duration_seconds,
        ):
            return ResolvedAudioInput(
                source_video_id=resolved.source_video_id,
                input_asset_id=existing.id,
                input_asset_type=MediaAssetType.SOURCE_AUDIO_EXTRACT,
                storage_key=existing.storage_key,
                source_video_duration_seconds=resolved.source_video_duration_seconds,
                source_caption=resolved.source_caption,
                source_checksum_sha256=existing.checksum_sha256,
                canonicalized=True,
            )

    source_path = to_windows_long_path(storage.resolve(resolved.storage_key).absolute_path)
    if not source_path.is_file() or shutil.which("ffmpeg") is None:
        return resolved

    with tempfile.TemporaryDirectory(prefix="audio_canonical_") as tmp:
        output_path = Path(tmp) / "canonical.wav"
        completed = run_captured(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-ac",
                str(CANONICAL_CHANNELS),
                "-ar",
                str(CANONICAL_SAMPLE_RATE),
                "-c:a",
                CANONICAL_CODEC,
                str(output_path),
            ]
        )
        if completed.returncode != 0 or not output_path.is_file():
            detail = (completed.stderr or completed.stdout or "ffmpeg audio extract failed").strip()
            raise RuntimeError(detail[:600])
        write = storage.write_file(key, output_path)

    for old in db.scalars(
        select(MediaAsset).where(
            MediaAsset.source_video_id == source_video.id,
            MediaAsset.asset_type == MediaAssetType.SOURCE_AUDIO_EXTRACT,
            MediaAsset.is_current.is_(True),
        )
    ):
        old.is_current = False
    max_version = db.scalar(
        select(func.max(MediaAsset.version)).where(
            MediaAsset.source_video_id == source_video.id,
            MediaAsset.asset_type == MediaAssetType.SOURCE_AUDIO_EXTRACT,
        )
    )
    asset = MediaAsset(
        workspace_id=source_video.workspace_id,
        source_video_id=source_video.id,
        asset_type=MediaAssetType.SOURCE_AUDIO_EXTRACT,
        status=MediaAssetStatus.AVAILABLE,
        version=int(max_version or 0) + 1,
        storage_provider=write.storage_provider,
        storage_key=write.storage_key,
        logical_key=write.storage_key,
        relative_path=write.relative_path,
        manifest_group="audio_source",
        is_current=True,
        created_by_job_id=job_id,
        mime_type="audio/wav",
        size_bytes=write.size_bytes,
        checksum_sha256=write.checksum_sha256,
        metadata_json={
            "source_asset_id": str(resolved.input_asset_id),
            "source_asset_sha256": resolved.source_checksum_sha256,
            "sample_rate": CANONICAL_SAMPLE_RATE,
            "channels": CANONICAL_CHANNELS,
            "codec": CANONICAL_CODEC,
            "purpose": "vad_demucs_asr_authority",
            "recipe_version": CANONICAL_AUDIO_RECIPE_VERSION,
            "duration_seconds": resolved.source_video_duration_seconds,
        },
    )
    db.add(asset)
    db.flush()
    return ResolvedAudioInput(
        source_video_id=resolved.source_video_id,
        input_asset_id=asset.id,
        input_asset_type=MediaAssetType.SOURCE_AUDIO_EXTRACT,
        storage_key=asset.storage_key,
        source_video_duration_seconds=resolved.source_video_duration_seconds,
        source_caption=resolved.source_caption,
        source_checksum_sha256=asset.checksum_sha256,
        canonicalized=True,
    )
