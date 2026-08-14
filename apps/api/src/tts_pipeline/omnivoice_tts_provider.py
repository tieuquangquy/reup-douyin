"""Local TTS via the installed ``omnivoice`` package (k2-fsa / OmniVoice Studio default engine)."""

from __future__ import annotations

import logging
import threading
import wave
from collections.abc import Callable
from io import BytesIO
from typing import Any

from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput

logger = logging.getLogger(__name__)

DEFAULT_OMNIVOICE_MODEL = "k2-fsa/OmniVoice"
DEFAULT_SAMPLE_RATE = 24000

# OmniVoice.generate(instruct=...) only accepts allowlisted voice-design tokens
# (English comma+space, or Chinese full-width comma). Free-form prose fails at runtime.
VALID_ENGLISH_INSTRUCTS = frozenset(
    {
        "american accent",
        "australian accent",
        "british accent",
        "canadian accent",
        "child",
        "chinese accent",
        "elderly",
        "female",
        "high pitch",
        "indian accent",
        "japanese accent",
        "korean accent",
        "low pitch",
        "male",
        "middle-aged",
        "moderate pitch",
        "portuguese accent",
        "russian accent",
        "teenager",
        "very high pitch",
        "very low pitch",
        "whisper",
        "young adult",
    }
)

# Map curated Voice ID presets → OmniVoice allowlisted ``instruct`` strings.
# Vietnamese "north/south" is not in the allowlist; language=vi carries locale.
INSTRUCT_PRESETS: dict[str, str] = {
    "instruct:vi_female_north": "female, young adult",
    "instruct:vi_female_south": "female, young adult",
    "instruct:vi_male_north": "male, young adult",
    "instruct:vi_male_south": "male, young adult",
    "instruct:vi_news": "male, middle-aged",
    "instruct:vi_warm": "female, young adult",
    "instruct:en_female": "female, american accent",
    "instruct:en_male": "male, american accent",
    "instruct:en_british": "female, british accent",
    "alloy": "female, young adult",
    "echo": "male, middle-aged",
    "fable": "female, young adult",
    "onyx": "male, low pitch",
    "nova": "female, high pitch",
    "shimmer": "female, moderate pitch",
}

# Engines in the Ops catalog that are not wired to k2-fsa OmniVoice.generate yet.
UNSUPPORTED_ENGINE_PREFIXES = (
    "cosyvoice",
    "gpt-sovits",
    "voxcpm2",
    "moss",
    "kitten",
    "sherpa",
    "mlx",
    "indextts",
    "supertonic",
    "dots",
    "confucius",
    "omnivoice-gguf",
)

SynthesizeAudioFn = Callable[..., tuple[bytes, float]]

_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, Any] = {}
_INFERENCE_LOCKS: dict[str, threading.Lock] = {}


def resolve_omnivoice_model_id(model_id: str | None) -> str:
    raw = (model_id or "").strip()
    if not raw or raw.lower() in {"omnivoice", "omnivoice-studio", "omnivoice_studio", "auto"}:
        return DEFAULT_OMNIVOICE_MODEL
    if raw.lower().startswith("omnivoice") and "/" not in raw and raw.lower() != "omnivoice-gguf":
        return DEFAULT_OMNIVOICE_MODEL
    return raw


def resolve_omnivoice_instruct(voice_id: str | None) -> str | None:
    cleaned = (voice_id or "").strip()
    if not cleaned or cleaned.lower() in {"auto", "none", "-"}:
        return None
    if cleaned in INSTRUCT_PRESETS:
        return INSTRUCT_PRESETS[cleaned]
    if cleaned.lower().startswith("instruct:"):
        rest = cleaned.split(":", 1)[1].strip()
        if not rest:
            return None
        # Known slug without "instruct:" prefix already handled above; allow
        # raw allowlisted token lists after the prefix.
        return _sanitize_english_instruct(rest)
    if "," in cleaned or cleaned.lower() in VALID_ENGLISH_INSTRUCTS:
        return _sanitize_english_instruct(cleaned)
    return None


def _sanitize_english_instruct(raw: str) -> str | None:
    """Keep only OmniVoice-allowlisted English tokens; drop free-form prose."""
    parts = [p.strip() for p in raw.split(",")]
    kept: list[str] = []
    for part in parts:
        key = part.lower()
        if key in VALID_ENGLISH_INSTRUCTS:
            # Preserve canonical casing from the allowlist set member.
            for token in VALID_ENGLISH_INSTRUCTS:
                if token == key:
                    kept.append(token)
                    break
    if not kept:
        return None
    return ", ".join(kept)


def _engine_supported_for_k2(model_id: str) -> bool:
    lowered = model_id.strip().lower()
    if lowered in {"", "omnivoice", DEFAULT_OMNIVOICE_MODEL.lower(), "k2-fsa/omnivoice"}:
        return True
    if any(lowered.startswith(p) or p in lowered for p in UNSUPPORTED_ENGINE_PREFIXES):
        return False
    # HuggingFace-style OmniVoice checkpoints
    return "omnivoice" in lowered or lowered.startswith("k2-fsa/")


def _wav_bytes_from_tensor(audio: Any, sample_rate: int) -> tuple[bytes, float]:
    import numpy as np

    if hasattr(audio, "detach"):
        tensor = audio.detach().cpu().float()
        samples = tensor.numpy()
    else:
        samples = np.asarray(audio, dtype=np.float32)
    if samples.ndim > 1:
        samples = samples.squeeze()
    if samples.dtype != np.float32:
        samples = samples.astype(np.float32)
    # Clamp and convert to int16 PCM
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 1.0:
        samples = samples / peak
    pcm = (samples * 32767.0).astype(np.int16)
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate) or DEFAULT_SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    duration = float(len(pcm)) / float(sample_rate or DEFAULT_SAMPLE_RATE)
    return buf.getvalue(), duration


def _resolve_device(device: str) -> str:
    import torch

    requested = (device or "auto").strip().lower()
    if requested and requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _get_or_load_model(*, model_id: str, device: str) -> Any:
    import torch
    from omnivoice import OmniVoice  # type: ignore

    key = f"{model_id}|{device}"
    with _MODEL_LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        logger.info("omnivoice_model_loading", extra={"model_id": model_id, "device": device})
        dtype = torch.float16 if device in {"cuda", "mps"} else torch.float32
        model = OmniVoice.from_pretrained(model_id, device_map=device, dtype=dtype)
        _MODEL_CACHE[key] = model
        _INFERENCE_LOCKS.setdefault(key, threading.Lock())
        return model


def _model_inference_lock(*, model_id: str, device: str) -> threading.Lock:
    key = f"{model_id}|{device}"
    with _MODEL_LOCK:
        return _INFERENCE_LOCKS.setdefault(key, threading.Lock())


class OmniVoiceTtsProvider:
    """Synthesize with k2-fsa OmniVoice (default Studio engine)."""

    provider_name = "omnivoice"

    def __init__(
        self,
        *,
        synthesize_audio: SynthesizeAudioFn | None = None,
        model_id: str = "",
        device: str = "auto",
        options: dict[str, Any] | None = None,
    ):
        self._synthesize_audio = synthesize_audio
        self.model_id = resolve_omnivoice_model_id(model_id)
        self.device = (device or "auto").strip().lower() or "auto"
        self.options = dict(options or {})

    @property
    def preferred_batch_size(self) -> int:
        """Choose throughput batch size from real accelerator headroom.

        OmniVoice is autoregressive; on a 4 GB GTX 1650 a batch of four fills
        VRAM but is slower than sequential generation. Keep batching for cards
        with enough memory to benefit and fail conservative elsewhere.
        """

        try:
            import torch

            device = _resolve_device(self.device)
            if device != "cuda" or not torch.cuda.is_available():
                return 1
            total_gb = float(torch.cuda.get_device_properties(0).total_memory) / (1024**3)
            if total_gb >= 10.0:
                return 4
            if total_gb >= 6.0:
                return 2
        except Exception:
            return 1
        return 1

    def warmup(self) -> dict[str, Any]:
        """Make the persistent worker process the single warm model owner."""

        if self._synthesize_audio is not None:
            return {"status": "injected_runtime", "model_id": self.model_id}
        model_id = resolve_omnivoice_model_id(self.model_id)
        if not _engine_supported_for_k2(model_id):
            return {"status": "unsupported_engine", "model_id": model_id}
        device = _resolve_device(self.device)
        key = f"{model_id}|{device}"
        with _MODEL_LOCK:
            was_warm = key in _MODEL_CACHE
        _get_or_load_model(model_id=model_id, device=device)
        return {
            "status": "already_warm" if was_warm else "loaded",
            "model_id": model_id,
            "device": device,
            "owner": "persistent_worker_process",
        }

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        text = (request.text or "").strip()
        if not text:
            raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, "TTS text is empty")

        if not _engine_supported_for_k2(self.model_id):
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                f"Engine '{self.model_id}' is listed in the OmniVoice catalog but only the "
                f"default OmniVoice model ({DEFAULT_OMNIVOICE_MODEL}) is wired for Preview/jobs yet. "
                "Select Model ID = omnivoice or k2-fsa/OmniVoice.",
            )

        speaking_rate = max(0.5, min(2.0, float(request.voice_config.speaking_rate or 1.0)))
        language = (request.language_code or request.voice_config.language_code or "vi").strip() or "vi"
        instruct = resolve_omnivoice_instruct(request.voice_config.voice_id)
        model_id = resolve_omnivoice_model_id(self.model_id)

        try:
            if self._synthesize_audio is not None:
                audio_bytes, duration_seconds = self._synthesize_audio(
                    text=text,
                    language=language,
                    speaking_rate=speaking_rate,
                    instruct=instruct,
                    model_id=model_id,
                )
            else:
                audio_bytes, duration_seconds = self._synthesize_via_omnivoice(
                    text=text,
                    language=language,
                    speaking_rate=speaking_rate,
                    instruct=instruct,
                    model_id=model_id,
                )
        except TtsPipelineError:
            raise
        except Exception as exc:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                f"OmniVoice TTS failed: {exc}",
            ) from exc

        if not audio_bytes or not audio_bytes.startswith(b"RIFF"):
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "OmniVoice did not produce a valid WAV clip",
            )

        warnings: list[str] = []
        if request.target_duration_seconds and duration_seconds > request.target_duration_seconds * 1.2:
            warnings.append("tts_longer_than_slot")

        return TtsProviderOutput(
            audio_bytes=audio_bytes,
            duration_seconds=duration_seconds,
            mime_type="audio/wav",
            file_extension="wav",
            provider_metadata={
                "provider": self.provider_name,
                "voice_id": request.voice_config.voice_id,
                "instruct": instruct or "",
                "speaking_rate": speaking_rate,
                "model_id": model_id,
                "language": language,
            },
            warnings=warnings,
        )

    def synthesize_batch(
        self,
        requests: list[TtsProviderInput],
    ) -> list[TtsProviderOutput]:
        """Generate a bounded batch in one model call.

        OmniVoice accepts list-valued inputs.  Keeping batching here (provider
        boundary) lets the pipeline remain provider-agnostic and fall back to
        the normal per-clip path for test doubles or custom adapters.
        """

        if not requests:
            return []
        if self._synthesize_audio is not None:
            return [self.synthesize(request) for request in requests]
        first = requests[0]
        model_id = resolve_omnivoice_model_id(self.model_id)
        if not _engine_supported_for_k2(model_id):
            return [self.synthesize(request) for request in requests]
        device = _resolve_device(self.device)
        model = _get_or_load_model(model_id=model_id, device=device)
        sample_rate = int(getattr(model, "sampling_rate", None) or DEFAULT_SAMPLE_RATE)
        texts = [(request.text or "").strip() for request in requests]
        if any(not text for text in texts):
            raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, "OmniVoice batch contains empty text")
        languages = [
            (request.language_code or request.voice_config.language_code or "vi").strip() or "vi"
            for request in requests
        ]
        instructs = [resolve_omnivoice_instruct(request.voice_config.voice_id) for request in requests]
        speeds = [
            max(0.5, min(2.0, float(request.voice_config.speaking_rate or 1.0)))
            for request in requests
        ]
        logger.info(
            "omnivoice_synthesize_batch",
            extra={"model_id": model_id, "device": device, "batch_size": len(requests)},
        )
        try:
            with _model_inference_lock(model_id=model_id, device=device):
                audios = model.generate(
                    text=texts,
                    language=languages,
                    instruct=instructs,
                    speed=speeds,
                )
        except Exception as exc:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                f"OmniVoice batch TTS failed: {exc}",
            ) from exc
        if not isinstance(audios, (list, tuple)) or len(audios) != len(requests):
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "OmniVoice batch returned an unexpected audio count",
            )
        outputs: list[TtsProviderOutput] = []
        for request, audio in zip(requests, audios, strict=True):
            audio_bytes, duration_seconds = _wav_bytes_from_tensor(audio, sample_rate)
            if not audio_bytes.startswith(b"RIFF"):
                raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, "OmniVoice batch returned invalid WAV")
            voice_id = request.voice_config.voice_id
            outputs.append(
                TtsProviderOutput(
                    audio_bytes=audio_bytes,
                    duration_seconds=duration_seconds,
                    mime_type="audio/wav",
                    file_extension="wav",
                    provider_metadata={
                        "provider": self.provider_name,
                        "voice_id": voice_id,
                        "instruct": resolve_omnivoice_instruct(voice_id) or "",
                        "speaking_rate": float(request.voice_config.speaking_rate),
                        "model_id": model_id,
                        "language": request.language_code or "vi",
                        "batch_size": len(requests),
                    },
                    warnings=[],
                )
            )
        return outputs

    def _synthesize_via_omnivoice(
        self,
        *,
        text: str,
        language: str,
        speaking_rate: float,
        instruct: str | None,
        model_id: str,
    ) -> tuple[bytes, float]:
        try:
            import omnivoice  # noqa: F401
        except ImportError as exc:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "omnivoice package is not installed. Install OmniVoice-Studio / omnivoice via Ops.",
            ) from exc

        device = _resolve_device(self.device)
        model = _get_or_load_model(model_id=model_id, device=device)
        sample_rate = int(getattr(model, "sampling_rate", None) or DEFAULT_SAMPLE_RATE)

        kwargs: dict[str, Any] = {
            "text": text,
            "language": language,
            "speed": speaking_rate,
        }
        if instruct:
            kwargs["instruct"] = instruct

        logger.info(
            "omnivoice_synthesize",
            extra={"model_id": model_id, "device": device, "has_instruct": bool(instruct)},
        )
        with _model_inference_lock(model_id=model_id, device=device):
            audios = model.generate(**kwargs)
        if not audios:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "OmniVoice generate() returned no audio",
            )
        return _wav_bytes_from_tensor(audios[0], sample_rate)


def reset_omnivoice_model_cache_for_tests() -> None:
    with _MODEL_LOCK:
        _MODEL_CACHE.clear()
        _INFERENCE_LOCKS.clear()
