"""Canonicalize provider audio before temporal fitting and persistence."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.services.narration_assembler import normalize_wav_bytes


_EXTENSION_BY_MIME = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
    "audio/flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


def canonicalize_provider_audio(
    content: bytes,
    *,
    mime_type: str | None,
    file_extension: str | None,
    ffmpeg_binary: str = "ffmpeg",
) -> tuple[bytes, float, dict[str, object]]:
    """Return validated mono PCM WAV at the narration authority sample rate.

    Providers are allowed to transport MP3/OGG/FLAC/etc. The temporal pipeline
    itself is deliberately WAV-only, so decoding happens once at this boundary
    before silence trimming, duration measurement, caching or assembly.
    """

    if not content:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
            "TTS provider returned empty audio.",
        )

    source_format = _source_format(content, mime_type, file_extension)
    if _looks_like_wav(content):
        try:
            normalized, duration = normalize_wav_bytes(content)
        except TtsPipelineError as exc:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                f"TTS provider returned an invalid WAV payload: {exc.message}",
            ) from exc
        return normalized, duration, {
            "schema_version": "tts_provider_audio_normalization_v1",
            "source_format": source_format,
            "converted": False,
            "output_format": "wav_pcm_s16le_48000_mono",
        }

    resolved_ffmpeg = shutil.which(ffmpeg_binary)
    if not resolved_ffmpeg:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
            "TTS provider returned compressed audio but FFmpeg is unavailable for local WAV normalization.",
        )

    suffix = _input_suffix(content, mime_type, file_extension)
    with tempfile.TemporaryDirectory(prefix="reup_tts_decode_") as temp_root:
        root = Path(temp_root)
        input_path = root / f"provider_audio{suffix}"
        output_path = root / "provider_audio.wav"
        input_path.write_bytes(content)
        completed = subprocess.run(
            [
                resolved_ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(input_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ac",
                "1",
                "-ar",
                "48000",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0 or not output_path.is_file():
            detail = (completed.stderr or completed.stdout or "FFmpeg decode failed").strip()
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                f"Unable to decode TTS provider audio ({source_format}): {detail[:400]}",
            )
        decoded = output_path.read_bytes()

    try:
        normalized, duration = normalize_wav_bytes(decoded)
    except TtsPipelineError as exc:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
            f"Decoded TTS audio is not valid PCM WAV: {exc.message}",
        ) from exc
    return normalized, duration, {
        "schema_version": "tts_provider_audio_normalization_v1",
        "source_format": source_format,
        "converted": True,
        "decoder": "ffmpeg",
        "output_format": "wav_pcm_s16le_48000_mono",
    }


def _looks_like_wav(content: bytes) -> bool:
    return len(content) >= 12 and content[:4] in {b"RIFF", b"RF64"} and content[8:12] == b"WAVE"


def _source_format(content: bytes, mime_type: str | None, file_extension: str | None) -> str:
    if _looks_like_wav(content):
        return "wav"
    if content.startswith(b"ID3") or content[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "mp3"
    if content.startswith(b"OggS"):
        return "ogg"
    if content.startswith(b"fLaC"):
        return "flac"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "mp4_audio"
    extension = str(file_extension or "").strip().lower().lstrip(".")
    if extension:
        return extension
    mime = str(mime_type or "").split(";", 1)[0].strip().lower()
    return mime or "unknown"


def _input_suffix(content: bytes, mime_type: str | None, file_extension: str | None) -> str:
    detected = _source_format(content, mime_type, file_extension)
    if detected == "mp3":
        return ".mp3"
    if detected == "ogg":
        return ".ogg"
    if detected == "flac":
        return ".flac"
    if detected == "mp4_audio":
        return ".m4a"
    extension = str(file_extension or "").strip().lower().lstrip(".")
    if extension.isalnum() and len(extension) <= 8:
        return f".{extension}"
    mime = str(mime_type or "").split(";", 1)[0].strip().lower()
    return _EXTENSION_BY_MIME.get(mime, ".bin")
