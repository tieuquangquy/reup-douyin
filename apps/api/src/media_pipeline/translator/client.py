"""Caption LLM client factory with additive native-provider adapters."""

from __future__ import annotations

from openai import OpenAI

from src.media_pipeline.translator.config import TranslatorSettings
from src.audio_pipeline.google_cloud_genai import build_google_cloud_caption_client


def build_openai_client(settings: TranslatorSettings) -> OpenAI:
    """Build the Caption chat client while preserving the legacy public factory name.

    Existing providers still return the exact OpenAI SDK client. Only the new
    google_cloud provider returns a native Google Gen AI SDK adapter.
    """
    if settings.provider == "google_cloud":
        return build_google_cloud_caption_client(
            api_key=settings.api_key,
            model=settings.model_name,
            region=settings.region,
            timeout_seconds=settings.timeout_seconds,
        )  # type: ignore[return-value]
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=float(settings.timeout_seconds or 90.0),
    )
