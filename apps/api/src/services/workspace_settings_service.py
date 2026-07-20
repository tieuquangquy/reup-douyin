"""Workspace-scoped operator settings persisted in ``workspaces.settings_json``."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.db.bootstrap import ensure_default_workspace
from src.models.foundation import Workspace
from src.tts_pipeline.runtime_snapshot import merge_runtime, normalize_runtime

logger = logging.getLogger(__name__)

TRANSLATION_USER_PROMPT_KEY = "translation_user_prompt"
TRANSLATION_AI_KEY = "translation_ai"
# Phase 2.5 hard-sub / OCR caption translator — separate from dialogue Translation settings.
CAPTION_AI_KEY = "caption_ai"
CAPTION_PROMPT_KEY = "caption_prompt"
TTS_AI_KEY = "tts_ai"
DEFAULT_TTS_PROFILE_ID = "default"
DEFAULT_TTS_PROFILE_NAME = "Default"
DEFAULT_LLM_AI_PROFILE_ID = "default"
DEFAULT_LLM_AI_PROFILE_NAME = "Default"
DEFAULT_PROMPT_PROFILE_ID = "default"
DEFAULT_PROMPT_PROFILE_NAME = "Default"

_ALLOWED_PROVIDERS = frozenset({"auto", "gemini", "openai_compatible", "ollama", "placeholder"})
_ALLOWED_FALLBACKS = frozenset({"none", "ollama", "gemini", "openai_compatible"})

_ALLOWED_TTS_PROVIDERS = frozenset(
    {
        "auto",
        "edge",
        "vieneu",
        "google",
        "azure",
        "elevenlabs",
        "openai",
        "openai_compatible",
        "http_custom",
        "cli",
        "placeholder",
    }
)
_ALLOWED_TTS_FALLBACKS = frozenset(
    {
        "none",
        "edge",
        "vieneu",
        "google",
        "azure",
        "elevenlabs",
        "openai",
        "openai_compatible",
        "http_custom",
        "cli",
        "placeholder",
    }
)
_TTS_CUSTOM_PROVIDER_RE = re.compile(r"^[a-z][a-z0-9_\-]{0,62}$")
_TTS_RESERVED_SLUGS = frozenset({"none", "off", "null", "undefined"})
_ALLOWED_TTS_LOCAL_BACKENDS = frozenset({"auto", "onnx", "pytorch", "remote"})
_ALLOWED_TTS_DEVICES = frozenset({"auto", "cpu", "cuda"})


def is_allowed_tts_provider(name: str) -> bool:
    cleaned = (name or "").strip().lower()
    if not cleaned or cleaned in _TTS_RESERVED_SLUGS:
        return False
    if cleaned in _ALLOWED_TTS_PROVIDERS:
        return True
    return bool(_TTS_CUSTOM_PROVIDER_RE.match(cleaned))


def is_allowed_tts_fallback(name: str) -> bool:
    cleaned = (name or "").strip().lower()
    if cleaned == "none":
        return True
    return is_allowed_tts_provider(cleaned)


def mask_secret(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "••••"
    return f"••••{text[-4:]}"


@dataclass
class TranslationAiConfig:
    """Internal Translation AI connection (includes raw api_key)."""

    enabled: bool = False
    provider: str = "auto"
    model: str = ""
    api_key: str | None = None
    base_url: str = ""
    timeout_seconds: float = 90.0
    fallback_provider: str = "none"
    fallback_model: str = ""


@dataclass
class TtsAiConfig:
    """Internal TTS provider connection (includes raw api_key)."""

    enabled: bool = False
    provider: str = "auto"
    voice_id: str = ""
    speaking_rate: float = 1.0
    language_code: str = "vi"
    model_id: str = ""
    api_key: str | None = None
    base_url: str = ""
    timeout_seconds: float = 120.0
    fallback_provider: str = "none"
    fallback_voice_id: str = ""
    local_backend: str = "auto"
    device: str = "auto"
    cli_binary: str = ""
    options_json: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None


class WorkspaceSettingsService:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_workspace(self, workspace_id: UUID | None) -> Workspace:
        """
        Resolve the settings workspace for Phase 1 local ops.

        Login JWT historically used a deterministic uuid5 that is not always
        materialised as a ``workspaces`` row. Jobs/videos use
        ``ensure_default_workspace`` (slug ``local``). When the claim is missing
        or unknown, fall back to that default so Save and Translate share authority.
        """
        if workspace_id is not None:
            workspace = self.db.get(Workspace, workspace_id)
            if workspace is not None:
                return workspace
            logger.warning(
                "workspace_settings_fallback_default",
                extra={"requested_workspace_id": str(workspace_id)},
            )
        return ensure_default_workspace(self.db)

    def get_translation_user_prompt(self, workspace_id: UUID | None) -> str | None:
        return self._get_prompt_active(workspace_id, TRANSLATION_USER_PROMPT_KEY)

    def set_translation_user_prompt(self, workspace_id: UUID | None, prompt: str) -> str:
        """Write into the active dialogue translation prompt profile."""
        return self._set_prompt_active(workspace_id, TRANSLATION_USER_PROMPT_KEY, prompt)

    def get_translation_prompt_public(self, workspace_id: UUID | None) -> dict[str, Any]:
        return self._get_prompt_public(workspace_id, TRANSLATION_USER_PROMPT_KEY)

    def get_translation_prompt_profile_public(
        self, workspace_id: UUID | None, profile_id: str
    ) -> dict[str, Any]:
        return self._get_prompt_profile_public(workspace_id, TRANSLATION_USER_PROMPT_KEY, profile_id)

    def create_translation_prompt_profile(
        self, workspace_id: UUID | None, *, name: str
    ) -> dict[str, Any]:
        return self._create_prompt_profile(workspace_id, TRANSLATION_USER_PROMPT_KEY, name=name)

    def set_translation_prompt_profile(
        self, workspace_id: UUID | None, profile_id: str, *, prompt: str
    ) -> dict[str, Any]:
        return self._set_prompt_profile(
            workspace_id, TRANSLATION_USER_PROMPT_KEY, profile_id, prompt=prompt
        )

    def rename_translation_prompt_profile(
        self, workspace_id: UUID | None, profile_id: str, *, name: str
    ) -> dict[str, Any]:
        return self._rename_prompt_profile(
            workspace_id, TRANSLATION_USER_PROMPT_KEY, profile_id, name=name
        )

    def activate_translation_prompt_profile(
        self, workspace_id: UUID | None, profile_id: str
    ) -> dict[str, Any]:
        return self._activate_prompt_profile(
            workspace_id, TRANSLATION_USER_PROMPT_KEY, profile_id
        )

    def reorder_translation_prompt_profiles(
        self, workspace_id: UUID | None, profile_ids: list[str]
    ) -> dict[str, Any]:
        self._reorder_prompt_profiles(workspace_id, TRANSLATION_USER_PROMPT_KEY, profile_ids)
        return self.get_translation_prompt_public(workspace_id)

    def delete_translation_prompt_profile(
        self, workspace_id: UUID | None, profile_id: str
    ) -> None:
        self._delete_prompt_profile(workspace_id, TRANSLATION_USER_PROMPT_KEY, profile_id)

    def get_translation_ai(self, workspace_id: UUID | None) -> TranslationAiConfig:
        return self._get_llm_ai_active_config(workspace_id, TRANSLATION_AI_KEY)

    def get_translation_ai_public(self, workspace_id: UUID | None) -> dict[str, Any]:
        return self._get_llm_ai_public(workspace_id, TRANSLATION_AI_KEY)

    def get_translation_ai_profile_public(
        self, workspace_id: UUID | None, profile_id: str
    ) -> dict[str, Any]:
        return self._get_llm_ai_profile_public(workspace_id, TRANSLATION_AI_KEY, profile_id)

    def create_translation_ai_profile(
        self, workspace_id: UUID | None, *, name: str
    ) -> dict[str, Any]:
        return self._create_llm_ai_profile(workspace_id, TRANSLATION_AI_KEY, name=name)

    def set_translation_ai_profile(
        self,
        workspace_id: UUID | None,
        profile_id: str,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TranslationAiConfig:
        return self._set_llm_ai_profile(
            workspace_id,
            TRANSLATION_AI_KEY,
            profile_id,
            payload,
            keep_existing_api_key=keep_existing_api_key,
            clear_api_key=clear_api_key,
        )

    def set_translation_ai_profile_enabled(
        self, workspace_id: UUID | None, profile_id: str, *, enabled: bool
    ) -> dict[str, Any]:
        return self._set_llm_ai_profile_enabled(
            workspace_id, TRANSLATION_AI_KEY, profile_id, enabled=enabled
        )

    def rename_translation_ai_profile(
        self, workspace_id: UUID | None, profile_id: str, *, name: str
    ) -> dict[str, Any]:
        return self._rename_llm_ai_profile(
            workspace_id, TRANSLATION_AI_KEY, profile_id, name=name
        )

    def activate_translation_ai_profile(
        self, workspace_id: UUID | None, profile_id: str
    ) -> dict[str, Any]:
        return self._activate_llm_ai_profile(workspace_id, TRANSLATION_AI_KEY, profile_id)

    def reorder_translation_ai_profiles(
        self, workspace_id: UUID | None, profile_ids: list[str]
    ) -> dict[str, Any]:
        self._reorder_llm_ai_profiles(workspace_id, TRANSLATION_AI_KEY, profile_ids)
        return self.get_translation_ai_public(workspace_id)

    def delete_translation_ai_profile(
        self, workspace_id: UUID | None, profile_id: str
    ) -> None:
        self._delete_llm_ai_profile(workspace_id, TRANSLATION_AI_KEY, profile_id)

    def set_translation_ai(
        self,
        workspace_id: UUID | None,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TranslationAiConfig:
        return self._set_llm_ai_active(
            workspace_id,
            TRANSLATION_AI_KEY,
            payload,
            keep_existing_api_key=keep_existing_api_key,
            clear_api_key=clear_api_key,
        )

    # --- Caption AI (Phase 2.5 hard-sub) — independent of translation_ai ---

    def get_caption_prompt(self, workspace_id: UUID | None) -> str | None:
        return self._get_prompt_active(workspace_id, CAPTION_PROMPT_KEY)

    def set_caption_prompt(self, workspace_id: UUID | None, prompt: str) -> str:
        """Write into the active caption prompt profile (never touches translation_user_prompt)."""
        return self._set_prompt_active(workspace_id, CAPTION_PROMPT_KEY, prompt)

    def get_caption_prompt_public(self, workspace_id: UUID | None) -> dict[str, Any]:
        return self._get_prompt_public(workspace_id, CAPTION_PROMPT_KEY)

    def get_caption_prompt_profile_public(
        self, workspace_id: UUID | None, profile_id: str
    ) -> dict[str, Any]:
        return self._get_prompt_profile_public(workspace_id, CAPTION_PROMPT_KEY, profile_id)

    def create_caption_prompt_profile(
        self, workspace_id: UUID | None, *, name: str
    ) -> dict[str, Any]:
        return self._create_prompt_profile(workspace_id, CAPTION_PROMPT_KEY, name=name)

    def set_caption_prompt_profile(
        self, workspace_id: UUID | None, profile_id: str, *, prompt: str
    ) -> dict[str, Any]:
        return self._set_prompt_profile(workspace_id, CAPTION_PROMPT_KEY, profile_id, prompt=prompt)

    def rename_caption_prompt_profile(
        self, workspace_id: UUID | None, profile_id: str, *, name: str
    ) -> dict[str, Any]:
        return self._rename_prompt_profile(workspace_id, CAPTION_PROMPT_KEY, profile_id, name=name)

    def activate_caption_prompt_profile(
        self, workspace_id: UUID | None, profile_id: str
    ) -> dict[str, Any]:
        return self._activate_prompt_profile(workspace_id, CAPTION_PROMPT_KEY, profile_id)

    def reorder_caption_prompt_profiles(
        self, workspace_id: UUID | None, profile_ids: list[str]
    ) -> dict[str, Any]:
        self._reorder_prompt_profiles(workspace_id, CAPTION_PROMPT_KEY, profile_ids)
        return self.get_caption_prompt_public(workspace_id)

    def delete_caption_prompt_profile(
        self, workspace_id: UUID | None, profile_id: str
    ) -> None:
        self._delete_prompt_profile(workspace_id, CAPTION_PROMPT_KEY, profile_id)

    # --- Shared prompt-profile internals (translation_user_prompt + caption_prompt) ---

    def _get_prompt_active(self, workspace_id: UUID | None, settings_key: str) -> str | None:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(settings_key)
        active_id, profiles = self._normalize_prompt_profiles(raw)
        active = self._find_tts_profile(profiles, active_id) or profiles[0]
        text = str(active.get("prompt") or "").strip()
        return text or None

    def _set_prompt_active(
        self, workspace_id: UUID | None, settings_key: str, prompt: str
    ) -> str:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_prompt_profiles(meta.get(settings_key))
        active = self._find_tts_profile(profiles, active_id) or profiles[0]
        cleaned = (prompt or "").strip()
        active["prompt"] = cleaned
        meta[settings_key] = {
            "active_profile_id": str(active.get("id") or active_id),
            "profiles": profiles,
        }
        self._persist_workspace_settings(workspace, meta)
        return cleaned

    def _get_prompt_public(
        self, workspace_id: UUID | None, settings_key: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(settings_key)
        active_id, profiles = self._normalize_prompt_profiles(raw)
        active = self._find_tts_profile(profiles, active_id) or profiles[0]
        prompt_text = str(active.get("prompt") or "")
        summaries = [
            self._prompt_profile_summary(p, active_id=str(active.get("id") or active_id))
            for p in profiles
        ]
        return {
            "prompt": prompt_text,
            "source": "workspace_db" if prompt_text.strip() else "empty",
            "active_profile_id": str(active.get("id") or active_id),
            "active_profile_name": str(active.get("name") or DEFAULT_PROMPT_PROFILE_NAME),
            "profiles": summaries,
            "focus_profile_id": None,
        }

    def _get_prompt_profile_public(
        self, workspace_id: UUID | None, settings_key: str, profile_id: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(settings_key)
        active_id, profiles = self._normalize_prompt_profiles(raw)
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        active = self._find_tts_profile(profiles, active_id) or profiles[0]
        prompt_text = str(target.get("prompt") or "")
        summaries = [
            self._prompt_profile_summary(p, active_id=str(active.get("id") or active_id))
            for p in profiles
        ]
        return {
            "prompt": prompt_text,
            "source": "workspace_db" if prompt_text.strip() else "empty",
            "active_profile_id": str(active.get("id") or active_id),
            "active_profile_name": str(active.get("name") or DEFAULT_PROMPT_PROFILE_NAME),
            "profiles": summaries,
            "focus_profile_id": str(target.get("id") or profile_id),
        }

    def _create_prompt_profile(
        self, workspace_id: UUID | None, settings_key: str, *, name: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        cleaned_name = self._validate_tts_profile_name(name)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_prompt_profiles(meta.get(settings_key))
        self._ensure_unique_tts_profile_name(profiles, cleaned_name)
        profile_id = str(uuid4())
        blank = self._blank_prompt_profile(profile_id=profile_id, name=cleaned_name)
        profiles.append(blank)
        meta[settings_key] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return blank

    def _set_prompt_profile(
        self,
        workspace_id: UUID | None,
        settings_key: str,
        profile_id: str,
        *,
        prompt: str,
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_prompt_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        target["prompt"] = (prompt or "").strip()
        meta[settings_key] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def _rename_prompt_profile(
        self,
        workspace_id: UUID | None,
        settings_key: str,
        profile_id: str,
        *,
        name: str,
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        cleaned_name = self._validate_tts_profile_name(name)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_prompt_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        self._ensure_unique_tts_profile_name(profiles, cleaned_name, exclude_id=str(target["id"]))
        target["name"] = cleaned_name
        meta[settings_key] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def _activate_prompt_profile(
        self, workspace_id: UUID | None, settings_key: str, profile_id: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        _active_id, profiles = self._normalize_prompt_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        meta[settings_key] = {"active_profile_id": str(target["id"]), "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def _delete_prompt_profile(
        self, workspace_id: UUID | None, settings_key: str, profile_id: str
    ) -> None:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_prompt_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        if len(profiles) <= 1:
            raise ValueError("last_profile")
        remaining = [p for p in profiles if str(p.get("id")) != str(target["id"])]
        next_active = active_id
        if str(active_id) == str(target["id"]):
            next_active = str(remaining[0]["id"])
        meta[settings_key] = {"active_profile_id": next_active, "profiles": remaining}
        self._persist_workspace_settings(workspace, meta)

    def _reorder_prompt_profiles(
        self, workspace_id: UUID | None, settings_key: str, profile_ids: list[str]
    ) -> None:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_prompt_profiles(meta.get(settings_key))
        ordered = self._reorder_profiles_by_ids(profiles, profile_ids)
        meta[settings_key] = {"active_profile_id": active_id, "profiles": ordered}
        self._persist_workspace_settings(workspace, meta)

    @classmethod
    def _normalize_prompt_profiles(cls, raw: Any) -> tuple[str, list[dict[str, Any]]]:
        """Return (active_profile_id, profiles). Migrates legacy plain string blobs."""
        if isinstance(raw, dict) and isinstance(raw.get("profiles"), list) and raw["profiles"]:
            profiles: list[dict[str, Any]] = []
            for item in raw["profiles"]:
                if not isinstance(item, dict):
                    continue
                profile_id = str(item.get("id") or "").strip() or str(uuid4())
                name = str(item.get("name") or "").strip() or DEFAULT_PROMPT_PROFILE_NAME
                prompt_text = item.get("prompt")
                if not isinstance(prompt_text, str):
                    prompt_text = ""
                profiles.append({"id": profile_id, "name": name, "prompt": prompt_text})
            if not profiles:
                blank = cls._blank_prompt_profile(
                    profile_id=DEFAULT_PROMPT_PROFILE_ID, name=DEFAULT_PROMPT_PROFILE_NAME
                )
                return str(blank["id"]), [blank]
            active_id = str(raw.get("active_profile_id") or "").strip()
            if not active_id or cls._find_tts_profile(profiles, active_id) is None:
                active_id = str(profiles[0]["id"])
            return active_id, profiles

        if isinstance(raw, str):
            text = raw.strip()
            legacy = cls._blank_prompt_profile(
                profile_id=DEFAULT_PROMPT_PROFILE_ID, name=DEFAULT_PROMPT_PROFILE_NAME
            )
            legacy["prompt"] = text
            return str(legacy["id"]), [legacy]

        blank = cls._blank_prompt_profile(
            profile_id=DEFAULT_PROMPT_PROFILE_ID, name=DEFAULT_PROMPT_PROFILE_NAME
        )
        return str(blank["id"]), [blank]

    @staticmethod
    def _blank_prompt_profile(*, profile_id: str, name: str, prompt: str = "") -> dict[str, Any]:
        return {"id": profile_id, "name": name, "prompt": prompt}

    @staticmethod
    def _prompt_profile_summary(profile: dict[str, Any], *, active_id: str) -> dict[str, Any]:
        return {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or DEFAULT_PROMPT_PROFILE_NAME),
            "prompt": str(profile.get("prompt") or ""),
            "is_active": str(profile.get("id") or "") == str(active_id),
        }

    def get_caption_ai(self, workspace_id: UUID | None) -> TranslationAiConfig:
        return self._get_llm_ai_active_config(workspace_id, CAPTION_AI_KEY)

    def get_caption_ai_public(self, workspace_id: UUID | None) -> dict[str, Any]:
        return self._get_llm_ai_public(workspace_id, CAPTION_AI_KEY)

    def get_caption_ai_profile_public(
        self, workspace_id: UUID | None, profile_id: str
    ) -> dict[str, Any]:
        return self._get_llm_ai_profile_public(workspace_id, CAPTION_AI_KEY, profile_id)

    def create_caption_ai_profile(
        self, workspace_id: UUID | None, *, name: str
    ) -> dict[str, Any]:
        return self._create_llm_ai_profile(workspace_id, CAPTION_AI_KEY, name=name)

    def set_caption_ai_profile(
        self,
        workspace_id: UUID | None,
        profile_id: str,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TranslationAiConfig:
        return self._set_llm_ai_profile(
            workspace_id,
            CAPTION_AI_KEY,
            profile_id,
            payload,
            keep_existing_api_key=keep_existing_api_key,
            clear_api_key=clear_api_key,
        )

    def set_caption_ai_profile_enabled(
        self, workspace_id: UUID | None, profile_id: str, *, enabled: bool
    ) -> dict[str, Any]:
        return self._set_llm_ai_profile_enabled(
            workspace_id, CAPTION_AI_KEY, profile_id, enabled=enabled
        )

    def rename_caption_ai_profile(
        self, workspace_id: UUID | None, profile_id: str, *, name: str
    ) -> dict[str, Any]:
        return self._rename_llm_ai_profile(
            workspace_id, CAPTION_AI_KEY, profile_id, name=name
        )

    def activate_caption_ai_profile(
        self, workspace_id: UUID | None, profile_id: str
    ) -> dict[str, Any]:
        return self._activate_llm_ai_profile(workspace_id, CAPTION_AI_KEY, profile_id)

    def reorder_caption_ai_profiles(
        self, workspace_id: UUID | None, profile_ids: list[str]
    ) -> dict[str, Any]:
        self._reorder_llm_ai_profiles(workspace_id, CAPTION_AI_KEY, profile_ids)
        return self.get_caption_ai_public(workspace_id)

    def delete_caption_ai_profile(
        self, workspace_id: UUID | None, profile_id: str
    ) -> None:
        self._delete_llm_ai_profile(workspace_id, CAPTION_AI_KEY, profile_id)

    def set_caption_ai(
        self,
        workspace_id: UUID | None,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TranslationAiConfig:
        """Save Caption AI connection under caption_ai — never writes translation_ai."""
        return self._set_llm_ai_active(
            workspace_id,
            CAPTION_AI_KEY,
            payload,
            keep_existing_api_key=keep_existing_api_key,
            clear_api_key=clear_api_key,
        )

    # --- LLM AI shared internals (translation_ai + caption_ai) ---

    def _get_llm_ai_active_config(
        self, workspace_id: UUID | None, settings_key: str
    ) -> TranslationAiConfig:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(settings_key)
        return self._parse_translation_ai(raw)

    def _get_llm_ai_public(
        self, workspace_id: UUID | None, settings_key: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(settings_key)
        active_id, profiles = self._normalize_llm_ai_profiles(raw)
        active = self._find_tts_profile(profiles, active_id) or profiles[0]
        cfg = self._parse_translation_ai(active)
        key = (cfg.api_key or "").strip()
        source = "workspace_db" if cfg.enabled else "env"
        summaries = [
            self._llm_ai_profile_summary(p, active_id=str(active.get("id") or active_id))
            for p in profiles
        ]
        return {
            "enabled": cfg.enabled,
            "provider": cfg.provider,
            "model": cfg.model,
            "api_key_set": bool(key),
            "api_key_masked": mask_secret(key),
            "api_key": key,
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_model": cfg.fallback_model,
            "source": source,
            "active_profile_id": str(active.get("id") or active_id),
            "active_profile_name": str(active.get("name") or DEFAULT_LLM_AI_PROFILE_NAME),
            "profiles": summaries,
            "focus_profile_id": None,
        }

    def _get_llm_ai_profile_public(
        self, workspace_id: UUID | None, settings_key: str, profile_id: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(settings_key)
        active_id, profiles = self._normalize_llm_ai_profiles(raw)
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        active = self._find_tts_profile(profiles, active_id) or profiles[0]
        cfg = self._parse_translation_ai(target)
        key = (cfg.api_key or "").strip()
        summaries = [
            self._llm_ai_profile_summary(p, active_id=str(active.get("id") or active_id))
            for p in profiles
        ]
        return {
            "enabled": cfg.enabled,
            "provider": cfg.provider,
            "model": cfg.model,
            "api_key_set": bool(key),
            "api_key_masked": mask_secret(key),
            "api_key": key,
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_model": cfg.fallback_model,
            "source": "workspace_db" if cfg.enabled else "env",
            "active_profile_id": str(active.get("id") or active_id),
            "active_profile_name": str(active.get("name") or DEFAULT_LLM_AI_PROFILE_NAME),
            "profiles": summaries,
            "focus_profile_id": str(target.get("id") or profile_id),
        }

    def _create_llm_ai_profile(
        self, workspace_id: UUID | None, settings_key: str, *, name: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        cleaned_name = self._validate_tts_profile_name(name)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_llm_ai_profiles(meta.get(settings_key))
        self._ensure_unique_tts_profile_name(profiles, cleaned_name)
        profile_id = str(uuid4())
        blank = self._blank_llm_ai_profile(profile_id=profile_id, name=cleaned_name)
        profiles.append(blank)
        meta[settings_key] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return blank

    def _set_llm_ai_profile_enabled(
        self,
        workspace_id: UUID | None,
        settings_key: str,
        profile_id: str,
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_llm_ai_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        target["enabled"] = bool(enabled)
        meta[settings_key] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def _set_llm_ai_profile(
        self,
        workspace_id: UUID | None,
        settings_key: str,
        profile_id: str,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TranslationAiConfig:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_llm_ai_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        self._apply_llm_ai_payload_to_profile(
            target,
            payload,
            keep_existing_api_key=keep_existing_api_key,
            clear_api_key=clear_api_key,
            preserve_enabled=True,
        )
        meta[settings_key] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return self._parse_translation_ai(target)

    def _rename_llm_ai_profile(
        self,
        workspace_id: UUID | None,
        settings_key: str,
        profile_id: str,
        *,
        name: str,
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        cleaned_name = self._validate_tts_profile_name(name)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_llm_ai_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        self._ensure_unique_tts_profile_name(profiles, cleaned_name, exclude_id=str(target["id"]))
        target["name"] = cleaned_name
        meta[settings_key] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def _activate_llm_ai_profile(
        self, workspace_id: UUID | None, settings_key: str, profile_id: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        _active_id, profiles = self._normalize_llm_ai_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        meta[settings_key] = {"active_profile_id": str(target["id"]), "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def _delete_llm_ai_profile(
        self, workspace_id: UUID | None, settings_key: str, profile_id: str
    ) -> None:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_llm_ai_profiles(meta.get(settings_key))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        if len(profiles) <= 1:
            raise ValueError("last_profile")
        remaining = [p for p in profiles if str(p.get("id")) != str(target["id"])]
        next_active = active_id
        if str(active_id) == str(target["id"]):
            next_active = str(remaining[0]["id"])
        meta[settings_key] = {"active_profile_id": next_active, "profiles": remaining}
        self._persist_workspace_settings(workspace, meta)

    def _reorder_llm_ai_profiles(
        self, workspace_id: UUID | None, settings_key: str, profile_ids: list[str]
    ) -> None:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_llm_ai_profiles(meta.get(settings_key))
        ordered = self._reorder_profiles_by_ids(profiles, profile_ids)
        meta[settings_key] = {"active_profile_id": active_id, "profiles": ordered}
        self._persist_workspace_settings(workspace, meta)

    def _set_llm_ai_active(
        self,
        workspace_id: UUID | None,
        settings_key: str,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TranslationAiConfig:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_llm_ai_profiles(meta.get(settings_key))
        active_profile = self._find_tts_profile(profiles, active_id) or profiles[0]
        self._apply_llm_ai_payload_to_profile(
            active_profile,
            payload,
            keep_existing_api_key=keep_existing_api_key,
            clear_api_key=clear_api_key,
            preserve_enabled=False,
        )
        meta[settings_key] = {
            "active_profile_id": str(active_profile["id"]),
            "profiles": profiles,
        }
        self._persist_workspace_settings(workspace, meta)
        return self._parse_translation_ai(active_profile)

    @classmethod
    def _normalize_llm_ai_profiles(cls, raw: Any) -> tuple[str, list[dict[str, Any]]]:
        """Return (active_profile_id, profiles). Migrates legacy flat translation/caption blobs."""
        if isinstance(raw, dict) and isinstance(raw.get("profiles"), list) and raw["profiles"]:
            profiles: list[dict[str, Any]] = []
            for item in raw["profiles"]:
                if not isinstance(item, dict):
                    continue
                profile = dict(item)
                profile_id = str(profile.get("id") or "").strip() or str(uuid4())
                profile["id"] = profile_id
                name = str(profile.get("name") or "").strip() or DEFAULT_LLM_AI_PROFILE_NAME
                profile["name"] = name
                profiles.append(profile)
            if not profiles:
                blank = cls._blank_llm_ai_profile(
                    profile_id=DEFAULT_LLM_AI_PROFILE_ID, name=DEFAULT_LLM_AI_PROFILE_NAME
                )
                return str(blank["id"]), [blank]
            active_id = str(raw.get("active_profile_id") or "").strip()
            if not active_id or cls._find_tts_profile(profiles, active_id) is None:
                active_id = str(profiles[0]["id"])
            return active_id, profiles

        if isinstance(raw, dict) and ("provider" in raw or "enabled" in raw or "model" in raw):
            profile_id = DEFAULT_LLM_AI_PROFILE_ID
            legacy = dict(raw)
            legacy.pop("profiles", None)
            legacy.pop("active_profile_id", None)
            legacy["id"] = profile_id
            legacy["name"] = DEFAULT_LLM_AI_PROFILE_NAME
            return profile_id, [legacy]

        blank = cls._blank_llm_ai_profile(
            profile_id=DEFAULT_LLM_AI_PROFILE_ID, name=DEFAULT_LLM_AI_PROFILE_NAME
        )
        return str(blank["id"]), [blank]

    @staticmethod
    def _blank_llm_ai_profile(*, profile_id: str, name: str) -> dict[str, Any]:
        return {
            "id": profile_id,
            "name": name,
            "enabled": False,
            "provider": "auto",
            "model": "",
            "api_key": "",
            "base_url": "",
            "timeout_seconds": 90.0,
            "fallback_provider": "none",
            "fallback_model": "",
        }

    @staticmethod
    def _llm_ai_profile_summary(profile: dict[str, Any], *, active_id: str) -> dict[str, Any]:
        cfg = WorkspaceSettingsService._parse_translation_ai(profile)
        key = (cfg.api_key or "").strip()
        return {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or DEFAULT_LLM_AI_PROFILE_NAME),
            "enabled": bool(cfg.enabled),
            "provider": cfg.provider,
            "model": cfg.model,
            "api_key_set": bool(key),
            "api_key_masked": mask_secret(key),
            "api_key": key,
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_model": cfg.fallback_model,
            "is_active": str(profile.get("id") or "") == str(active_id),
        }

    def _apply_llm_ai_payload_to_profile(
        self,
        profile: dict[str, Any],
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
        preserve_enabled: bool = True,
    ) -> None:
        existing = self._parse_translation_ai(profile)

        provider = str(payload.get("provider") or "auto").strip().lower()
        if provider not in _ALLOWED_PROVIDERS:
            raise ValueError(f"invalid_provider:{provider}")
        fallback = str(payload.get("fallback_provider") or "none").strip().lower()
        if fallback not in _ALLOWED_FALLBACKS:
            raise ValueError(f"invalid_fallback_provider:{fallback}")

        api_key: str | None
        if clear_api_key:
            api_key = None
        elif keep_existing_api_key or "api_key" not in payload:
            api_key = existing.api_key
        else:
            incoming = payload.get("api_key")
            if incoming is None:
                api_key = existing.api_key
            else:
                cleaned_key = str(incoming).strip()
                api_key = cleaned_key or None

        try:
            timeout = float(
                payload.get("timeout_seconds") if payload.get("timeout_seconds") is not None else 90.0
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_timeout_seconds") from exc
        if timeout <= 0 or timeout > 600:
            raise ValueError("invalid_timeout_seconds")

        next_enabled = bool(existing.enabled) if preserve_enabled else bool(payload.get("enabled"))
        profile.update(
            {
                "enabled": next_enabled,
                "provider": provider,
                "model": str(payload.get("model") or "").strip(),
                "api_key": api_key or "",
                "base_url": str(payload.get("base_url") or "").strip(),
                "timeout_seconds": timeout,
                "fallback_provider": fallback,
                "fallback_model": str(payload.get("fallback_model") or "").strip(),
            }
        )

    @staticmethod
    def _parse_translation_ai(raw: Any) -> TranslationAiConfig:
        if not isinstance(raw, dict):
            return TranslationAiConfig()
        # Multi-profile store: parse the active profile dict only.
        if isinstance(raw.get("profiles"), list):
            active_id = str(raw.get("active_profile_id") or "").strip()
            profiles = [p for p in raw["profiles"] if isinstance(p, dict)]
            chosen: dict[str, Any] | None = None
            for profile in profiles:
                if str(profile.get("id") or "") == active_id:
                    chosen = profile
                    break
            if chosen is None and profiles:
                chosen = profiles[0]
            raw = chosen if chosen is not None else {}
            if not isinstance(raw, dict):
                return TranslationAiConfig()
        provider = str(raw.get("provider") or "auto").strip().lower()
        if provider not in _ALLOWED_PROVIDERS:
            provider = "auto"
        fallback = str(raw.get("fallback_provider") or "none").strip().lower()
        if fallback not in _ALLOWED_FALLBACKS:
            fallback = "none"
        try:
            timeout = float(raw.get("timeout_seconds") if raw.get("timeout_seconds") is not None else 90.0)
        except (TypeError, ValueError):
            timeout = 90.0
        key = str(raw.get("api_key") or "").strip()
        return TranslationAiConfig(
            enabled=bool(raw.get("enabled")),
            provider=provider,
            model=str(raw.get("model") or "").strip(),
            api_key=key or None,
            base_url=str(raw.get("base_url") or "").strip(),
            timeout_seconds=timeout,
            fallback_provider=fallback,
            fallback_model=str(raw.get("fallback_model") or "").strip(),
        )

    def get_tts_ai(self, workspace_id: UUID | None) -> TtsAiConfig:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(TTS_AI_KEY)
        _active_id, profiles = self._normalize_tts_profiles(raw)
        active = self._find_tts_profile(profiles, _active_id) or profiles[0]
        return self._parse_tts_ai(active)

    def get_tts_ai_public(self, workspace_id: UUID | None) -> dict[str, Any]:
        from src.tts_pipeline.provider_factory import light_tts_import_ready

        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(TTS_AI_KEY)
        active_id, profiles = self._normalize_tts_profiles(raw)
        active = self._find_tts_profile(profiles, active_id) or profiles[0]
        cfg = self._parse_tts_ai(active)
        key = (cfg.api_key or "").strip()
        source = "workspace_db" if cfg.enabled else "env"
        options = dict(cfg.options_json or {})
        options.pop("runtime", None)  # authority lives on top-level runtime
        profile_summaries = [
            self._tts_profile_summary(p, active_id=str(active.get("id") or active_id)) for p in profiles
        ]
        return {
            "enabled": cfg.enabled,
            "provider": cfg.provider,
            "voice_id": cfg.voice_id,
            "speaking_rate": cfg.speaking_rate,
            "language_code": cfg.language_code,
            "model_id": cfg.model_id,
            "api_key_set": bool(key),
            "api_key_masked": mask_secret(key),
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_voice_id": cfg.fallback_voice_id,
            "local_backend": cfg.local_backend,
            "device": cfg.device,
            "cli_binary": cfg.cli_binary,
            "options_json": options,
            "runtime": normalize_runtime(cfg.runtime),
            "live_import_ok": light_tts_import_ready(cfg.provider),
            "source": source,
            "active_profile_id": str(active.get("id") or active_id),
            "active_profile_name": str(active.get("name") or DEFAULT_TTS_PROFILE_NAME),
            "profiles": profile_summaries,
            "focus_profile_id": None,
        }

    def get_tts_ai_profile_public(self, workspace_id: UUID | None, profile_id: str) -> dict[str, Any]:
        """Public view of one setup — does not change active."""
        from src.tts_pipeline.provider_factory import light_tts_import_ready

        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(TTS_AI_KEY)
        active_id, profiles = self._normalize_tts_profiles(raw)
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        active = self._find_tts_profile(profiles, active_id) or profiles[0]
        cfg = self._parse_tts_ai(target)
        key = (cfg.api_key or "").strip()
        options = dict(cfg.options_json or {})
        options.pop("runtime", None)
        profile_summaries = [
            self._tts_profile_summary(p, active_id=str(active.get("id") or active_id)) for p in profiles
        ]
        return {
            "enabled": cfg.enabled,
            "provider": cfg.provider,
            "voice_id": cfg.voice_id,
            "speaking_rate": cfg.speaking_rate,
            "language_code": cfg.language_code,
            "model_id": cfg.model_id,
            "api_key_set": bool(key),
            "api_key_masked": mask_secret(key),
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_voice_id": cfg.fallback_voice_id,
            "local_backend": cfg.local_backend,
            "device": cfg.device,
            "cli_binary": cfg.cli_binary,
            "options_json": options,
            "runtime": normalize_runtime(cfg.runtime),
            "live_import_ok": light_tts_import_ready(cfg.provider),
            "source": "workspace_db" if cfg.enabled else "env",
            "active_profile_id": str(active.get("id") or active_id),
            "active_profile_name": str(active.get("name") or DEFAULT_TTS_PROFILE_NAME),
            "profiles": profile_summaries,
            "focus_profile_id": str(target.get("id") or profile_id),
        }

    def create_tts_ai_profile(self, workspace_id: UUID | None, *, name: str) -> dict[str, Any]:
        """Create a blank TTS setup without changing the active setup."""
        workspace = self._resolve_workspace(workspace_id)
        cleaned_name = self._validate_tts_profile_name(name)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        self._ensure_unique_tts_profile_name(profiles, cleaned_name)
        profile_id = str(uuid4())
        blank = self._blank_tts_profile(profile_id=profile_id, name=cleaned_name)
        profiles.append(blank)
        store = {"active_profile_id": active_id, "profiles": profiles}
        meta[TTS_AI_KEY] = store
        self._persist_workspace_settings(workspace, meta)
        return blank

    def set_tts_ai_profile_enabled(
        self, workspace_id: UUID | None, profile_id: str, *, enabled: bool
    ) -> dict[str, Any]:
        """Toggle workspace override for one setup from the overview list."""
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        target["enabled"] = bool(enabled)
        meta[TTS_AI_KEY] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def set_tts_ai_profile(
        self,
        workspace_id: UUID | None,
        profile_id: str,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TtsAiConfig:
        """Save connection fields for one setup without changing active."""
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        self._apply_tts_payload_to_profile(
            target,
            payload,
            keep_existing_api_key=keep_existing_api_key,
            clear_api_key=clear_api_key,
        )
        meta[TTS_AI_KEY] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return self._parse_tts_ai(target)

    def rename_tts_ai_profile(
        self, workspace_id: UUID | None, profile_id: str, *, name: str
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        cleaned_name = self._validate_tts_profile_name(name)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        self._ensure_unique_tts_profile_name(profiles, cleaned_name, exclude_id=str(target["id"]))
        target["name"] = cleaned_name
        meta[TTS_AI_KEY] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def activate_tts_ai_profile(self, workspace_id: UUID | None, profile_id: str) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        _active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        meta[TTS_AI_KEY] = {"active_profile_id": str(target["id"]), "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return target

    def reorder_tts_ai_profiles(
        self, workspace_id: UUID | None, profile_ids: list[str]
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        ordered = self._reorder_profiles_by_ids(profiles, profile_ids)
        meta[TTS_AI_KEY] = {"active_profile_id": active_id, "profiles": ordered}
        self._persist_workspace_settings(workspace, meta)
        return self.get_tts_ai_public(workspace_id)

    def delete_tts_ai_profile(self, workspace_id: UUID | None, profile_id: str) -> None:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        if len(profiles) <= 1:
            raise ValueError("last_profile")
        remaining = [p for p in profiles if str(p.get("id")) != str(target["id"])]
        next_active = active_id
        if str(active_id) == str(target["id"]):
            next_active = str(remaining[0]["id"])
        meta[TTS_AI_KEY] = {"active_profile_id": next_active, "profiles": remaining}
        self._persist_workspace_settings(workspace, meta)

    def patch_tts_ai_runtime(
        self,
        workspace_id: UUID | None,
        *,
        last_install: dict[str, Any] | None = None,
        last_probe: dict[str, Any] | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist install/probe snapshot on a setup (default: active) without a full settings Save."""
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        target = self._find_tts_profile(profiles, profile_id) if profile_id else None
        if target is None:
            target = self._find_tts_profile(profiles, active_id) or profiles[0]
        runtime = merge_runtime(target.get("runtime"), last_install=last_install, last_probe=last_probe)
        target["runtime"] = runtime
        opts = target.get("options_json")
        if isinstance(opts, dict) and "runtime" in opts:
            cleaned = dict(opts)
            cleaned.pop("runtime", None)
            target["options_json"] = cleaned
        meta[TTS_AI_KEY] = {"active_profile_id": active_id, "profiles": profiles}
        self._persist_workspace_settings(workspace, meta)
        return runtime

    def set_tts_ai(
        self,
        workspace_id: UUID | None,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TtsAiConfig:
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        existing_profile = self._find_tts_profile(profiles, active_id) or profiles[0]
        self._apply_tts_payload_to_profile(
            existing_profile,
            payload,
            keep_existing_api_key=keep_existing_api_key,
            clear_api_key=clear_api_key,
            preserve_enabled=False,
        )
        meta[TTS_AI_KEY] = {
            "active_profile_id": str(existing_profile["id"]),
            "profiles": profiles,
        }
        self._persist_workspace_settings(workspace, meta)
        return self._parse_tts_ai(existing_profile)

    def _apply_tts_payload_to_profile(
        self,
        profile: dict[str, Any],
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
        preserve_enabled: bool = True,
    ) -> None:
        existing = self._parse_tts_ai(profile)

        provider = str(payload.get("provider") or "auto").strip().lower()
        if not is_allowed_tts_provider(provider):
            raise ValueError(f"invalid_provider:{provider}")
        fallback = str(payload.get("fallback_provider") or "none").strip().lower()
        if not is_allowed_tts_fallback(fallback):
            raise ValueError(f"invalid_fallback_provider:{fallback}")
        local_backend = str(payload.get("local_backend") or "auto").strip().lower()
        if local_backend not in _ALLOWED_TTS_LOCAL_BACKENDS:
            raise ValueError(f"invalid_local_backend:{local_backend}")
        device = str(payload.get("device") or "auto").strip().lower()
        if device not in _ALLOWED_TTS_DEVICES:
            raise ValueError(f"invalid_device:{device}")

        api_key: str | None
        if clear_api_key:
            api_key = None
        elif keep_existing_api_key or "api_key" not in payload:
            api_key = existing.api_key
        else:
            incoming = payload.get("api_key")
            if incoming is None:
                api_key = existing.api_key
            else:
                cleaned_key = str(incoming).strip()
                api_key = cleaned_key or None

        try:
            timeout = float(payload.get("timeout_seconds") if payload.get("timeout_seconds") is not None else 120.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_timeout_seconds") from exc
        if timeout <= 0 or timeout > 600:
            raise ValueError("invalid_timeout_seconds")

        try:
            speaking_rate = float(payload.get("speaking_rate") if payload.get("speaking_rate") is not None else 1.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_speaking_rate") from exc
        if speaking_rate < 0.5 or speaking_rate > 2.0:
            raise ValueError("invalid_speaking_rate")

        options_raw = payload.get("options_json")
        if options_raw is None:
            options: dict[str, Any] = dict(existing.options_json or {})
        elif isinstance(options_raw, dict):
            options = dict(options_raw)
        else:
            raise ValueError("invalid_options_json")
        options.pop("runtime", None)

        runtime = normalize_runtime(existing.runtime)
        if isinstance(payload.get("runtime"), dict):
            runtime = normalize_runtime(payload.get("runtime"))

        next_enabled = bool(existing.enabled) if preserve_enabled else bool(payload.get("enabled"))
        profile.update(
            {
                "enabled": next_enabled,
                "provider": provider,
                "voice_id": str(payload.get("voice_id") or "").strip(),
                "speaking_rate": speaking_rate,
                "language_code": str(payload.get("language_code") or "vi").strip() or "vi",
                "model_id": str(payload.get("model_id") or "").strip(),
                "api_key": api_key or "",
                "base_url": str(payload.get("base_url") or "").strip(),
                "timeout_seconds": timeout,
                "fallback_provider": fallback,
                "fallback_voice_id": str(payload.get("fallback_voice_id") or "").strip(),
                "local_backend": local_backend,
                "device": device,
                "cli_binary": str(payload.get("cli_binary") or "").strip(),
                "options_json": options,
                "runtime": runtime,
            }
        )

    def _persist_workspace_settings(self, workspace: Workspace, meta: dict[str, Any]) -> None:
        workspace.settings_json = meta
        if hasattr(workspace, "_sa_instance_state"):
            flag_modified(workspace, "settings_json")
        self.db.add(workspace)
        self.db.commit()
        if hasattr(self.db, "refresh"):
            try:
                self.db.refresh(workspace)
            except Exception:
                pass

    @classmethod
    def _normalize_tts_profiles(cls, raw: Any) -> tuple[str, list[dict[str, Any]]]:
        """Return (active_profile_id, profiles). Migrates legacy flat tts_ai blobs."""
        if isinstance(raw, dict) and isinstance(raw.get("profiles"), list) and raw["profiles"]:
            profiles: list[dict[str, Any]] = []
            for item in raw["profiles"]:
                if not isinstance(item, dict):
                    continue
                profile = dict(item)
                profile_id = str(profile.get("id") or "").strip() or str(uuid4())
                profile["id"] = profile_id
                name = str(profile.get("name") or "").strip() or DEFAULT_TTS_PROFILE_NAME
                profile["name"] = name
                profiles.append(profile)
            if not profiles:
                blank = cls._blank_tts_profile(profile_id=DEFAULT_TTS_PROFILE_ID, name=DEFAULT_TTS_PROFILE_NAME)
                return str(blank["id"]), [blank]
            active_id = str(raw.get("active_profile_id") or "").strip()
            if not active_id or cls._find_tts_profile(profiles, active_id) is None:
                active_id = str(profiles[0]["id"])
            return active_id, profiles

        if isinstance(raw, dict) and ("provider" in raw or "enabled" in raw or "voice_id" in raw):
            profile_id = DEFAULT_TTS_PROFILE_ID
            legacy = dict(raw)
            legacy.pop("profiles", None)
            legacy.pop("active_profile_id", None)
            legacy["id"] = profile_id
            legacy["name"] = DEFAULT_TTS_PROFILE_NAME
            return profile_id, [legacy]

        blank = cls._blank_tts_profile(profile_id=DEFAULT_TTS_PROFILE_ID, name=DEFAULT_TTS_PROFILE_NAME)
        return str(blank["id"]), [blank]

    @staticmethod
    def _tts_profile_summary(profile: dict[str, Any], *, active_id: str) -> dict[str, Any]:
        """Public list row for one setup — connection fields only, never raw api_key."""
        cfg = WorkspaceSettingsService._parse_tts_ai(profile)
        key = (cfg.api_key or "").strip()
        return {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or DEFAULT_TTS_PROFILE_NAME),
            "provider": cfg.provider,
            "enabled": bool(cfg.enabled),
            "voice_id": cfg.voice_id,
            "speaking_rate": cfg.speaking_rate,
            "language_code": cfg.language_code,
            "model_id": cfg.model_id,
            "api_key_set": bool(key),
            "api_key_masked": mask_secret(key),
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_voice_id": cfg.fallback_voice_id,
            "local_backend": cfg.local_backend,
            "device": cfg.device,
            "cli_binary": cfg.cli_binary,
            "is_active": str(profile.get("id") or "") == str(active_id),
            "runtime": normalize_runtime(cfg.runtime),
        }

    @staticmethod
    def _find_tts_profile(profiles: list[dict[str, Any]], profile_id: str) -> dict[str, Any] | None:
        wanted = str(profile_id or "").strip()
        if not wanted:
            return None
        for profile in profiles:
            if str(profile.get("id") or "") == wanted:
                return profile
        return None

    @staticmethod
    def _reorder_profiles_by_ids(
        profiles: list[dict[str, Any]], profile_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Return profiles in ``profile_ids`` order. Must be a permutation of current ids."""
        wanted = [str(item or "").strip() for item in profile_ids]
        if not wanted or any(not item for item in wanted):
            raise ValueError("invalid_profile_order")
        if len(wanted) != len(set(wanted)):
            raise ValueError("invalid_profile_order")
        by_id = {str(profile.get("id") or ""): profile for profile in profiles}
        if "" in by_id:
            raise ValueError("invalid_profile_order")
        if set(wanted) != set(by_id.keys()):
            raise ValueError("invalid_profile_order")
        return [by_id[profile_id] for profile_id in wanted]

    @staticmethod
    def _blank_tts_profile(*, profile_id: str, name: str) -> dict[str, Any]:
        return {
            "id": profile_id,
            "name": name,
            "enabled": False,
            "provider": "auto",
            "voice_id": "",
            "speaking_rate": 1.0,
            "language_code": "vi",
            "model_id": "",
            "api_key": "",
            "base_url": "",
            "timeout_seconds": 120.0,
            "fallback_provider": "none",
            "fallback_voice_id": "",
            "local_backend": "auto",
            "device": "auto",
            "cli_binary": "",
            "options_json": {},
            "runtime": normalize_runtime(None),
        }

    @staticmethod
    def _validate_tts_profile_name(name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned or len(cleaned) > 80:
            raise ValueError("invalid_profile_name")
        return cleaned

    @staticmethod
    def _ensure_unique_tts_profile_name(
        profiles: list[dict[str, Any]],
        name: str,
        *,
        exclude_id: str | None = None,
    ) -> None:
        needle = name.casefold()
        for profile in profiles:
            if exclude_id and str(profile.get("id")) == exclude_id:
                continue
            if str(profile.get("name") or "").strip().casefold() == needle:
                raise ValueError("duplicate_name")

    @staticmethod
    def _parse_tts_ai(raw: Any) -> TtsAiConfig:
        if not isinstance(raw, dict):
            return TtsAiConfig()
        # Multi-profile store: parse the active profile dict only.
        if isinstance(raw.get("profiles"), list):
            active_id = str(raw.get("active_profile_id") or "").strip()
            profiles = [p for p in raw["profiles"] if isinstance(p, dict)]
            chosen = None
            for profile in profiles:
                if str(profile.get("id") or "") == active_id:
                    chosen = profile
                    break
            if chosen is None and profiles:
                chosen = profiles[0]
            raw = chosen if chosen is not None else {}
        provider = str(raw.get("provider") or "auto").strip().lower()
        if not is_allowed_tts_provider(provider):
            provider = "auto"
        fallback = str(raw.get("fallback_provider") or "none").strip().lower()
        if not is_allowed_tts_fallback(fallback):
            fallback = "none"
        local_backend = str(raw.get("local_backend") or "auto").strip().lower()
        if local_backend not in _ALLOWED_TTS_LOCAL_BACKENDS:
            local_backend = "auto"
        device = str(raw.get("device") or "auto").strip().lower()
        if device not in _ALLOWED_TTS_DEVICES:
            device = "auto"
        try:
            timeout = float(raw.get("timeout_seconds") if raw.get("timeout_seconds") is not None else 120.0)
        except (TypeError, ValueError):
            timeout = 120.0
        try:
            speaking_rate = float(raw.get("speaking_rate") if raw.get("speaking_rate") is not None else 1.0)
        except (TypeError, ValueError):
            speaking_rate = 1.0
        key = str(raw.get("api_key") or "").strip()
        options_raw = raw.get("options_json")
        options = dict(options_raw) if isinstance(options_raw, dict) else {}
        options.pop("runtime", None)
        runtime = normalize_runtime(raw.get("runtime"))
        if not runtime.get("last_install") and not runtime.get("last_probe"):
            # Legacy: runtime nested under options_json
            nested = options_raw.get("runtime") if isinstance(options_raw, dict) else None
            if isinstance(nested, dict):
                runtime = normalize_runtime(nested)
        return TtsAiConfig(
            enabled=bool(raw.get("enabled")),
            provider=provider,
            voice_id=str(raw.get("voice_id") or "").strip(),
            speaking_rate=speaking_rate,
            language_code=str(raw.get("language_code") or "vi").strip() or "vi",
            model_id=str(raw.get("model_id") or "").strip(),
            api_key=key or None,
            base_url=str(raw.get("base_url") or "").strip(),
            timeout_seconds=timeout,
            fallback_provider=fallback,
            fallback_voice_id=str(raw.get("fallback_voice_id") or "").strip(),
            local_backend=local_backend,
            device=device,
            cli_binary=str(raw.get("cli_binary") or "").strip(),
            options_json=options,
            runtime=runtime,
        )
