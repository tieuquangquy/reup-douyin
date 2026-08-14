"""Workspace-scoped operator settings persisted in ``workspaces.settings_json``."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.db.bootstrap import ensure_default_workspace
from src.models.foundation import Workspace
from src.tts_pipeline.runtime_snapshot import merge_runtime, normalize_runtime, scope_runtime_to_provider

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
        "google_gemini",
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
        "google_gemini",
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


def _google_service_account_context(profile_id: str) -> str:
    identifier = str(profile_id or "default").strip() or "default"
    return f"tts-google-service-account:{identifier}"


def _encrypt_google_service_account(value: str, profile_id: str) -> str:
    from src.core.settings import get_settings
    from src.publish.services.platform_credential_key_store import (
        PlatformCredentialKeyStoreError,
        resolve_platform_credential_key_ref,
    )
    from src.publish.services.platform_secret_envelope import PlatformSecretEnvelope, PlatformSecretEnvelopeError

    try:
        key_ref = resolve_platform_credential_key_ref(get_settings(), create_local=True)
        return PlatformSecretEnvelope(key_ref=key_ref).encrypt(
            value,
            context=_google_service_account_context(profile_id),
        )
    except (PlatformCredentialKeyStoreError, PlatformSecretEnvelopeError) as exc:
        raise ValueError("google_service_account_encryption_unavailable") from exc


def _decrypt_google_service_account(value: str, profile_id: str) -> str | None:
    if not value:
        return None
    from src.core.settings import get_settings
    from src.publish.services.platform_credential_key_store import (
        PlatformCredentialKeyStoreError,
        resolve_platform_credential_key_ref,
    )
    from src.publish.services.platform_secret_envelope import PlatformSecretEnvelope

    try:
        key_ref = resolve_platform_credential_key_ref(get_settings(), create_local=False)
        return PlatformSecretEnvelope(key_ref=key_ref).decrypt(
            value,
            context=_google_service_account_context(profile_id),
        )
    except PlatformCredentialKeyStoreError:
        logger.warning("tts_google_credential_key_unavailable", extra={"profile_id": profile_id})
        return None


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
    api_key: str | None = field(default=None, repr=False)
    credential_mode: str = "api_key"
    google_service_account_json: str | None = field(default=None, repr=False)
    google_service_account_email: str = ""
    google_service_account_project_id: str = ""
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
        _profile_id, _profile_name, config = self.get_active_tts_ai_profile(
            workspace_id
        )
        return config

    def get_active_tts_ai_profile(
        self, workspace_id: UUID | None
    ) -> tuple[str, str, TtsAiConfig]:
        """Internal active setup identity plus raw synthesis configuration."""

        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(TTS_AI_KEY)
        _active_id, profiles = self._normalize_tts_profiles(raw)
        active = self._find_tts_profile(profiles, _active_id) or profiles[0]
        return (
            str(active.get("id") or _active_id),
            str(active.get("name") or DEFAULT_TTS_PROFILE_NAME),
            self._parse_tts_ai(active),
        )

    def get_enabled_tts_ai_profile(
        self, workspace_id: UUID | None
    ) -> tuple[str, str, TtsAiConfig]:
        """Return the one setup visibly On, independent of a legacy active pointer.

        Production synthesis treats the overview On switch as its authority. A
        stale ``active_profile_id`` must never make an Off setup authoritative,
        while multiple On rows are ambiguous and therefore fail closed.
        """

        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(TTS_AI_KEY)
        _active_id, profiles = self._normalize_tts_profiles(raw)
        enabled_profiles = [
            profile
            for profile in profiles
            if bool(self._parse_tts_ai(profile).enabled)
        ]
        if not enabled_profiles:
            raise ValueError("tts_active_setup_required")
        if len(enabled_profiles) != 1:
            raise ValueError("tts_multiple_active_setups")
        enabled = enabled_profiles[0]
        return (
            str(enabled.get("id") or ""),
            str(enabled.get("name") or DEFAULT_TTS_PROFILE_NAME),
            self._parse_tts_ai(enabled),
        )

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
        try:
            from src.tts_pipeline.http_connector import redact_http_connector_options

            options = redact_http_connector_options(options)
        except Exception:  # noqa: BLE001 - public serialization must remain resilient
            # Fail closed: a redaction regression must never turn into a raw
            # options/connector disclosure on a public settings endpoint.
            logger.warning("tts_public_options_redaction_failed")
            options = {}
        options.pop("runtime", None)  # authority lives on top-level runtime
        public_runtime = normalize_runtime(cfg.runtime)
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
            "credential_mode": cfg.credential_mode,
            "google_service_account_set": bool(cfg.google_service_account_json),
            "google_service_account_email": cfg.google_service_account_email,
            "google_service_account_project_id": cfg.google_service_account_project_id,
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_voice_id": cfg.fallback_voice_id,
            "local_backend": cfg.local_backend,
            "device": cfg.device,
            "cli_binary": cfg.cli_binary,
            "options_json": options,
            "runtime": public_runtime,
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
        try:
            from src.tts_pipeline.http_connector import redact_http_connector_options

            options = redact_http_connector_options(options)
        except Exception:  # noqa: BLE001 - public serialization must remain resilient
            logger.warning("tts_public_profile_options_redaction_failed")
            options = {}
        options.pop("runtime", None)
        public_runtime = normalize_runtime(cfg.runtime)
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
            "credential_mode": cfg.credential_mode,
            "google_service_account_set": bool(cfg.google_service_account_json),
            "google_service_account_email": cfg.google_service_account_email,
            "google_service_account_project_id": cfg.google_service_account_project_id,
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_voice_id": cfg.fallback_voice_id,
            "local_backend": cfg.local_backend,
            "device": cfg.device,
            "cli_binary": cfg.cli_binary,
            "options_json": options,
            "runtime": public_runtime,
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
        """Make one setup the exclusive On authority, or turn it Off.

        The overview switch represents production authority, not an independent
        per-row feature flag. Turning a row On therefore activates it and turns
        every other setup Off in the same database transaction.
        """
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        active_id, profiles = self._normalize_tts_profiles(meta.get(TTS_AI_KEY))
        target = self._find_tts_profile(profiles, profile_id)
        if target is None:
            raise ValueError("profile_not_found")
        if bool(enabled):
            for profile in profiles:
                profile["enabled"] = str(profile.get("id") or "") == str(
                    target.get("id") or ""
                )
            active_id = str(target["id"])
        else:
            target["enabled"] = False
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

        from src.tts_pipeline.google_cloud_credentials import (
            GOOGLE_CREDENTIAL_MODE_ADC,
            GOOGLE_CREDENTIAL_MODE_OAUTH_TOKEN,
            GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT,
            default_google_http_connector_options,
            normalize_google_credential_mode,
            validate_google_service_account_json,
        )

        credential_mode = normalize_google_credential_mode(
            payload.get("credential_mode", existing.credential_mode),
            provider=provider,
        )
        # Gemini can run either through the AI Studio API-key endpoint or the
        # billed Vertex AI endpoint.  Keep Google Cloud credential fields for
        # both slugs so a Vertex profile can use the same service-account
        # boundary as Google Cloud TTS.
        google_cloud_credential_provider = provider in {"google", "google_gemini"}
        if not google_cloud_credential_provider:
            credential_mode = "api_key"
        profile_id = str(profile.get("id") or "default")
        encrypted_service_account = str(profile.get("google_service_account_encrypted") or "").strip()
        service_account_email = existing.google_service_account_email
        service_account_project_id = existing.google_service_account_project_id
        clear_service_account = bool(payload.get("clear_google_service_account")) or not google_cloud_credential_provider
        incoming_service_account = payload.get("google_service_account_json")
        if clear_service_account:
            encrypted_service_account = ""
            service_account_email = ""
            service_account_project_id = ""
        elif incoming_service_account is not None and str(incoming_service_account).strip():
            metadata = validate_google_service_account_json(str(incoming_service_account))
            encrypted_service_account = _encrypt_google_service_account(
                metadata.normalized_json,
                profile_id,
            )
            service_account_email = metadata.client_email
            service_account_project_id = metadata.project_id
        if credential_mode in {GOOGLE_CREDENTIAL_MODE_SERVICE_ACCOUNT, GOOGLE_CREDENTIAL_MODE_ADC}:
            api_key = None
        elif google_cloud_credential_provider and credential_mode != GOOGLE_CREDENTIAL_MODE_OAUTH_TOKEN:
            api_key = None

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
        if provider == "google":
            options = default_google_http_connector_options(
                options,
                language_code=str(payload.get("language_code") or "vi").strip() or "vi",
            )
            from src.tts_pipeline.google_cloud_credentials import GOOGLE_CLOUD_TTS_BASE_URL

            persisted_base_url = GOOGLE_CLOUD_TTS_BASE_URL
        else:
            persisted_base_url = str(payload.get("base_url") or "").strip()
        if "http_connector" in options:
            try:
                from src.tts_pipeline.http_connector import normalize_http_connector_options

                # Validate before persisting. The manifest is declarative;
                # malformed paths/templates must not reach a worker.
                options = normalize_http_connector_options(options)
            except ValueError as exc:
                raise ValueError(f"invalid_http_connector:{str(exc)[:300]}") from exc

        runtime = scope_runtime_to_provider(existing.runtime, provider)
        if isinstance(payload.get("runtime"), dict):
            runtime = scope_runtime_to_provider(payload.get("runtime"), provider)

        voice_id = str(payload.get("voice_id") or "").strip()
        if provider == "google_gemini":
            from src.tts_pipeline.catalog import normalize_gemini_voice_id

            voice_id = normalize_gemini_voice_id(voice_id) or "Kore"

        next_enabled = bool(existing.enabled) if preserve_enabled else bool(payload.get("enabled"))
        profile.update(
            {
                "enabled": next_enabled,
                "provider": provider,
                "voice_id": voice_id,
                "speaking_rate": speaking_rate,
                "language_code": str(payload.get("language_code") or "vi").strip() or "vi",
                "model_id": str(payload.get("model_id") or "").strip(),
                "api_key": api_key or "",
                "credential_mode": credential_mode,
                "google_service_account_encrypted": encrypted_service_account,
                "google_service_account_email": service_account_email,
                "google_service_account_project_id": service_account_project_id,
                "base_url": persisted_base_url,
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
            "credential_mode": cfg.credential_mode,
            "google_service_account_set": bool(cfg.google_service_account_json),
            "google_service_account_email": cfg.google_service_account_email,
            "google_service_account_project_id": cfg.google_service_account_project_id,
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
            "credential_mode": "api_key",
            "google_service_account_encrypted": "",
            "google_service_account_email": "",
            "google_service_account_project_id": "",
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
        from src.tts_pipeline.google_cloud_credentials import normalize_google_credential_mode

        profile_id = str(raw.get("id") or "default")
        credential_mode = normalize_google_credential_mode(
            raw.get("credential_mode"),
            provider=provider,
        )
        encrypted_service_account = str(raw.get("google_service_account_encrypted") or "").strip()
        google_service_account_json = _decrypt_google_service_account(
            encrypted_service_account,
            profile_id,
        )
        options_raw = raw.get("options_json")
        options = dict(options_raw) if isinstance(options_raw, dict) else {}
        options.pop("runtime", None)
        runtime = scope_runtime_to_provider(raw.get("runtime"), provider)
        if not runtime.get("last_install") and not runtime.get("last_probe"):
            # Legacy: runtime nested under options_json
            nested = options_raw.get("runtime") if isinstance(options_raw, dict) else None
            if isinstance(nested, dict):
                runtime = scope_runtime_to_provider(nested, provider)
        voice_id = str(raw.get("voice_id") or "").strip()
        if provider == "google_gemini":
            from src.tts_pipeline.catalog import normalize_gemini_voice_id

            voice_id = normalize_gemini_voice_id(voice_id) or "Kore"
        return TtsAiConfig(
            enabled=bool(raw.get("enabled")),
            provider=provider,
            voice_id=voice_id,
            speaking_rate=speaking_rate,
            language_code=str(raw.get("language_code") or "vi").strip() or "vi",
            model_id=str(raw.get("model_id") or "").strip(),
            api_key=key or None,
            credential_mode=credential_mode,
            google_service_account_json=google_service_account_json,
            google_service_account_email=str(raw.get("google_service_account_email") or "").strip(),
            google_service_account_project_id=str(
                raw.get("google_service_account_project_id") or ""
            ).strip(),
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
