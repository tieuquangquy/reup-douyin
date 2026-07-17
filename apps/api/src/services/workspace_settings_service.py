"""Workspace-scoped operator settings persisted in ``workspaces.settings_json``."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

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
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(TRANSLATION_USER_PROMPT_KEY)
        if not isinstance(raw, str):
            return None
        text = raw.strip()
        return text or None

    def set_translation_user_prompt(self, workspace_id: UUID | None, prompt: str) -> str:
        """
        Persist operator dialogue-translation system prompt.

        Empty/whitespace clears the key so file/env/builtin fallbacks apply.
        Returns the stored prompt (empty string when cleared).
        """
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        cleaned = (prompt or "").strip()
        if cleaned:
            meta[TRANSLATION_USER_PROMPT_KEY] = cleaned
        else:
            meta.pop(TRANSLATION_USER_PROMPT_KEY, None)
        workspace.settings_json = meta
        # JSONB in-place / reassignment needs ORM dirty tracking in real sessions.
        if hasattr(workspace, "_sa_instance_state"):
            flag_modified(workspace, "settings_json")
        self.db.add(workspace)
        self.db.commit()
        if hasattr(self.db, "refresh"):
            try:
                self.db.refresh(workspace)
            except Exception:
                pass
        return cleaned

    def get_translation_ai(self, workspace_id: UUID | None) -> TranslationAiConfig:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(TRANSLATION_AI_KEY)
        return self._parse_translation_ai(raw)

    def get_translation_ai_public(self, workspace_id: UUID | None) -> dict[str, Any]:
        cfg = self.get_translation_ai(workspace_id)
        key = (cfg.api_key or "").strip()
        source = "workspace_db" if cfg.enabled else "env"
        return {
            "enabled": cfg.enabled,
            "provider": cfg.provider,
            "model": cfg.model,
            "api_key_set": bool(key),
            "api_key_masked": mask_secret(key),
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_model": cfg.fallback_model,
            "source": source,
        }

    def set_translation_ai(
        self,
        workspace_id: UUID | None,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TranslationAiConfig:
        workspace = self._resolve_workspace(workspace_id)

        existing = self._parse_translation_ai((workspace.settings_json or {}).get(TRANSLATION_AI_KEY))
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
            timeout = float(payload.get("timeout_seconds") if payload.get("timeout_seconds") is not None else 90.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_timeout_seconds") from exc
        if timeout <= 0 or timeout > 600:
            raise ValueError("invalid_timeout_seconds")

        stored = {
            "enabled": bool(payload.get("enabled")),
            "provider": provider,
            "model": str(payload.get("model") or "").strip(),
            "api_key": api_key or "",
            "base_url": str(payload.get("base_url") or "").strip(),
            "timeout_seconds": timeout,
            "fallback_provider": fallback,
            "fallback_model": str(payload.get("fallback_model") or "").strip(),
        }
        meta = dict(workspace.settings_json or {})
        meta[TRANSLATION_AI_KEY] = stored
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
        return self._parse_translation_ai(stored)

    # --- Caption AI (Phase 2.5 hard-sub) — independent of translation_ai ---

    def get_caption_prompt(self, workspace_id: UUID | None) -> str | None:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(CAPTION_PROMPT_KEY)
        if not isinstance(raw, str):
            return None
        text = raw.strip()
        return text or None

    def set_caption_prompt(self, workspace_id: UUID | None, prompt: str) -> str:
        """Persist hard-sub caption system prompt (does not touch translation_user_prompt)."""
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        cleaned = (prompt or "").strip()
        if cleaned:
            meta[CAPTION_PROMPT_KEY] = cleaned
        else:
            meta.pop(CAPTION_PROMPT_KEY, None)
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
        return cleaned

    def get_caption_ai(self, workspace_id: UUID | None) -> TranslationAiConfig:
        workspace = self._resolve_workspace(workspace_id)
        raw = (workspace.settings_json or {}).get(CAPTION_AI_KEY)
        return self._parse_translation_ai(raw)

    def get_caption_ai_public(self, workspace_id: UUID | None) -> dict[str, Any]:
        cfg = self.get_caption_ai(workspace_id)
        key = (cfg.api_key or "").strip()
        source = "workspace_db" if cfg.enabled else "env"
        return {
            "enabled": cfg.enabled,
            "provider": cfg.provider,
            "model": cfg.model,
            "api_key_set": bool(key),
            "api_key_masked": mask_secret(key),
            "base_url": cfg.base_url,
            "timeout_seconds": cfg.timeout_seconds,
            "fallback_provider": cfg.fallback_provider,
            "fallback_model": cfg.fallback_model,
            "source": source,
        }

    def set_caption_ai(
        self,
        workspace_id: UUID | None,
        payload: dict[str, Any],
        *,
        keep_existing_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> TranslationAiConfig:
        """Save Caption AI connection under caption_ai — never writes translation_ai."""
        workspace = self._resolve_workspace(workspace_id)

        existing = self._parse_translation_ai((workspace.settings_json or {}).get(CAPTION_AI_KEY))
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
            timeout = float(payload.get("timeout_seconds") if payload.get("timeout_seconds") is not None else 90.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_timeout_seconds") from exc
        if timeout <= 0 or timeout > 600:
            raise ValueError("invalid_timeout_seconds")

        stored = {
            "enabled": bool(payload.get("enabled")),
            "provider": provider,
            "model": str(payload.get("model") or "").strip(),
            "api_key": api_key or "",
            "base_url": str(payload.get("base_url") or "").strip(),
            "timeout_seconds": timeout,
            "fallback_provider": fallback,
            "fallback_model": str(payload.get("fallback_model") or "").strip(),
        }
        meta = dict(workspace.settings_json or {})
        meta[CAPTION_AI_KEY] = stored
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
        return self._parse_translation_ai(stored)

    @staticmethod
    def _parse_translation_ai(raw: Any) -> TranslationAiConfig:
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
        return self._parse_tts_ai(raw)

    def get_tts_ai_public(self, workspace_id: UUID | None) -> dict[str, Any]:
        from src.tts_pipeline.provider_factory import light_tts_import_ready

        cfg = self.get_tts_ai(workspace_id)
        key = (cfg.api_key or "").strip()
        source = "workspace_db" if cfg.enabled else "env"
        options = dict(cfg.options_json or {})
        options.pop("runtime", None)  # authority lives on top-level runtime
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
        }

    def patch_tts_ai_runtime(
        self,
        workspace_id: UUID | None,
        *,
        last_install: dict[str, Any] | None = None,
        last_probe: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist install/probe snapshot without requiring a full settings Save."""
        workspace = self._resolve_workspace(workspace_id)
        meta = dict(workspace.settings_json or {})
        raw = meta.get(TTS_AI_KEY)
        stored = dict(raw) if isinstance(raw, dict) else {}
        runtime = merge_runtime(stored.get("runtime"), last_install=last_install, last_probe=last_probe)
        stored["runtime"] = runtime
        opts = stored.get("options_json")
        if isinstance(opts, dict) and "runtime" in opts:
            cleaned = dict(opts)
            cleaned.pop("runtime", None)
            stored["options_json"] = cleaned
        meta[TTS_AI_KEY] = stored
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
        existing = self._parse_tts_ai((workspace.settings_json or {}).get(TTS_AI_KEY))

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

        # Runtime is owned by Install/Test endpoints — never wipe on Save.
        runtime = normalize_runtime(existing.runtime)
        if isinstance(payload.get("runtime"), dict):
            runtime = normalize_runtime(payload.get("runtime"))

        stored = {
            "enabled": bool(payload.get("enabled")),
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
        meta = dict(workspace.settings_json or {})
        meta[TTS_AI_KEY] = stored
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
        return self._parse_tts_ai(stored)

    @staticmethod
    def _parse_tts_ai(raw: Any) -> TtsAiConfig:
        if not isinstance(raw, dict):
            return TtsAiConfig()
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
