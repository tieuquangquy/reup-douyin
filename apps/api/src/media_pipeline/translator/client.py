"""OpenAI-compatible client factory (Gemini / Groq / OpenAI / local via LLM_BASE_URL)."""

from __future__ import annotations

from openai import OpenAI

from src.media_pipeline.translator.config import TranslatorSettings


def build_openai_client(settings: TranslatorSettings) -> OpenAI:
    """One client; swap provider by changing Ops Translation AI (or LLM_* fallback)."""
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=float(settings.timeout_seconds or 90.0),
    )
