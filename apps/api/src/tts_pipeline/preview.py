"""Ops TTS speech preview — one short synthesize, no durable job."""

from __future__ import annotations

import base64
import logging
from types import SimpleNamespace
from typing import Any

from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.provider_factory import build_default_tts_provider
from src.tts_pipeline.types import TtsProviderInput, VoiceConfig

logger = logging.getLogger(__name__)

DEFAULT_PREVIEW_MAX_CHARS = 280
DEFAULT_PREVIEW_TEXT = "Xin chào, đây là bản xem trước giọng đọc tiếng Việt."


class PreviewTtsError(ValueError):
    """Invalid preview request."""


def _as_preview_cfg(workspace_tts: Any) -> SimpleNamespace:
    """Draft Ops form always wins for preview (treat as enabled)."""
    src = workspace_tts
    return SimpleNamespace(
        enabled=True,
        provider=str(getattr(src, "provider", "auto") or "auto"),
        voice_id=str(getattr(src, "voice_id", "") or ""),
        speaking_rate=float(getattr(src, "speaking_rate", 1.0) or 1.0),
        language_code=str(getattr(src, "language_code", "vi") or "vi") or "vi",
        model_id=str(getattr(src, "model_id", "") or ""),
        api_key=getattr(src, "api_key", None),
        base_url=str(getattr(src, "base_url", "") or ""),
        timeout_seconds=float(getattr(src, "timeout_seconds", 120.0) or 120.0),
        fallback_provider=str(getattr(src, "fallback_provider", "none") or "none"),
        fallback_voice_id=str(getattr(src, "fallback_voice_id", "") or ""),
        local_backend=str(getattr(src, "local_backend", "auto") or "auto"),
        device=str(getattr(src, "device", "auto") or "auto"),
        cli_binary=str(getattr(src, "cli_binary", "") or ""),
        options_json=dict(getattr(src, "options_json", None) or {}),
        runtime=getattr(src, "runtime", None),
    )


def preview_tts_speech(
    *,
    workspace_tts: Any,
    text: str,
    max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        raise PreviewTtsError("empty_text")
    limit = max(20, min(int(max_chars or DEFAULT_PREVIEW_MAX_CHARS), 500))
    if len(cleaned) > limit:
        cleaned = cleaned[:limit]

    cfg = _as_preview_cfg(workspace_tts)
    provider = build_default_tts_provider(workspace_tts=cfg)
    rate = max(0.5, min(2.0, float(cfg.speaking_rate or 1.0)))

    try:
        output = provider.synthesize(
            TtsProviderInput(
                text=cleaned,
                language_code=cfg.language_code,
                voice_config=VoiceConfig(
                    voice_id=cfg.voice_id,
                    language_code=cfg.language_code,
                    speaking_rate=rate,
                ),
            )
        )
    except TtsPipelineError:
        raise
    except Exception as exc:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
            f"TTS preview failed: {exc}",
        ) from exc

    if not output.audio_bytes:
        raise PreviewTtsError("empty_audio")

    provider_name = str(
        getattr(provider, "provider_name", None)
        or (output.provider_metadata or {}).get("provider")
        or "unknown"
    )
    logger.info(
        "tts_preview_ok",
        extra={
            "provider": provider_name,
            "chars": len(cleaned),
            "duration_seconds": output.duration_seconds,
        },
    )
    return {
        "ok": True,
        "provider": provider_name,
        "detail": f"Preview ready ({len(cleaned)} chars)",
        "mime_type": output.mime_type or "audio/wav",
        "duration_seconds": float(output.duration_seconds or 0.0),
        "audio_base64": base64.b64encode(bytes(output.audio_bytes)).decode("ascii"),
        "warnings": list(output.warnings or []),
        "text": cleaned,
    }
