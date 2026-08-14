"""Fail-closed authority for the one Ops TTS setup that is visibly On."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.services.workspace_settings_service import TtsAiConfig, WorkspaceSettingsService
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode


TTS_PROFILE_AUTHORITY_SCHEMA = "tts_active_profile_authority_v1"
_PRODUCTION_FORBIDDEN_PROVIDERS = frozenset(
    {"", "auto", "none", "off", "placeholder", "placeholder_tone_tts"}
)


def bind_active_tts_profile_authority(db: Session, workspace_id: UUID) -> dict[str, Any]:
    """Return a secret-free snapshot of the active, enabled TTS setup."""

    settings = WorkspaceSettingsService(db)
    try:
        profile_id, profile_name, cfg = settings.get_enabled_tts_ai_profile(
            workspace_id
        )
    except ValueError as exc:
        code = str(exc)
        if code == "tts_multiple_active_setups":
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED,
                "Multiple TTS setups are On. Turn off all but one setup, then run Generate TTS again.",
            ) from exc
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED,
            "No TTS setup is On. Turn on exactly one setup in Ops Console > TTS settings, then run Generate TTS again.",
        ) from exc
    _validate_production_config(cfg, profile_id=profile_id, profile_name=profile_name)
    fingerprint = tts_profile_config_fingerprint(cfg)
    return {
        "schema_version": TTS_PROFILE_AUTHORITY_SCHEMA,
        "workspace_id": str(workspace_id),
        "profile_id": profile_id,
        "profile_name": profile_name,
        "provider": _normalize_provider(cfg.provider),
        "model_id": str(cfg.model_id or ""),
        "voice_id": str(cfg.voice_id or ""),
        "language_code": str(cfg.language_code or "vi"),
        "speaking_rate": float(cfg.speaking_rate),
        "local_backend": str(cfg.local_backend or "auto"),
        "device": str(cfg.device or "auto"),
        "fallback_provider": "none",
        "configured_fallback_suppressed": str(
            cfg.fallback_provider or "none"
        ).strip().lower()
        not in {"", "none"},
        "config_fingerprint": fingerprint,
    }


def resolve_active_tts_profile_authority(
    db: Session,
    workspace_id: UUID,
    authority: dict[str, Any] | None,
) -> tuple[TtsAiConfig, dict[str, Any]]:
    """Verify the bound setup is still the one visibly On, then load secrets.

    Secrets and connector options stay in workspace settings. The durable job
    stores only the fingerprint, so changing/toggling a setup while queued makes
    the job fail instead of silently using another model.
    """

    current = bind_active_tts_profile_authority(db, workspace_id)
    if not isinstance(authority, dict) or not authority:
        return _production_config(db, workspace_id), current
    if str(authority.get("schema_version") or "") != TTS_PROFILE_AUTHORITY_SCHEMA:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
            "TTS job has a legacy or invalid voice authority. Create a new TTS job from the setup currently On.",
        )
    if str(authority.get("workspace_id") or "") != str(workspace_id):
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
            "TTS setup authority belongs to another workspace.",
        )
    for field in ("profile_id", "provider", "model_id", "voice_id", "config_fingerprint"):
        if str(authority.get(field) or "") != str(current.get(field) or ""):
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                "The TTS setup was switched, disabled, or edited while this job was queued. Start Generate TTS again.",
            )
    return _production_config(db, workspace_id), current


def assert_manifest_tts_authority_active(
    db: Session,
    workspace_id: UUID,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    """Block render/reuse when narration belongs to an Off or changed setup."""

    outputs = dict(manifest.get("current_outputs") or {})
    joined = [dict(item) for item in list(outputs.get("joined_narration") or []) if isinstance(item, dict)]
    if any(str(item.get("role") or "") == "verified_no_dialogue_source_audio" for item in joined):
        return None
    authority = dict(dict(manifest.get("provider_summary") or {}).get("tts_authority") or {})
    if not authority:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
            "Current narration predates single-setup TTS authority. Generate TTS again with the setup currently On before rendering.",
        )
    _cfg, current = resolve_active_tts_profile_authority(
        db,
        workspace_id,
        authority,
    )
    return current


def tts_profile_config_fingerprint(cfg: TtsAiConfig) -> str:
    """Hash all synthesis-affecting fields without persisting credentials."""

    api_key = str(cfg.api_key or "")
    service_account_json = str(cfg.google_service_account_json or "")
    base_url = str(cfg.base_url or "")
    options = dict(cfg.options_json or {})
    payload = {
        "schema_version": TTS_PROFILE_AUTHORITY_SCHEMA,
        "enabled": bool(cfg.enabled),
        "provider": _normalize_provider(cfg.provider),
        "voice_id": str(cfg.voice_id or ""),
        "speaking_rate": float(cfg.speaking_rate),
        "language_code": str(cfg.language_code or "vi"),
        "model_id": str(cfg.model_id or ""),
        "api_key_sha256": hashlib.sha256(api_key.encode("utf-8")).hexdigest(),
        "credential_mode": str(cfg.credential_mode or "api_key").strip().lower(),
        "google_service_account_sha256": hashlib.sha256(
            service_account_json.encode("utf-8")
        ).hexdigest(),
        "base_url_sha256": hashlib.sha256(base_url.encode("utf-8")).hexdigest(),
        "timeout_seconds": float(cfg.timeout_seconds),
        "fallback_provider": str(cfg.fallback_provider or "none").strip().lower(),
        "fallback_voice_id": str(cfg.fallback_voice_id or ""),
        "local_backend": str(cfg.local_backend or "auto"),
        "device": str(cfg.device or "auto"),
        "cli_binary": str(cfg.cli_binary or ""),
        "options_sha256": hashlib.sha256(
            json.dumps(
                options,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _production_config(db: Session, workspace_id: UUID) -> TtsAiConfig:
    try:
        _profile_id, _profile_name, cfg = (
            WorkspaceSettingsService(db).get_enabled_tts_ai_profile(workspace_id)
        )
    except ValueError as exc:
        code = str(exc)
        message = (
            "Multiple TTS setups are On. Turn off all but one setup, then run Generate TTS again."
            if code == "tts_multiple_active_setups"
            else "No TTS setup is On. Turn on exactly one setup in Ops Console > TTS settings, then run Generate TTS again."
        )
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED,
            message,
        ) from exc
    _validate_production_config(cfg, profile_id="", profile_name="")
    # A saved fallback is never allowed to cross the production boundary. The
    # validation above reports it; this replacement is defense in depth.
    return replace(cfg, fallback_provider="none", fallback_voice_id="")


def _validate_production_config(
    cfg: TtsAiConfig,
    *,
    profile_id: str,
    profile_name: str,
) -> None:
    label = profile_name or profile_id or "current"
    if not bool(cfg.enabled):
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED,
            "No TTS setup is On. Turn on exactly one setup in Ops Console > TTS settings, then run Generate TTS again.",
        )
    provider = _normalize_provider(cfg.provider)
    if provider in _PRODUCTION_FORBIDDEN_PROVIDERS:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED,
            f"TTS setup '{label}' must select one explicit production provider; provider={provider or 'empty'} is not allowed.",
        )
    if not str(cfg.voice_id or "").strip():
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED,
            f"TTS setup '{label}' is On but has no Voice ID.",
        )


def _normalize_provider(value: str) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    if raw == "omnivoice_studio":
        return "omnivoice"
    return raw
