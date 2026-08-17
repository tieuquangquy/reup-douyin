"""Resolve caption-translator settings from Ops Caption AI settings (workspace DB)."""

from __future__ import annotations

import logging
import os
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.media_pipeline.translator.config import (
    DEFAULT_TRANSLATION_SYSTEM_PROMPT,
    ENV_SYSTEM_PROMPT,
    TranslatorSettings,
    load_translator_settings,
)
from src.media_pipeline.translator.errors import TranslatorError, TranslatorErrorCode
from src.services.workspace_settings_service import TranslationAiConfig, WorkspaceSettingsService
from src.audio_pipeline.google_cloud_genai import (
    GOOGLE_CLOUD_DEFAULT_MODEL,
    GOOGLE_CLOUD_DEFAULT_REGION,
)

logger = logging.getLogger(__name__)

GEMINI_OPENAI_COMPAT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"


def _resolve_system_prompt(db_prompt: str | None) -> str:
    text = (db_prompt or "").strip()
    if text:
        return text
    env_prompt = os.environ.get(ENV_SYSTEM_PROMPT, "").strip()
    return env_prompt or DEFAULT_TRANSLATION_SYSTEM_PROMPT


def _settings_from_openai_compatible(
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout_seconds: float,
    system_prompt: str,
    source: str,
) -> TranslatorSettings:
    if not api_key or not model:
        raise TranslatorError(
            TranslatorErrorCode.CONFIG_MISSING,
            "Ops Caption AI (openai_compatible) needs API key + model. "
            "Save them under Ops Console → Caption AI settings.",
        )
    return TranslatorSettings(
        api_key=api_key,
        base_url=(base_url or DEFAULT_OPENAI_BASE).rstrip("/"),
        model_name=model,
        system_prompt=system_prompt,
        timeout_seconds=float(timeout_seconds or 90.0),
        source=source,
        provider="openai_compatible",
    )


def _map_workspace_ai_to_settings(
    ai: TranslationAiConfig,
    *,
    system_prompt: str,
    env_settings: Any,
) -> TranslatorSettings:
    """Map Ops Caption AI row → OpenAI-SDK TranslatorSettings."""
    provider = str(ai.provider or "auto").strip().lower()
    api_key = (ai.api_key or "").strip()
    base_url = (ai.base_url or "").strip()
    model = (ai.model or "").strip()
    timeout = float(ai.timeout_seconds or 90.0)
    region = str(ai.region or GOOGLE_CLOUD_DEFAULT_REGION).strip() or GOOGLE_CLOUD_DEFAULT_REGION

    if provider in {"placeholder", "off", "none"}:
        raise TranslatorError(
            TranslatorErrorCode.CONFIG_MISSING,
            "Ops Caption AI provider is placeholder — pick openai_compatible / gemini / ollama.",
        )

    if provider == "google_cloud":
        chosen_model = model or GOOGLE_CLOUD_DEFAULT_MODEL
        if not api_key:
            raise TranslatorError(
                TranslatorErrorCode.CONFIG_MISSING,
                "Ops Caption AI (google_cloud) needs a Google Cloud API key. "
                "Save it under Ops Console → Caption AI settings.",
            )
        return TranslatorSettings(
            api_key=api_key,
            base_url="",
            model_name=chosen_model,
            system_prompt=system_prompt,
            timeout_seconds=timeout,
            source="workspace_db",
            provider="google_cloud",
            region=region,
        )

    if provider == "openai_compatible":
        return _settings_from_openai_compatible(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout,
            system_prompt=system_prompt,
            source="workspace_db",
        )

    if provider == "gemini":
        key = api_key or (getattr(env_settings, "gemini_api_key", None) or "").strip()
        chosen_model = model or str(
            getattr(env_settings, "gemini_translation_model", "gemini-2.5-flash") or "gemini-2.5-flash"
        )
        return _settings_from_openai_compatible(
            api_key=key,
            base_url=base_url or GEMINI_OPENAI_COMPAT_BASE,
            model=chosen_model,
            timeout_seconds=timeout,
            system_prompt=system_prompt,
            source="workspace_db",
        )

    if provider in {"ollama", "qwen"}:
        chosen_base = base_url or str(
            getattr(env_settings, "ollama_base_url", "http://127.0.0.1:11434") or "http://127.0.0.1:11434"
        )
        if not chosen_base.rstrip("/").endswith("/v1"):
            chosen_base = chosen_base.rstrip("/") + "/v1"
        chosen_model = model or str(
            getattr(env_settings, "ollama_translation_model", "qwen2.5:14b") or "qwen2.5:14b"
        )
        return _settings_from_openai_compatible(
            api_key=api_key or "ollama",
            base_url=chosen_base,
            model=chosen_model,
            timeout_seconds=timeout,
            system_prompt=system_prompt,
            source="workspace_db",
        )

    if provider == "auto":
        if api_key and model and base_url:
            return _settings_from_openai_compatible(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout,
                system_prompt=system_prompt,
                source="workspace_db",
            )
        gemini_key = api_key or (getattr(env_settings, "gemini_api_key", None) or "").strip()
        if gemini_key:
            return _map_workspace_ai_to_settings(
                TranslationAiConfig(
                    enabled=True,
                    provider="gemini",
                    model=model,
                    api_key=gemini_key,
                    base_url=base_url,
                    timeout_seconds=timeout,
                ),
                system_prompt=system_prompt,
                env_settings=env_settings,
            )
        return _map_workspace_ai_to_settings(
            TranslationAiConfig(
                enabled=True,
                provider="ollama",
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout_seconds=timeout,
            ),
            system_prompt=system_prompt,
            env_settings=env_settings,
        )

    raise TranslatorError(
        TranslatorErrorCode.CONFIG_MISSING,
        f"Unsupported Ops Caption AI provider: {provider}",
    )


def resolve_translator_settings(
    *,
    db: Session | None = None,
    workspace_id: UUID | None = None,
    workspace_ai: TranslationAiConfig | None = None,
    system_prompt: str | None = None,
) -> TranslatorSettings:
    """
    Authority for Phase 2.5 caption translator (does NOT use Translation settings):

    1. Ops **Caption AI settings** (`caption_ai` + `caption_prompt`) when enabled
    2. Else env ``LLM_*`` / ``TRANSLATION_SYSTEM_PROMPT`` fallback

    Dialogue Translation settings (`translation_ai`) remain untouched for audio jobs.
    """
    env_settings = get_settings()

    if db is not None or workspace_ai is not None:
        if workspace_ai is None:
            assert db is not None
            svc = WorkspaceSettingsService(db)
            workspace_ai = svc.get_caption_ai(workspace_id)
            db_prompt = svc.get_caption_prompt(workspace_id)
        else:
            db_prompt = system_prompt
            if db is not None and system_prompt is None:
                db_prompt = WorkspaceSettingsService(db).get_caption_prompt(workspace_id)

        prompt = _resolve_system_prompt(
            system_prompt if system_prompt is not None else db_prompt
        )

        if workspace_ai is not None and bool(workspace_ai.enabled):
            settings = _map_workspace_ai_to_settings(
                workspace_ai,
                system_prompt=prompt,
                env_settings=env_settings,
            )
            logger.info(
                "caption_translator_settings_workspace_db",
                extra={
                    "provider": workspace_ai.provider,
                    "model": settings.model_name,
                    "base_url": settings.base_url,
                },
            )
            return settings

    settings = load_translator_settings(require_credentials=True)
    if system_prompt and system_prompt.strip():
        settings = TranslatorSettings(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model_name=settings.model_name,
            system_prompt=system_prompt.strip(),
            timeout_seconds=settings.timeout_seconds,
            source="env",
            provider=settings.provider,
            region=settings.region,
        )
    logger.info(
        "caption_translator_settings_env",
        extra={"model": settings.model_name, "base_url": settings.base_url},
    )
    return settings
