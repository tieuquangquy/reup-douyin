"""Resolve Translation / Caption AI provider ids to a runtime mode."""

from __future__ import annotations

from typing import Literal

TranslationProviderMode = Literal["gemini", "ollama", "openai_compatible", "unsupported"]

# Native runtimes (must match Ops LLM catalog).
_NATIVE_GEMINI = frozenset({"gemini"})
_NATIVE_OLLAMA = frozenset({"ollama", "qwen"})

# Explicit openai-compatible aliases from the Ops dropdown (plus legacy openai_compatible).
# Any other non-empty id also falls through to openai_compatible.
_OPENAI_COMPATIBLE_ALIASES = frozenset(
    {
        "openai_compatible",
        "openai",
        "openai_chatgpt",
        "openrouter",
        "deepseek",
        "fireworks",
        "mistral",
        "moonshot",
        "xai",
        "baseten",
        "minimax",
        "lmstudio",
        "litellm",
        "poe",
        "requesty",
        "unbound",
        "sambanova",
        "vercel_ai_gateway",
        "zai",
        "amazon_bedrock",
        "anthropic",
        "gcp_vertex",
        "qwen_code",
        "vscode_lm",
    }
)


def resolve_translation_provider_mode(provider: str | None) -> TranslationProviderMode:
    """
    Map a stored provider id to the HTTP client family used for Test / Translate / list-models.

    - gemini / ollama / qwen: native clients
    - known OpenAI-compatible presets and unknown non-empty ids: openai_compatible
    - auto / empty / placeholder / off / none: unsupported (caller handles auto separately)
    """
    mode = (provider or "").strip().lower()
    if not mode or mode in {"auto", "placeholder", "off", "none"}:
        return "unsupported"
    if mode in _NATIVE_GEMINI:
        return "gemini"
    if mode in _NATIVE_OLLAMA:
        return "ollama"
    if mode in _OPENAI_COMPATIBLE_ALIASES:
        return "openai_compatible"
    # Unknown saved ids (custom gateways) still use the OpenAI-compatible client.
    return "openai_compatible"
