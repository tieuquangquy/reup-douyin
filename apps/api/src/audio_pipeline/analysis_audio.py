"""Reusable low-cost audio intermediate for the analysis-only stages.

The canonical source remains 44.1 kHz stereo PCM for Demucs and archival
provenance.  Silero and the target-speech classifier only need a deterministic
16 kHz mono waveform; materialising it once avoids two independent ffmpeg/
resampling passes per analysis run.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
import wave

from src.audio_pipeline.demucs_runner import run_captured
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend, to_windows_long_path


ANALYSIS_AUDIO_RECIPE_VERSION = "analysis-audio-v1-16khz-mono-pcm"
ANALYSIS_AUDIO_SAMPLE_RATE = 16_000
ANALYSIS_AUDIO_CHANNELS = 1
ANALYSIS_AUDIO_CACHE_PREFIX = ".cache/audio-analysis/"
ANALYSIS_AUDIO_CACHE_MAX_BYTES = 5 * 1024 * 1024 * 1024
ANALYSIS_AUDIO_CACHE_MIN_AGE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class AnalysisAudioIntermediate:
    storage_key: str
    checksum_sha256: str | None
    cache_hit: bool
    recipe_version: str = ANALYSIS_AUDIO_RECIPE_VERSION

    def to_dict(self) -> dict:
        return {
            "storage_key": self.storage_key,
            "checksum_sha256": self.checksum_sha256,
            "cache_hit": self.cache_hit,
            "recipe_version": self.recipe_version,
            "sample_rate": ANALYSIS_AUDIO_SAMPLE_RATE,
            "channels": ANALYSIS_AUDIO_CHANNELS,
            "codec": "pcm_s16le",
        }


def _valid_analysis_wav(path: str | Path) -> bool:
    try:
        with wave.open(str(path), "rb") as handle:
            return (
                handle.getframerate() == ANALYSIS_AUDIO_SAMPLE_RATE
                and handle.getnchannels() == ANALYSIS_AUDIO_CHANNELS
                and handle.getsampwidth() == 2
                and handle.getnframes() > 0
            )
    except (OSError, EOFError, wave.Error):
        return False


def prune_analysis_audio_cache(
    storage: LocalStorageBackend,
    *,
    max_bytes: int = ANALYSIS_AUDIO_CACHE_MAX_BYTES,
    min_age_seconds: float = ANALYSIS_AUDIO_CACHE_MIN_AGE_SECONDS,
) -> dict[str, int]:
    """Bound the regenerable analysis cache without touching source assets.

    Only files under the explicit ``.cache/audio-analysis`` namespace are
    eligible.  The oldest files past the age floor are removed first; source
    media and DB-registered assets are never considered.
    """

    if max_bytes <= 0:
        return {"scanned": 0, "deleted": 0, "bytes_reclaimed": 0}
    root = to_windows_long_path(storage.resolve(ANALYSIS_AUDIO_CACHE_PREFIX).absolute_path)
    if not root.exists():
        return {"scanned": 0, "deleted": 0, "bytes_reclaimed": 0}
    now = time.time()
    candidates: list[tuple[float, int, str]] = []
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        size = int(stat.st_size)
        total += size
        if now - stat.st_mtime >= max(0.0, float(min_age_seconds)):
            key = str(path.relative_to(to_windows_long_path(storage.root))).replace("\\", "/")
            candidates.append((stat.st_mtime, size, key))
    deleted = 0
    reclaimed = 0
    for _mtime, size, key in sorted(candidates):
        if total <= max_bytes:
            break
        try:
            storage.delete(key)
        except OSError:
            continue
        total -= size
        deleted += 1
        reclaimed += size
    return {"scanned": len(candidates), "deleted": deleted, "bytes_reclaimed": reclaimed}


def materialize_analysis_audio(
    storage: StorageBackend,
    *,
    source_storage_key: str,
    source_checksum_sha256: str | None,
    cache_max_bytes: int = ANALYSIS_AUDIO_CACHE_MAX_BYTES,
    cache_min_age_seconds: float = ANALYSIS_AUDIO_CACHE_MIN_AGE_SECONDS,
) -> AnalysisAudioIntermediate | None:
    """Create/reuse the mono waveform used by VAD and acoustic classification.

    Non-local storage adapters deliberately return ``None`` and retain their
    existing provider path.  This keeps the storage boundary SaaS-ready while
    making local-first runs fast and deterministic.
    """

    if not isinstance(storage, LocalStorageBackend) or shutil.which("ffmpeg") is None:
        return None
    source_path = to_windows_long_path(storage.resolve(source_storage_key).absolute_path)
    if not source_path.is_file():
        return None
    source_meta = storage.metadata(source_storage_key)
    source_sha = source_checksum_sha256 or source_meta.checksum_sha256
    if not source_sha:
        return None
    identity = {
        "recipe_version": ANALYSIS_AUDIO_RECIPE_VERSION,
        "source_storage_key": source_storage_key,
        "source_sha256": source_sha,
        "sample_rate": ANALYSIS_AUDIO_SAMPLE_RATE,
        "channels": ANALYSIS_AUDIO_CHANNELS,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    key = f".cache/audio-analysis/{digest[:2]}/{digest}.wav"
    if storage.exists(key):
        metadata = storage.metadata(key)
        cached_path = to_windows_long_path(storage.resolve(key).absolute_path)
        if metadata.exists and metadata.checksum_sha256 and _valid_analysis_wav(cached_path):
            return AnalysisAudioIntermediate(
                storage_key=key,
                checksum_sha256=metadata.checksum_sha256,
                cache_hit=True,
            )

    with tempfile.TemporaryDirectory(prefix="analysis_audio_") as temporary:
        output = Path(temporary) / "analysis.wav"
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
                str(ANALYSIS_AUDIO_CHANNELS),
                "-ar",
                str(ANALYSIS_AUDIO_SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                str(output),
            ]
        )
        if completed.returncode != 0 or not output.is_file():
            return None
        if not _valid_analysis_wav(output):
            return None
        write = storage.write_file(key, output)
    try:
        prune_analysis_audio_cache(
            storage,
            max_bytes=cache_max_bytes,
            min_age_seconds=cache_min_age_seconds,
        )
    except OSError:
        # Cache housekeeping must never turn a successful analysis decode into
        # a failed job (for example, when another worker owns a file handle).
        pass
    return AnalysisAudioIntermediate(
        storage_key=write.storage_key,
        checksum_sha256=write.checksum_sha256,
        cache_hit=False,
    )
