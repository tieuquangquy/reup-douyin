"""Env-driven LLM settings for Phase 2.5 caption translation (no hardcoded keys/models)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.media_pipeline.translator.errors import TranslatorError, TranslatorErrorCode

DEFAULT_TRANSLATION_SYSTEM_PROMPT = (
    "Bạn là một chuyên gia dịch thuật video ngắn. Hãy dịch các câu tiếng Trung sau sang tiếng Việt. "
    "Yêu cầu: Dịch theo văn cảnh toàn bộ video, văn phong tự nhiên, bắt trend mạng xã hội. "
    "RÚT GỌN CÂU CHỮ sao cho ngắn gọn nhất có thể để vừa khung hình phụ đề video "
    "(tối đa 10-12 chữ/dòng). Trả về định dạng JSON nghiêm ngặt."
)

ENV_API_KEY = "LLM_API_KEY"
ENV_BASE_URL = "LLM_BASE_URL"
ENV_MODEL_NAME = "LLM_MODEL_NAME"
ENV_SYSTEM_PROMPT = "TRANSLATION_SYSTEM_PROMPT"


@dataclass(frozen=True)
class TranslatorSettings:
    api_key: str
    base_url: str
    model_name: str
    system_prompt: str
    timeout_seconds: float = 90.0
    source: str = "env"  # workspace_db | env


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _maybe_load_dotenv() -> None:
    """Best-effort load repo-root and apps/api .env without requiring python-dotenv."""
    here = Path(__file__).resolve()
    # config.py → translator → media_pipeline → src → api → apps → repo
    repo_root = here.parents[5]
    api_root = here.parents[3]
    _load_env_file(repo_root / ".env")
    _load_env_file(api_root / ".env")


def load_translator_settings(*, require_credentials: bool = True) -> TranslatorSettings:
    """
    Read LLM_* + TRANSLATION_SYSTEM_PROMPT from process env (and optional .env files).

    Change model / endpoint / prompt without editing Python — only env / Ops later.
    """
    _maybe_load_dotenv()
    api_key = os.environ.get(ENV_API_KEY, "").strip()
    base_url = os.environ.get(ENV_BASE_URL, "").strip()
    model_name = os.environ.get(ENV_MODEL_NAME, "").strip()
    prompt = os.environ.get(ENV_SYSTEM_PROMPT, "").strip() or DEFAULT_TRANSLATION_SYSTEM_PROMPT

    if require_credentials:
        missing = [
            name
            for name, value in (
                (ENV_API_KEY, api_key),
                (ENV_BASE_URL, base_url),
                (ENV_MODEL_NAME, model_name),
            )
            if not value
        ]
        if missing:
            raise TranslatorError(
                TranslatorErrorCode.CONFIG_MISSING,
                "Missing env: "
                + ", ".join(missing)
                + ". Set them in repo .env (see apps/api/.env.example).",
            )

    return TranslatorSettings(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model_name=model_name,
        system_prompt=prompt,
        timeout_seconds=90.0,
        source="env",
    )
