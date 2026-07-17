"""Run Demucs two-stem vocal extract for ASR-quality DialogueBeats."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DEMUCS_MODEL = "htdemucs"
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}

DemucsRunner = Callable[..., Path]


def demucs_is_importable() -> bool:
    try:
        import demucs  # noqa: F401

        return True
    except Exception:
        return False


def ensure_wav_for_demucs(input_path: Path, work_dir: Path, *, ffmpeg_binary: str = "ffmpeg") -> Path:
    """Return a wav path Demucs can read; extract via ffmpeg when input is video/container."""
    suffix = input_path.suffix.lower()
    if suffix in AUDIO_SUFFIXES and suffix == ".wav":
        return input_path
    if suffix in AUDIO_SUFFIXES:
        return input_path
    if shutil.which(ffmpeg_binary) is None:
        raise RuntimeError("ffmpeg binary not found on PATH; cannot extract audio for Demucs")
    wav_path = work_dir / f"{input_path.stem}_extract.wav"
    command = [
        ffmpeg_binary,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
        str(wav_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not wav_path.exists():
        detail = (completed.stderr or completed.stdout or "ffmpeg extract failed").strip()
        raise RuntimeError(detail[:500])
    return wav_path


def run_demucs_vocals(
    *,
    input_path: Path,
    output_dir: Path,
    model_name: str = DEFAULT_DEMUCS_MODEL,
) -> Path:
    """
    Execute Demucs two-stem separation and return path to vocals.wav.

    Uses `python -m demucs` so we do not require a separate CLI install.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="demucs_work_"))
    try:
        wav_input = ensure_wav_for_demucs(input_path, work_dir)
        command = [
            sys.executable,
            "-m",
            "demucs",
            "--two-stems=vocals",
            "-n",
            model_name,
            "-o",
            str(output_dir),
            str(wav_input),
        ]
        logger.info(
            "demucs_separate_started",
            extra={"input": str(wav_input), "model": model_name, "output_dir": str(output_dir)},
        )
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "demucs failed").strip()
            raise RuntimeError(detail[:800])
        vocals = _find_vocals_wav(output_dir, model_name=model_name, track_stem=wav_input.stem)
        if vocals is None or not vocals.exists():
            raise RuntimeError(f"Demucs finished but vocals.wav not found under {output_dir}")
        logger.info("demucs_separate_finished", extra={"vocals_path": str(vocals)})
        return vocals
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _find_vocals_wav(output_dir: Path, *, model_name: str, track_stem: str) -> Path | None:
    candidates = [
        output_dir / model_name / track_stem / "vocals.wav",
        output_dir / "htdemucs" / track_stem / "vocals.wav",
        output_dir / "htdemucs_ft" / track_stem / "vocals.wav",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = list(output_dir.rglob("vocals.wav"))
    return matches[0] if matches else None


def vocal_storage_key_for_input(input_storage_key: str) -> str:
    normalized = input_storage_key.replace("\\", "/").strip("/")
    parent = "/".join(normalized.split("/")[:-1])
    stem = Path(normalized).stem
    relative = f"audio/{stem}_vocals.wav"
    return f"{parent}/{relative}" if parent else relative
