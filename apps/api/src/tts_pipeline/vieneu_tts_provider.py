from __future__ import annotations

import logging
import wave
from collections.abc import Callable
from io import BytesIO
from typing import Any

from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput

logger = logging.getLogger(__name__)

DEFAULT_VIENEU_VOICE = "Phạm Tuyên"
DEFAULT_VIENEU_STYLE = "tu_nhien"
# ModelScope hosts MOSS under openmoss/*; HF uses OpenMOSS-Team/*.
MOSS_TOKENIZER_MODELSCOPE_ID = "openmoss/MOSS-Audio-Tokenizer-Nano"
LEGACY_EDGE_VOICES = frozenset(
    {
        "",
        "vi_female_placeholder",
        "vi_male_placeholder",
        "vi-VN-HoaiMyNeural",
        "vi-VN-NamMinhNeural",
    }
)

SynthesizeAudioFn = Callable[..., tuple[bytes, float]]


def resolve_vieneu_voice_id(voice_id: str | None) -> str:
    cleaned = (voice_id or "").strip()
    if not cleaned or cleaned in LEGACY_EDGE_VOICES:
        return DEFAULT_VIENEU_VOICE
    return cleaned


def build_vieneu_client_kwargs(
    *,
    local_backend: str,
    model_id: str,
    base_url: str,
    device: str,
) -> dict[str, Any]:
    """Map Ops/env runtime to vieneu SDK kwargs.

    Phase 1: ``auto`` prefers ONNX so Ngọc Linh and other catalog voices work on Windows
    without the PyTorch+ModelScope MOSS tokenizer id mismatch on GPU machines.
    """
    backend = (local_backend or "auto").strip().lower()
    kwargs: dict[str, Any] = {}

    if backend == "remote" and base_url.strip():
        kwargs["mode"] = "remote"
        kwargs["api_base"] = base_url.strip().rstrip("/")
        if model_id.strip():
            kwargs["model_name"] = model_id.strip()
        return kwargs

    if backend in {"onnx", "auto"}:
        kwargs["backend"] = "onnx"
    elif backend == "pytorch":
        kwargs["backend"] = "pytorch"
        kwargs["moss_tokenizer"] = MOSS_TOKENIZER_MODELSCOPE_ID

    if model_id.strip():
        lowered = model_id.strip().lower()
        if "v3" in lowered or "turbo" in lowered:
            kwargs["mode"] = "v3turbo"

    dev = (device or "auto").strip().lower()
    if dev and dev != "auto":
        kwargs["device"] = dev

    return kwargs


class VieNeuTtsProvider:
    """Local/remote Vietnamese TTS via the `vieneu` SDK (VieNeu-TTS)."""

    provider_name = "vieneu"

    def __init__(
        self,
        *,
        synthesize_audio: SynthesizeAudioFn | None = None,
        local_backend: str = "auto",
        device: str = "auto",
        model_id: str = "",
        base_url: str = "",
        options: dict[str, Any] | None = None,
    ):
        self._synthesize_audio = synthesize_audio
        self.local_backend = (local_backend or "auto").strip().lower()
        self.device = (device or "auto").strip().lower()
        self.model_id = (model_id or "").strip()
        self.base_url = (base_url or "").strip()
        self.options = dict(options or {})

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        text = (request.text or "").strip()
        if not text:
            raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, "TTS text is empty")

        voice_id = resolve_vieneu_voice_id(request.voice_config.voice_id)
        speaking_rate = max(0.5, min(2.0, float(request.voice_config.speaking_rate or 1.0)))
        style = str(self.options.get("style") or "tu_nhien").strip() or "tu_nhien"

        try:
            if self._synthesize_audio is not None:
                audio_bytes, duration_seconds = self._synthesize_audio(
                    text=text,
                    voice_id=voice_id,
                    speaking_rate=speaking_rate,
                    style=style,
                )
            else:
                audio_bytes, duration_seconds = self._synthesize_via_vieneu(
                    text=text,
                    voice_id=voice_id,
                    speaking_rate=speaking_rate,
                    style=style,
                )
        except TtsPipelineError:
            raise
        except Exception as exc:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                f"VieNeu TTS failed: {exc}",
            ) from exc

        if not audio_bytes or not audio_bytes.startswith(b"RIFF"):
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "VieNeu did not produce a valid WAV clip",
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
                "voice_id": voice_id,
                "speaking_rate": speaking_rate,
                "style": style,
                "local_backend": self.local_backend,
                "model_id": self.model_id or "v3turbo",
            },
            warnings=warnings,
        )

    def _synthesize_via_vieneu(
        self,
        *,
        text: str,
        voice_id: str,
        speaking_rate: float,
        style: str,
    ) -> tuple[bytes, float]:
        try:
            from vieneu import Vieneu  # type: ignore
        except ImportError as exc:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "vieneu package is not installed. Run: pip install vieneu",
            ) from exc

        kwargs = build_vieneu_client_kwargs(
            local_backend=self.local_backend,
            model_id=self.model_id,
            base_url=self.base_url,
            device=self.device,
        )

        client = Vieneu(**kwargs)
        audio = client.infer(text, voice=voice_id, style=style)
        sample_rate = int(getattr(client, "sample_rate", None) or self.options.get("sample_rate") or 48000)
        if hasattr(audio, "tolist"):
            # numpy array float32
            import struct

            samples = audio
            if hasattr(samples, "astype"):
                pcm = (samples * 32767.0).astype("int16").tobytes()
            else:
                floats = [float(x) for x in samples]
                pcm = b"".join(struct.pack("<h", max(-32768, min(32767, int(v * 32767)))) for v in floats)
            buf = BytesIO()
            with wave.open(buf, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(pcm)
            audio_bytes = buf.getvalue()
            duration_seconds = (len(pcm) / 2) / float(sample_rate)
        elif isinstance(audio, (bytes, bytearray)) and bytes(audio).startswith(b"RIFF"):
            audio_bytes = bytes(audio)
            duration_seconds = _wav_duration_seconds(audio_bytes)
        else:
            # SDK may return path-like or save helper — prefer save to temp via client.save if present
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "VieNeu returned an unsupported audio payload type",
            )

        # speaking_rate: VieNeu may not expose rate; metadata still records requested rate.
        _ = speaking_rate
        return audio_bytes, duration_seconds


def _wav_duration_seconds(audio_bytes: bytes) -> float:
    with wave.open(BytesIO(audio_bytes), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate() or 1
        return frames / float(rate)
