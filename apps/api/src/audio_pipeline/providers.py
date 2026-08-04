from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.audio_pipeline.demucs_runner import (
    DEFAULT_DEMUCS_MODEL,
    DemucsStemPaths,
    background_storage_key_for_input,
    demucs_is_importable,
    run_demucs_two_stems,
    vocal_storage_key_for_input,
)
from src.audio_pipeline.speech_budget import (
    DEFAULT_VI_UNITS_PER_SECOND,
    count_spoken_units,
)
from src.audio_pipeline.silero_vad_runner import (
    SpeechSummary,
    run_silero_speech_summary,
    silero_is_importable,
)
from src.audio_pipeline.types import (
    SourceSeparationResult,
    TranscriptionUnit,
    TranslationDraftSegment,
    TranslationPreset,
    VadResult,
)
from src.core.settings import get_settings
from src.storage.local import LocalStorageBackend, to_windows_long_path
from src.storage.base import StorageBackend

logger = logging.getLogger(__name__)

DemucsRunnerFn = Callable[..., object]
SileroRunnerFn = Callable[[str], SpeechSummary]


class SourceSeparationProvider(Protocol):
    provider_name: str

    def separate(self, audio_storage_key: str) -> SourceSeparationResult:
        ...


class VadProvider(Protocol):
    provider_name: str

    def detect(
        self,
        audio_storage_key: str,
        *,
        duration_seconds: float | None = None,
        source_caption: str | None = None,
    ) -> VadResult:
        ...


class SttProvider(Protocol):
    provider_name: str

    def transcribe(
        self,
        audio_storage_key: str,
        *,
        source_caption: str | None = None,
        duration_seconds: float | None = None,
    ) -> list[TranscriptionUnit]:
        ...


class TranslationProvider(Protocol):
    provider_name: str

    def translate(
        self,
        source_text: str,
        *,
        preset: TranslationPreset,
        duration_budget_seconds: float,
        source_confidence: float | None = None,
    ) -> TranslationDraftSegment:
        ...


@dataclass
class FallbackSourceSeparationProvider:
    provider_name: str = "fallback_no_separation"

    def separate(self, audio_storage_key: str) -> SourceSeparationResult:
        return SourceSeparationResult(
            vocal_asset_id=None,
            background_asset_id=None,
            transcription_storage_key=audio_storage_key,
            fallback_used=True,
            difficulty_flags=["source_separation_unavailable"],
            metadata={"provider": self.provider_name},
        )


@dataclass
class DemucsSourceSeparationProvider:
    """Demucs two-stem vocal extract for ASR; falls back when demucs/torch unavailable."""

    provider_name: str = "demucs_htdemucs"
    fallback: SourceSeparationProvider | None = None
    storage: StorageBackend | None = None
    runner: DemucsRunnerFn | None = None
    model_name: str = DEFAULT_DEMUCS_MODEL
    demucs_importable: bool | None = None

    def separate(self, audio_storage_key: str) -> SourceSeparationResult:
        fallback = self.fallback or FallbackSourceSeparationProvider()
        importable = demucs_is_importable() if self.demucs_importable is None else self.demucs_importable
        if not importable:
            result = fallback.separate(audio_storage_key)
            flags = list(result.difficulty_flags)
            if "source_separation_unavailable" not in flags:
                flags.append("source_separation_unavailable")
            flags.append("demucs_unavailable")
            return SourceSeparationResult(
                vocal_asset_id=result.vocal_asset_id,
                background_asset_id=result.background_asset_id,
                transcription_storage_key=result.transcription_storage_key,
                fallback_used=True,
                difficulty_flags=flags,
                metadata={
                    **result.metadata,
                    "requested_provider": self.provider_name,
                    "fallback_provider": fallback.provider_name,
                },
            )

        storage = self.storage or LocalStorageBackend(get_settings().local_storage_root)
        runner = self.runner or run_demucs_two_stems
        try:
            resolved = storage.resolve(audio_storage_key)
            input_path = resolved.absolute_path
            if not to_windows_long_path(input_path).exists():
                raise FileNotFoundError(f"Audio input missing for separation: {audio_storage_key}")

            vocal_key = vocal_storage_key_for_input(audio_storage_key)
            background_key = background_storage_key_for_input(audio_storage_key)
            if storage.exists(vocal_key) and storage.exists(background_key):
                logger.info(
                    "demucs_vocal_cache_hit",
                    extra={"input_key": audio_storage_key, "vocal_key": vocal_key},
                )
                return SourceSeparationResult(
                    vocal_asset_id=None,
                    background_asset_id=None,
                    transcription_storage_key=vocal_key,
                    fallback_used=False,
                    difficulty_flags=[],
                    metadata={
                        "provider": self.provider_name,
                        "model": self.model_name,
                        "cache_hit": True,
                        "vocal_storage_key": vocal_key,
                        "background_storage_key": background_key,
                    },
                )

            with tempfile.TemporaryDirectory(prefix="demucs_out_") as out_tmp:
                stem_result = runner(
                    input_path=input_path,
                    output_dir=Path(out_tmp),
                    model_name=self.model_name,
                )
                if isinstance(stem_result, DemucsStemPaths):
                    vocals_path = stem_result.vocals
                    background_path = stem_result.background
                else:
                    vocals_path = Path(stem_result)
                    background_path = None
                vocal_bytes = Path(vocals_path).read_bytes()
                background_bytes = (
                    Path(background_path).read_bytes()
                    if background_path is not None and Path(background_path).is_file()
                    else None
                )
            write_result = storage.write_bytes(vocal_key, vocal_bytes)
            background_write = (
                storage.write_bytes(background_key, background_bytes)
                if background_bytes
                else None
            )
            logger.info(
                "demucs_vocal_persisted",
                extra={
                    "input_key": audio_storage_key,
                    "vocal_key": write_result.storage_key,
                    "size_bytes": write_result.size_bytes,
                },
            )
            return SourceSeparationResult(
                vocal_asset_id=None,
                background_asset_id=None,
                transcription_storage_key=write_result.storage_key,
                fallback_used=False,
                difficulty_flags=[],
                metadata={
                    "provider": self.provider_name,
                    "model": self.model_name,
                    "cache_hit": False,
                    "vocal_storage_key": write_result.storage_key,
                    "background_storage_key": (
                        background_write.storage_key if background_write is not None else None
                    ),
                },
            )
        except Exception as exc:
            logger.exception(
                "demucs_separate_failed",
                extra={"input_key": audio_storage_key, "error": str(exc)},
            )
            result = fallback.separate(audio_storage_key)
            flags = list(result.difficulty_flags)
            if "source_separation_unavailable" not in flags:
                flags.append("source_separation_unavailable")
            flags.append("demucs_failed")
            return SourceSeparationResult(
                vocal_asset_id=result.vocal_asset_id,
                background_asset_id=result.background_asset_id,
                transcription_storage_key=result.transcription_storage_key,
                fallback_used=True,
                difficulty_flags=flags,
                metadata={
                    **result.metadata,
                    "requested_provider": self.provider_name,
                    "fallback_provider": fallback.provider_name,
                    "error": str(exc)[:300],
                },
            )


@dataclass
class FixedVadProvider:
    """Deterministic VAD for tests and injected overrides."""

    has_speech: bool = True
    speech_ratio: float | None = None
    provider_name: str = "fixed_vad"

    def detect(
        self,
        audio_storage_key: str,
        *,
        duration_seconds: float | None = None,
        source_caption: str | None = None,
    ) -> VadResult:
        return VadResult(
            has_speech=self.has_speech,
            speech_ratio=self.speech_ratio if self.speech_ratio is not None else (1.0 if self.has_speech else 0.0),
            difficulty_flags=[] if self.has_speech else ["skip_dubbing", "no_speech_detected"],
            metadata={
                "provider": self.provider_name,
                "audio_storage_key": audio_storage_key,
                "duration_seconds": duration_seconds,
                "source_caption_present": bool(source_caption and source_caption.strip()),
            },
        )


@dataclass
class HeuristicVadProvider:
    """
    Free, dependency-light speech gate when Silero is unavailable.

    Conservative: assume speech unless duration is missing/near-zero, so we do not
    accidentally skip dubbing. Real speech ratio comes from Silero when installed.
    """

    provider_name: str = "heuristic_vad"
    min_duration_seconds: float = 0.4

    def detect(
        self,
        audio_storage_key: str,
        *,
        duration_seconds: float | None = None,
        source_caption: str | None = None,
    ) -> VadResult:
        duration = float(duration_seconds or 0.0)
        if duration > 0 and duration < self.min_duration_seconds:
            return VadResult(
                has_speech=False,
                speech_ratio=0.0,
                difficulty_flags=["skip_dubbing", "no_speech_detected", "duration_too_short"],
                metadata={"provider": self.provider_name, "audio_storage_key": audio_storage_key, "duration_seconds": duration},
            )
        return VadResult(
            has_speech=True,
            speech_ratio=None,
            difficulty_flags=["vad_heuristic_assume_speech"],
            metadata={
                "provider": self.provider_name,
                "audio_storage_key": audio_storage_key,
                "duration_seconds": duration_seconds,
                "source_caption_present": bool(source_caption and source_caption.strip()),
            },
        )


@dataclass
class SileroVadProvider:
    """Measured speech gate; falls back to HeuristicVadProvider when Silero cannot run.

    ``min_speech_seconds`` keeps a stray cough or jingle vocal from opening a dubbing
    lane, and works the same for a 10s clip and a 3min clip because it is an absolute
    floor rather than a ratio tuned to one video length.
    """

    provider_name: str = "silero_vad"
    fallback: VadProvider | None = None
    storage: StorageBackend | None = None
    runner: SileroRunnerFn | None = None
    silero_importable: bool | None = None
    min_speech_seconds: float = 0.8

    def detect(
        self,
        audio_storage_key: str,
        *,
        duration_seconds: float | None = None,
        source_caption: str | None = None,
    ) -> VadResult:
        fallback = self.fallback or HeuristicVadProvider()
        importable = silero_is_importable() if self.silero_importable is None else self.silero_importable
        if not importable:
            return self._fallback_result(
                fallback,
                audio_storage_key,
                duration_seconds=duration_seconds,
                source_caption=source_caption,
                extra_flag="silero_unavailable",
            )

        try:
            storage = self.storage or LocalStorageBackend(get_settings().local_storage_root)
            audio_path = storage.resolve(audio_storage_key).absolute_path
            runner = self.runner or run_silero_speech_summary
            summary = runner(audio_path)
        except Exception as exc:
            logger.exception(
                "silero_vad_failed",
                extra={"audio_storage_key": audio_storage_key, "error": str(exc)},
            )
            return self._fallback_result(
                fallback,
                audio_storage_key,
                duration_seconds=duration_seconds,
                source_caption=source_caption,
                extra_flag="silero_failed",
                error=str(exc)[:300],
            )

        total_seconds = summary.audio_seconds or float(duration_seconds or 0.0)
        speech_ratio = round(summary.speech_seconds / total_seconds, 4) if total_seconds > 0 else 0.0
        has_speech = summary.speech_seconds >= self.min_speech_seconds
        flags = ["silero_vad_executed"]
        if not has_speech:
            flags.extend(["skip_dubbing", "no_speech_detected"])
            if summary.speech_seconds > 0:
                flags.append("speech_below_threshold")
        return VadResult(
            has_speech=has_speech,
            speech_ratio=speech_ratio,
            difficulty_flags=flags,
            metadata={
                "provider": self.provider_name,
                "audio_storage_key": audio_storage_key,
                "duration_seconds": duration_seconds,
                "speech_seconds": summary.speech_seconds,
                "audio_seconds": summary.audio_seconds,
                "speech_segment_count": summary.segment_count,
                "min_speech_seconds": self.min_speech_seconds,
                "source_caption_present": bool(source_caption and source_caption.strip()),
            },
        )

    def _fallback_result(
        self,
        fallback: VadProvider,
        audio_storage_key: str,
        *,
        duration_seconds: float | None,
        source_caption: str | None,
        extra_flag: str,
        error: str | None = None,
    ) -> VadResult:
        result = fallback.detect(
            audio_storage_key,
            duration_seconds=duration_seconds,
            source_caption=source_caption,
        )
        flags = list(result.difficulty_flags)
        if extra_flag not in flags:
            flags.append(extra_flag)
        metadata = {
            **result.metadata,
            "requested_provider": self.provider_name,
            "fallback_provider": fallback.provider_name,
        }
        if error is not None:
            metadata["error"] = error
        return VadResult(
            has_speech=result.has_speech,
            speech_ratio=result.speech_ratio,
            difficulty_flags=flags,
            metadata=metadata,
        )


def build_default_vad_provider() -> VadProvider:
    return SileroVadProvider()


def build_default_separation_provider() -> SourceSeparationProvider:
    return DemucsSourceSeparationProvider()


@dataclass
class CaptionFallbackSttProvider:
    provider_name: str = "caption_fallback_stt"

    def transcribe(
        self,
        audio_storage_key: str,
        *,
        source_caption: str | None = None,
        duration_seconds: float | None = None,
    ) -> list[TranscriptionUnit]:
        if not source_caption:
            return []
        end_seconds = max(1.0, duration_seconds or 1.0)
        return [
            TranscriptionUnit(
                text=source_caption,
                start_seconds=0.0,
                end_seconds=end_seconds,
                confidence=0.55,
                flags=["caption_fallback", "likely_mistranscribed"],
                raw_payload={
                    "provider": self.provider_name,
                    "audio_storage_key": audio_storage_key,
                    "source": "source_video.caption",
                },
            )
        ]


@dataclass
class PlaceholderVietnameseTranslationProvider:
    provider_name: str = "placeholder_vi_translation"

    def translate(
        self,
        source_text: str,
        *,
        preset: TranslationPreset,
        duration_budget_seconds: float,
        source_confidence: float | None = None,
    ) -> TranslationDraftSegment:
        text = _placeholder_translation(source_text, preset)
        estimated_duration = estimate_tts_duration_seconds(text)
        flags: list[str] = ["provider_placeholder"]
        if source_confidence is not None and source_confidence < 0.65:
            flags.append("low_confidence_source")
        if estimated_duration > duration_budget_seconds * 1.2:
            flags.append("translation_too_long_for_slot")
        if duration_budget_seconds < 0.8:
            flags.append("awkward_short_segment")
        return TranslationDraftSegment(
            segment_index=0,
            translated_text=text,
            translation_preset=preset,
            duration_budget_seconds=duration_budget_seconds,
            estimated_tts_duration_seconds=estimated_duration,
            quality_flags=flags,
            metadata={"provider": self.provider_name},
        )


def estimate_tts_duration_seconds(text: str) -> float:
    # Advisory only; synthesized audio remains the duration authority.
    return max(0.6, count_spoken_units(text) / DEFAULT_VI_UNITS_PER_SECOND)


def _placeholder_translation(source_text: str, preset: TranslationPreset) -> str:
    prefix_by_preset = {
        TranslationPreset.LITERAL_SAFE: "Ban dich sat nghia can review:",
        TranslationPreset.NATURAL_VIRAL: "Ban dich tu nhien can review:",
        TranslationPreset.AFFILIATE_SOFT_SELL: "Ban dich affiliate mem can review:",
    }
    return f"{prefix_by_preset[preset]} {source_text.strip()}"
