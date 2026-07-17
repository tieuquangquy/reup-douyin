from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.tts_pipeline.catalog import discover_tts_catalog
from src.tts_pipeline.edge_tts_provider import EdgeTtsProvider
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.providers import PlaceholderToneTtsProvider, TtsProvider
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput, VoiceConfig
from src.tts_pipeline.vieneu_tts_provider import VieNeuTtsProvider

logger = logging.getLogger(__name__)


@dataclass
class TtsProbeResult:
    ok: bool
    provider: str
    detail: str
    catalog: dict[str, Any] | None = None


def light_tts_import_ready(provider: str) -> bool | None:
    """Cheap import check for GET hydrate (no catalog / no model download)."""
    name = (provider or "").strip().lower()
    if name == "edge":
        try:
            import edge_tts  # noqa: F401

            return True
        except ImportError:
            return False
    if name == "vieneu":
        try:
            import vieneu  # noqa: F401

            return True
        except ImportError:
            return False
    if name == "auto":
        try:
            import vieneu  # noqa: F401

            return True
        except ImportError:
            pass
        try:
            import edge_tts  # noqa: F401

            return True
        except ImportError:
            return False
    return None


class FallbackTtsProvider:
    """Try primary provider; on failure optionally run fallback."""

    def __init__(
        self,
        primary: TtsProvider,
        fallback: TtsProvider | None = None,
        *,
        fallback_voice_id: str | None = None,
    ):
        self.primary = primary
        self.fallback = fallback
        self.fallback_voice_id = (fallback_voice_id or "").strip() or None
        self.provider_name = getattr(primary, "provider_name", primary.__class__.__name__)

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        try:
            return self.primary.synthesize(request)
        except Exception as primary_exc:
            if self.fallback is None:
                raise
            logger.warning(
                "tts_primary_failed_using_fallback",
                extra={
                    "primary": getattr(self.primary, "provider_name", type(self.primary).__name__),
                    "fallback": getattr(self.fallback, "provider_name", type(self.fallback).__name__),
                    "error": str(primary_exc)[:200],
                },
            )
            fallback_request = request
            if self.fallback_voice_id:
                fallback_request = TtsProviderInput(
                    text=request.text,
                    language_code=request.language_code,
                    voice_config=VoiceConfig(
                        voice_id=self.fallback_voice_id,
                        language_code=request.voice_config.language_code,
                        speaking_rate=request.voice_config.speaking_rate,
                    ),
                    target_duration_seconds=request.target_duration_seconds,
                )
            output = self.fallback.synthesize(fallback_request)
            warnings = list(output.warnings or [])
            warnings.append("tts_used_fallback_provider")
            meta = dict(output.provider_metadata or {})
            meta["fallback_used"] = True
            meta["primary_error"] = str(primary_exc)[:200]
            return TtsProviderOutput(
                audio_bytes=output.audio_bytes,
                duration_seconds=output.duration_seconds,
                mime_type=output.mime_type,
                file_extension=output.file_extension,
                provider_metadata=meta,
                warnings=warnings,
            )


class ConfiguredButUnavailableTtsProvider:
    """Settings-accepted vendor whose runtime adapter is not wired yet (or missing deps)."""

    def __init__(self, provider_name: str, message: str):
        self.provider_name = provider_name
        self.message = message

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, self.message)


def build_default_tts_provider(
    *,
    provider_name: str | None = None,
    workspace_tts: Any | None = None,
    edge_provider_factory: Callable[[], TtsProvider] | None = None,
    vieneu_provider_factory: Callable[[], TtsProvider] | None = None,
) -> TtsProvider:
    """
    Resolve TTS provider from workspace TTS AI settings (when enabled) or env.

    Providers: auto | edge | vieneu | google | azure | elevenlabs | openai |
    openai_compatible | http_custom | cli | placeholder
    """
    from src.core.settings import get_settings

    settings = get_settings()
    if workspace_tts is not None and bool(getattr(workspace_tts, "enabled", False)):
        return _build_from_workspace_tts(
            workspace_tts,
            env_settings=settings,
            edge_provider_factory=edge_provider_factory,
            vieneu_provider_factory=vieneu_provider_factory,
        )

    name = (provider_name or settings.audio_tts_provider or "auto").strip().lower()
    return _build_named_provider(
        name,
        env_settings=settings,
        voice_id=getattr(settings, "audio_tts_voice_id", "") or "",
        speaking_rate=float(getattr(settings, "audio_tts_speaking_rate", 1.0) or 1.0),
        api_key=(getattr(settings, "audio_tts_api_key", None) or "").strip() or None,
        base_url=(getattr(settings, "audio_tts_base_url", None) or "").strip(),
        model_id=(getattr(settings, "audio_tts_model_id", None) or "").strip(),
        local_backend=(getattr(settings, "audio_tts_local_backend", None) or "auto").strip().lower(),
        device=(getattr(settings, "audio_tts_device", None) or "auto").strip().lower(),
        cli_binary=(getattr(settings, "audio_tts_cli_binary", None) or "").strip(),
        timeout_seconds=float(getattr(settings, "audio_tts_timeout_seconds", 120.0) or 120.0),
        options={},
        edge_provider_factory=edge_provider_factory,
        vieneu_provider_factory=vieneu_provider_factory,
        fallback_name=(getattr(settings, "audio_tts_fallback_provider", None) or "none").strip().lower(),
        fallback_voice_id=(getattr(settings, "audio_tts_fallback_voice_id", None) or "").strip(),
    )


def _build_from_workspace_tts(
    workspace_tts: Any,
    *,
    env_settings: Any,
    edge_provider_factory: Callable[[], TtsProvider] | None,
    vieneu_provider_factory: Callable[[], TtsProvider] | None,
) -> TtsProvider:
    name = str(getattr(workspace_tts, "provider", "auto") or "auto").strip().lower()
    return _build_named_provider(
        name,
        env_settings=env_settings,
        voice_id=str(getattr(workspace_tts, "voice_id", "") or ""),
        speaking_rate=float(getattr(workspace_tts, "speaking_rate", 1.0) or 1.0),
        api_key=(getattr(workspace_tts, "api_key", None) or "").strip() or None,
        base_url=str(getattr(workspace_tts, "base_url", "") or "").strip(),
        model_id=str(getattr(workspace_tts, "model_id", "") or "").strip(),
        local_backend=str(getattr(workspace_tts, "local_backend", "auto") or "auto").strip().lower(),
        device=str(getattr(workspace_tts, "device", "auto") or "auto").strip().lower(),
        cli_binary=str(getattr(workspace_tts, "cli_binary", "") or "").strip(),
        timeout_seconds=float(getattr(workspace_tts, "timeout_seconds", 120.0) or 120.0),
        options=dict(getattr(workspace_tts, "options_json", None) or {}),
        edge_provider_factory=edge_provider_factory,
        vieneu_provider_factory=vieneu_provider_factory,
        fallback_name=str(getattr(workspace_tts, "fallback_provider", "none") or "none").strip().lower(),
        fallback_voice_id=str(getattr(workspace_tts, "fallback_voice_id", "") or "").strip(),
    )


def _build_named_provider(
    name: str,
    *,
    env_settings: Any,
    voice_id: str,
    speaking_rate: float,
    api_key: str | None,
    base_url: str,
    model_id: str,
    local_backend: str,
    device: str,
    cli_binary: str,
    timeout_seconds: float,
    options: dict[str, Any],
    edge_provider_factory: Callable[[], TtsProvider] | None,
    vieneu_provider_factory: Callable[[], TtsProvider] | None,
    fallback_name: str,
    fallback_voice_id: str,
) -> TtsProvider:
    primary = _make_provider(
        name,
        env_settings=env_settings,
        voice_id=voice_id,
        api_key=api_key,
        base_url=base_url,
        model_id=model_id,
        local_backend=local_backend,
        device=device,
        cli_binary=cli_binary,
        timeout_seconds=timeout_seconds,
        options=options,
        edge_provider_factory=edge_provider_factory,
        vieneu_provider_factory=vieneu_provider_factory,
    )
    if fallback_name in {"", "none"}:
        return primary
    fallback = _make_provider(
        fallback_name,
        env_settings=env_settings,
        voice_id=fallback_voice_id or voice_id,
        api_key=api_key,
        base_url=base_url,
        model_id=model_id,
        local_backend=local_backend,
        device=device,
        cli_binary=cli_binary,
        timeout_seconds=timeout_seconds,
        options=options,
        edge_provider_factory=edge_provider_factory,
        vieneu_provider_factory=vieneu_provider_factory,
    )
    return FallbackTtsProvider(primary, fallback, fallback_voice_id=fallback_voice_id or None)


def _make_provider(
    name: str,
    *,
    env_settings: Any,
    voice_id: str,
    api_key: str | None,
    base_url: str,
    model_id: str,
    local_backend: str,
    device: str,
    cli_binary: str,
    timeout_seconds: float,
    options: dict[str, Any],
    edge_provider_factory: Callable[[], TtsProvider] | None,
    vieneu_provider_factory: Callable[[], TtsProvider] | None,
) -> TtsProvider:
    _ = (timeout_seconds, device)

    if name in {"placeholder", "off", "none"}:
        return PlaceholderToneTtsProvider()

    if name == "edge":
        if edge_provider_factory is not None:
            return edge_provider_factory()
        return EdgeTtsProvider()

    if name == "vieneu":
        if vieneu_provider_factory is not None:
            return vieneu_provider_factory()
        return VieNeuTtsProvider(
            local_backend=local_backend,
            device=device,
            model_id=model_id,
            base_url=base_url,
            options=options,
        )

    if name == "cli":
        binary = cli_binary or "edge-tts"
        return ConfiguredButUnavailableTtsProvider(
            "cli",
            f"CLI TTS provider is configured (binary={binary}) but the adapter is not enabled yet. "
            "Use provider=edge or vieneu, or set fallback_provider=edge.",
        )

    if name in {"openai", "openai_compatible", "http_custom"}:
        if not base_url and name != "openai":
            return ConfiguredButUnavailableTtsProvider(
                name,
                f"{name} requires base_url (OpenAI-compatible or custom TTS HTTP endpoint).",
            )
        return ConfiguredButUnavailableTtsProvider(
            name,
            f"{name} settings are saved, but the HTTP TTS adapter is not enabled yet. "
            "Use provider=edge or vieneu for synthesis now, or set fallback_provider=edge.",
        )

    if name in {"google", "azure", "elevenlabs"}:
        if not api_key and name != "google":
            # google may use ADC later; still require explicit enable messaging
            pass
        if name in {"azure", "elevenlabs"} and not api_key:
            return ConfiguredButUnavailableTtsProvider(
                name,
                f"{name} requires an API key. Save api_key in Ops TTS settings.",
            )
        return ConfiguredButUnavailableTtsProvider(
            name,
            f"{name} settings are saved, but the cloud TTS adapter is not enabled yet. "
            "Use provider=edge or vieneu for synthesis now, or set fallback_provider=edge.",
        )

    # Custom Local/SDK slug (installed via Ops Install). Synthesis still needs a known adapter
    # or fallback until a generic runner is added.
    if name not in {"auto"}:
        return ConfiguredButUnavailableTtsProvider(
            name,
            f"Custom provider '{name}' is configured. Install the package via Ops, then set "
            "fallback_provider=edge or vieneu until a dedicated synthesize adapter exists for this slug.",
        )

    # auto
    if edge_provider_factory is not None:
        return edge_provider_factory()
    if vieneu_provider_factory is not None:
        return vieneu_provider_factory()

    prefer = str(getattr(env_settings, "audio_tts_provider", "auto") or "auto").strip().lower()
    # Prefer vieneu when explicitly requested via env auto-path installs; else edge.
    try:
        import vieneu  # noqa: F401

        if prefer in {"auto", "vieneu"}:
            logger.info("tts_provider_selected", extra={"provider": "vieneu"})
            return VieNeuTtsProvider(
                local_backend=local_backend or "auto",
                device=device or "auto",
                model_id=model_id,
                base_url=base_url,
                options=options,
            )
    except ImportError:
        pass

    try:
        import edge_tts  # noqa: F401

        logger.info("tts_provider_selected", extra={"provider": "edge_tts"})
        return EdgeTtsProvider()
    except ImportError:
        logger.warning(
            "tts_provider_fallback_placeholder",
            extra={"reason": "no_tts_sdk_installed"},
        )
        return PlaceholderToneTtsProvider()


def probe_tts_ai_client(workspace_tts: Any, *, settings: Any | None = None) -> TtsProbeResult:
    """Lightweight readiness check for Ops Test Connection (no long synthesis).

    When ok for edge/vieneu/auto, attaches a voices/styles/models catalog (sdk or curated).
    """
    from src.core.settings import get_settings

    cfg = workspace_tts
    env = settings or get_settings()
    if cfg is None or not bool(getattr(cfg, "enabled", False)):
        name = str(getattr(env, "audio_tts_provider", "auto") or "auto").strip().lower()
        language = str(getattr(env, "audio_tts_language_code", "vi") or "vi")
        result = _probe_named(
            name,
            api_key=getattr(env, "audio_tts_api_key", None),
            base_url=getattr(env, "audio_tts_base_url", ""),
        )
        return _attach_catalog(result, language_code=language)

    name = str(getattr(cfg, "provider", "auto") or "auto").strip().lower()
    language = str(getattr(cfg, "language_code", "vi") or "vi")
    result = _probe_named(
        name,
        api_key=getattr(cfg, "api_key", None),
        base_url=getattr(cfg, "base_url", ""),
    )
    return _attach_catalog(result, language_code=language)


def _attach_catalog(result: TtsProbeResult, *, language_code: str) -> TtsProbeResult:
    if not result.ok or result.provider not in {"edge", "vieneu", "auto"}:
        return result
    catalog = discover_tts_catalog(result.provider, language_code=language_code)
    result.catalog = catalog.to_dict()
    if catalog.warning and catalog.source == "curated":
        result.detail = f"{result.detail} · {catalog.warning}"
    return result


def _probe_named(name: str, *, api_key: str | None, base_url: str) -> TtsProbeResult:
    if name in {"placeholder", "off", "none"}:
        return TtsProbeResult(True, "placeholder", "Placeholder tone provider ready (test-only).")

    if name == "edge":
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return TtsProbeResult(False, "edge", "edge-tts not installed. Run: pip install edge-tts")
        return TtsProbeResult(True, "edge", "edge-tts import ready")

    if name == "vieneu":
        try:
            import vieneu  # noqa: F401
        except ImportError:
            return TtsProbeResult(False, "vieneu", "vieneu not installed. Run: pip install vieneu")
        return TtsProbeResult(True, "vieneu", "vieneu import ready")

    if name == "cli":
        return TtsProbeResult(True, "cli", "CLI provider settings accepted (runtime adapter pending).")

    if name in {"openai", "openai_compatible", "http_custom"}:
        if name != "openai" and not (base_url or "").strip():
            return TtsProbeResult(False, name, f"{name} requires base_url")
        return TtsProbeResult(
            True, name, f"{name} settings look valid (HTTP adapter pending for synthesis)."
        )

    if name in {"google", "azure", "elevenlabs"}:
        if name in {"azure", "elevenlabs"} and not (api_key or "").strip():
            return TtsProbeResult(False, name, f"{name} requires api_key")
        return TtsProbeResult(
            True, name, f"{name} settings accepted (cloud adapter pending for synthesis)."
        )

    if name != "auto":
        return TtsProbeResult(
            True,
            name,
            f"Custom provider '{name}' settings accepted. Set fallback_provider=edge/vieneu until "
            "a dedicated synthesize adapter exists.",
        )

    try:
        import vieneu  # noqa: F401

        return TtsProbeResult(True, "auto", "auto → vieneu available")
    except ImportError:
        pass
    try:
        import edge_tts  # noqa: F401

        return TtsProbeResult(True, "auto", "auto → edge-tts available")
    except ImportError:
        return TtsProbeResult(False, "auto", "Neither vieneu nor edge-tts is installed")
