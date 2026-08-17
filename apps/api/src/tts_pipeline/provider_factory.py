from __future__ import annotations

import importlib.util
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.tts_pipeline.catalog import discover_tts_catalog
from src.tts_pipeline.edge_tts_provider import EdgeTtsProvider
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.omnivoice_tts_provider import OmniVoiceTtsProvider
from src.tts_pipeline.providers import PlaceholderToneTtsProvider, TtsProvider
from src.tts_pipeline.remote_catalog import (
    REMOTE_TTS_DEFAULT_BASE_URLS,
    discover_remote_tts_catalog,
)
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput, VoiceConfig
from src.tts_pipeline.vieneu_tts_provider import VieNeuTtsProvider

logger = logging.getLogger(__name__)


def _module_importable(module_name: str) -> bool:
    """Check package availability without executing heavyweight native imports."""

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


@dataclass
class TtsProbeResult:
    ok: bool
    provider: str
    detail: str
    catalog: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)


def light_tts_import_ready(provider: str) -> bool | None:
    """Cheap import check for GET hydrate (no catalog / no model download)."""
    name = (provider or "").strip().lower()
    if name == "edge":
        return _module_importable("edge_tts")
    if name == "vieneu":
        return _module_importable("vieneu")
    if name in {"omnivoice", "omnivoice_studio", "omnivoice-studio"}:
        return _module_importable("omnivoice")
    if name == "google_cloud_tts":
        return _module_importable("google.genai")
    if name == "auto":
        return _module_importable("vieneu") or _module_importable("edge_tts")
    return None


class FallbackTtsProvider:
    """Try primary provider; on failure optionally run fallback."""

    def __init__(
        self,
        primary: TtsProvider,
        fallback: TtsProvider | None = None,
        *,
        fallback_voice_id: str | None = None,
        degrade_expressive_fallback: bool = False,
    ):
        self.primary = primary
        self.fallback = fallback
        self.fallback_voice_id = (fallback_voice_id or "").strip() or None
        self.degrade_expressive_fallback = bool(degrade_expressive_fallback)
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
            if self.fallback_voice_id or self.degrade_expressive_fallback:
                fallback_text = request.text
                fallback_audio_tags = request.audio_tags
                fallback_ssml = request.ssml_text
                fallback_mode = request.expressive_mode
                if self.degrade_expressive_fallback:
                    fallback_text = re.sub(r"(?m)^\s*\[[^\]\r\n]+\]\s*$", "", fallback_text)
                    fallback_text = "\n".join(
                        line for line in fallback_text.splitlines() if line.strip()
                    ).strip()
                    fallback_audio_tags = ()
                    fallback_ssml = None
                    fallback_mode = "best_effort"
                fallback_request = TtsProviderInput(
                    text=fallback_text,
                    language_code=request.language_code,
                    voice_config=VoiceConfig(
                        voice_id=self.fallback_voice_id,
                        language_code=request.voice_config.language_code,
                        speaking_rate=request.voice_config.speaking_rate,
                    ),
                    target_duration_seconds=request.target_duration_seconds,
                    voice_direction=request.voice_direction,
                    sample_context=request.sample_context,
                    audio_tags=fallback_audio_tags,
                    prosody_state=request.prosody_state,
                    performance_chunk_id=request.performance_chunk_id,
                    ssml_text=fallback_ssml,
                    expressive_mode=fallback_mode,
                    requested_features=request.requested_features,
                )
            output = self.fallback.synthesize(fallback_request)
            warnings = list(output.warnings or [])
            warnings.append("tts_used_fallback_provider")
            if self.degrade_expressive_fallback and request.requested_features:
                warnings.append("tts_expressive_fallback_degraded")
            meta = dict(output.provider_metadata or {})
            meta["fallback_used"] = True
            meta["primary_error"] = str(primary_exc)[:200]
            if self.degrade_expressive_fallback:
                meta["fallback_degraded_features"] = list(request.requested_features)
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
    omnivoice_provider_factory: Callable[[], TtsProvider] | None = None,
    allow_fallback: bool = True,
) -> TtsProvider:
    """
    Resolve TTS provider from workspace TTS AI settings (active Ops profile) or env.

    This is a transport factory. Preview may pass a draft or disabled setup.
    Durable production callers validate the one active On setup first and pass
    ``allow_fallback=False``. Env is used only when ``workspace_tts`` is omitted.

    Providers: auto | edge | vieneu | omnivoice | google | google_gemini | azure |
    elevenlabs | openai | openai_compatible | http_custom | cli | placeholder
    """
    from src.core.settings import get_settings

    settings = get_settings()
    if workspace_tts is not None:
        return _build_from_workspace_tts(
            workspace_tts,
            env_settings=settings,
            edge_provider_factory=edge_provider_factory,
            vieneu_provider_factory=vieneu_provider_factory,
            omnivoice_provider_factory=omnivoice_provider_factory,
            allow_fallback=allow_fallback,
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
        omnivoice_provider_factory=omnivoice_provider_factory,
        fallback_name=(
            (getattr(settings, "audio_tts_fallback_provider", None) or "none").strip().lower()
            if allow_fallback
            else "none"
        ),
        fallback_voice_id=(getattr(settings, "audio_tts_fallback_voice_id", None) or "").strip(),
    )


def _build_from_workspace_tts(
    workspace_tts: Any,
    *,
    env_settings: Any,
    edge_provider_factory: Callable[[], TtsProvider] | None,
    vieneu_provider_factory: Callable[[], TtsProvider] | None,
    omnivoice_provider_factory: Callable[[], TtsProvider] | None,
    allow_fallback: bool,
) -> TtsProvider:
    name = str(getattr(workspace_tts, "provider", "auto") or "auto").strip().lower()
    api_key = (getattr(workspace_tts, "api_key", None) or "").strip() or None
    base_url = str(getattr(workspace_tts, "base_url", "") or "").strip()
    options = dict(getattr(workspace_tts, "options_json", None) or {})
    if name == "google":
        from src.tts_pipeline.google_cloud_credentials import GOOGLE_CLOUD_TTS_BASE_URL

        base_url = GOOGLE_CLOUD_TTS_BASE_URL
        try:
            api_key, options = _resolve_google_runtime_auth(
                workspace_tts,
                api_key=api_key,
                options=options,
                timeout_seconds=float(getattr(workspace_tts, "timeout_seconds", 120.0) or 120.0),
            )
        except ValueError as exc:
            return ConfiguredButUnavailableTtsProvider(
                "google",
                f"Google Cloud credential is not ready ({str(exc)[:160]}).",
            )
    elif name == "google_gemini" and str(getattr(workspace_tts, "credential_mode", "") or "").strip().lower() in {
        "google_service_account",
        "google_adc",
    }:
        # Vertex AI uses the same Cloud OAuth scope as Google Cloud TTS, but
        # must charge the request to the service-account project/region rather
        # than the AI Studio API-key quota bucket.
        from src.tts_pipeline.google_cloud_credentials import (
            resolve_google_access_token,
        )
        from src.tts_pipeline.gemini_tts_provider import (
            VERTEX_GEMINI_DEFAULT_LOCATION,
            default_vertex_gemini_http_connector_options,
            vertex_gemini_base_url,
        )

        try:
            token = resolve_google_access_token(
                credential_mode=str(getattr(workspace_tts, "credential_mode", "") or ""),
                service_account_json=getattr(workspace_tts, "google_service_account_json", None),
                timeout_seconds=float(getattr(workspace_tts, "timeout_seconds", 120.0) or 120.0),
            )
            project_id = str(
                getattr(workspace_tts, "google_service_account_project_id", "") or ""
            ).strip()
            vertex_options = dict(options)
            vertex_options["vertex_ai"] = {
                "project_id": project_id,
                "location": str(
                    dict(vertex_options.get("vertex_ai") or {}).get(
                        "location", VERTEX_GEMINI_DEFAULT_LOCATION
                    )
                ),
            }
            options = default_vertex_gemini_http_connector_options(vertex_options)
            base_url = vertex_gemini_base_url(
                project_id=project_id,
                location=str(vertex_options["vertex_ai"]["location"]),
            )
            api_key = token
        except ValueError as exc:
            return ConfiguredButUnavailableTtsProvider(
                "google_gemini",
                f"Vertex Gemini credential is not ready ({str(exc)[:160]}).",
            )
    configured_fallback = (
        str(getattr(workspace_tts, "fallback_provider", "none") or "none").strip().lower()
        if allow_fallback
        else "none"
    )
    # A Vertex Gemini primary and Google Classic fallback need different
    # endpoint/auth manifests.  The generic fallback path intentionally
    # shares options for lightweight providers, so construct this pair with
    # their own OAuth-bound transports instead of accidentally sending a
    # Vertex manifest to the Cloud TTS endpoint.
    if name == "google_gemini" and configured_fallback == "google" and str(
        getattr(workspace_tts, "credential_mode", "") or ""
    ).strip().lower() in {"google_service_account", "google_adc"}:
        primary = _build_named_provider(
            name,
            env_settings=env_settings,
            voice_id=str(getattr(workspace_tts, "voice_id", "") or ""),
            speaking_rate=float(getattr(workspace_tts, "speaking_rate", 1.0) or 1.0),
            api_key=api_key,
            base_url=base_url,
            model_id=str(getattr(workspace_tts, "model_id", "") or "").strip(),
            local_backend=str(getattr(workspace_tts, "local_backend", "auto") or "auto").strip().lower(),
            device=str(getattr(workspace_tts, "device", "auto") or "auto").strip().lower(),
            cli_binary=str(getattr(workspace_tts, "cli_binary", "") or "").strip(),
            timeout_seconds=float(getattr(workspace_tts, "timeout_seconds", 120.0) or 120.0),
            options=options,
            edge_provider_factory=edge_provider_factory,
            vieneu_provider_factory=vieneu_provider_factory,
            omnivoice_provider_factory=omnivoice_provider_factory,
            fallback_name="none",
            fallback_voice_id="",
        )
        try:
            fallback_token, fallback_options = _resolve_google_runtime_auth(
                workspace_tts,
                api_key=None,
                options={},
                timeout_seconds=float(getattr(workspace_tts, "timeout_seconds", 120.0) or 120.0),
            )
            fallback_connector = dict(fallback_options.get("http_connector") or {})
            fallback_synthesis = dict(fallback_connector.get("synthesis") or {})
            fallback_body = dict(fallback_synthesis.get("body") or {})
            fallback_body["input"] = {"text": "{{text}}"}
            fallback_audio_config = dict(fallback_body.get("audioConfig") or {})
            fallback_audio_config["speakingRate"] = "{{speaking_rate}}"
            fallback_body["audioConfig"] = fallback_audio_config
            fallback_synthesis["body"] = fallback_body
            fallback_connector["synthesis"] = fallback_synthesis
            fallback_options["http_connector"] = fallback_connector
            fallback = _make_provider(
                "google",
                env_settings=env_settings,
                voice_id=str(getattr(workspace_tts, "fallback_voice_id", "") or ""),
                api_key=fallback_token,
                base_url="",
                model_id="",
                local_backend="auto",
                device="auto",
                cli_binary="",
                timeout_seconds=float(getattr(workspace_tts, "timeout_seconds", 120.0) or 120.0),
                options=fallback_options,
                edge_provider_factory=edge_provider_factory,
                vieneu_provider_factory=vieneu_provider_factory,
                omnivoice_provider_factory=omnivoice_provider_factory,
            )
        except ValueError as exc:
            return ConfiguredButUnavailableTtsProvider(
                "google_gemini",
                f"Vertex fallback credential is not ready ({str(exc)[:160]}).",
            )
        return FallbackTtsProvider(
            primary,
            fallback,
            fallback_voice_id=str(getattr(workspace_tts, "fallback_voice_id", "") or "").strip() or None,
            degrade_expressive_fallback=True,
        )

    return _build_named_provider(
        name,
        env_settings=env_settings,
        voice_id=str(getattr(workspace_tts, "voice_id", "") or ""),
        speaking_rate=float(getattr(workspace_tts, "speaking_rate", 1.0) or 1.0),
        api_key=api_key,
        base_url=base_url,
        model_id=str(getattr(workspace_tts, "model_id", "") or "").strip(),
        local_backend=str(getattr(workspace_tts, "local_backend", "auto") or "auto").strip().lower(),
        device=str(getattr(workspace_tts, "device", "auto") or "auto").strip().lower(),
        cli_binary=str(getattr(workspace_tts, "cli_binary", "") or "").strip(),
        timeout_seconds=float(getattr(workspace_tts, "timeout_seconds", 120.0) or 120.0),
        options=options,
        edge_provider_factory=edge_provider_factory,
        vieneu_provider_factory=vieneu_provider_factory,
        omnivoice_provider_factory=omnivoice_provider_factory,
        fallback_name=configured_fallback,
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
    omnivoice_provider_factory: Callable[[], TtsProvider] | None,
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
        omnivoice_provider_factory=omnivoice_provider_factory,
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
        omnivoice_provider_factory=omnivoice_provider_factory,
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
    omnivoice_provider_factory: Callable[[], TtsProvider] | None,
) -> TtsProvider:
    _ = (timeout_seconds, voice_id)

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

    if name in {"omnivoice", "omnivoice_studio", "omnivoice-studio"}:
        if omnivoice_provider_factory is not None:
            return omnivoice_provider_factory()
        return OmniVoiceTtsProvider(
            model_id=model_id,
            device=device,
            options=options,
        )

    if name == "cli":
        binary = cli_binary or "edge-tts"
        return ConfiguredButUnavailableTtsProvider(
            "cli",
            f"CLI TTS provider is configured (binary={binary}) but the adapter is not enabled yet. "
            "Use provider=edge or vieneu, or set fallback_provider=edge.",
        )

    if name == "google_gemini":
        try:
            from src.tts_pipeline.gemini_tts_provider import (
                GEMINI_DEFAULT_BASE_URL,
                GeminiTtsProvider,
            )

            return GeminiTtsProvider(
                base_url=base_url or GEMINI_DEFAULT_BASE_URL,
                api_key=api_key,
                model_id=model_id,
                options=options,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ConfiguredButUnavailableTtsProvider(
                "google_gemini",
                f"Invalid Gemini expressive connector configuration: {str(exc)[:300]}",
            )

    if name == "google_cloud_tts":
        if not str(api_key or "").strip():
            return ConfiguredButUnavailableTtsProvider(
                name,
                "google_cloud_tts requires an Agent Platform API key.",
            )
        from src.tts_pipeline.google_cloud_agent_tts_provider import (
            GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
            GoogleCloudAgentTtsProvider,
        )

        agent_options = dict(options or {})
        agent_config = dict(agent_options.get("google_cloud_tts") or {})
        try:
            return GoogleCloudAgentTtsProvider(
                api_key=str(api_key),
                model_id=model_id or GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
                region=str(agent_config.get("region") or "global"),
                options=agent_options,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ConfiguredButUnavailableTtsProvider(
                name,
                f"Invalid Google Cloud Agent TTS configuration: {str(exc)[:300]}",
            )

    if name in {
        "openai",
        "openai_compatible",
        "http_custom",
        "google",
        "google_gemini",
        "azure",
        "elevenlabs",
    } and isinstance(options.get("http_connector"), dict):
        try:
            from src.tts_pipeline.http_connector import GenericHttpTtsProvider

            return GenericHttpTtsProvider(
                provider_name=name,
                base_url=base_url or REMOTE_TTS_DEFAULT_BASE_URLS.get(name, ""),
                api_key=api_key,
                model_id=model_id,
                options=options,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            return ConfiguredButUnavailableTtsProvider(
                name,
                f"Invalid HTTP connector configuration: {str(exc)[:300]}",
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
            "Configure options_json.http_connector or set fallback_provider=edge.",
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


def probe_tts_ai_client(
    workspace_tts: Any,
    *,
    settings: Any | None = None,
    discover_remote: bool = False,
) -> TtsProbeResult:
    """Lightweight readiness check for Ops Test Connection (no long synthesis).

    Always probes the draft ``workspace_tts`` provider/fields when a config object is
    provided — ``enabled`` does not switch the probe to ENV (Enabled only gates jobs).
    When ``workspace_tts`` is None, falls back to ENV defaults.
    Local providers attach SDK/curated catalogs. Remote providers are queried only
    when ``discover_remote`` is explicitly enabled by the Ops Test endpoint.
    """
    from src.core.settings import get_settings

    cfg = workspace_tts
    env = settings or get_settings()
    if cfg is None:
        name = str(getattr(env, "audio_tts_provider", "auto") or "auto").strip().lower()
        language = str(getattr(env, "audio_tts_language_code", "vi") or "vi")
        api_key = getattr(env, "audio_tts_api_key", None)
        base_url = getattr(env, "audio_tts_base_url", "")
        result = _probe_named(
            name,
            api_key=api_key,
            base_url=base_url,
            cli_binary=getattr(env, "audio_tts_cli_binary", "") or "",
        )
        return _attach_catalog(
            result,
            language_code=language,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=float(getattr(env, "audio_tts_timeout_seconds", 120.0) or 120.0),
            discover_remote=discover_remote,
            options={},
        )

    name = str(getattr(cfg, "provider", "auto") or "auto").strip().lower()
    language = str(getattr(cfg, "language_code", "vi") or "vi")
    api_key = getattr(cfg, "api_key", None)
    base_url = getattr(cfg, "base_url", "")
    options = dict(getattr(cfg, "options_json", None) or {})
    if name == "google_cloud_tts":
        result = _probe_named(name, api_key=api_key, base_url="", cli_binary="")
        if result.ok and discover_remote:
            from src.tts_pipeline.google_cloud_agent_tts_provider import (
                GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
                GoogleCloudAgentTtsProvider,
            )
            from src.tts_pipeline.types import TtsProviderInput, VoiceConfig

            agent_config = dict(options.get("google_cloud_tts") or {})
            try:
                provider = GoogleCloudAgentTtsProvider(
                    api_key=str(api_key or ""),
                    model_id=str(getattr(cfg, "model_id", "") or GOOGLE_CLOUD_TTS_DEFAULT_MODEL),
                    region=str(agent_config.get("region") or "global"),
                    options=options,
                    timeout_seconds=float(getattr(cfg, "timeout_seconds", 120.0) or 120.0),
                )
                output = provider.synthesize(
                    TtsProviderInput(
                        text="Xin chào.",
                        language_code=language,
                        voice_config=VoiceConfig(
                            voice_id=str(getattr(cfg, "voice_id", "") or "Achernar"),
                            language_code=language,
                        ),
                    )
                )
                if not output.audio_bytes:
                    raise RuntimeError("google_cloud_tts_probe_empty_audio")
                result.detail = "Agent Platform TTS generated probe audio successfully."
                result.checks = [
                    {"stage": "audio_generation", "status": "passed", "detail": result.detail}
                ]
            except Exception as exc:  # noqa: BLE001 - return operator-safe SDK error
                result = TtsProbeResult(
                    False,
                    name,
                    str(exc)[:400],
                    checks=[
                        {
                            "stage": "audio_generation",
                            "status": "failed",
                            "detail": str(exc)[:300],
                        }
                    ],
                )
        return _attach_catalog(
            result,
            language_code=language,
            api_key=api_key,
            timeout_seconds=float(getattr(cfg, "timeout_seconds", 120.0) or 120.0),
            discover_remote=False,
            options=options,
        )
    if name == "google":
        from src.tts_pipeline.google_cloud_credentials import GOOGLE_CLOUD_TTS_BASE_URL

        base_url = GOOGLE_CLOUD_TTS_BASE_URL
        try:
            api_key, options = _resolve_google_runtime_auth(
                cfg,
                api_key=(api_key or "").strip() or None,
                options=options,
                timeout_seconds=float(getattr(cfg, "timeout_seconds", 120.0) or 120.0),
            )
        except ValueError as exc:
            return TtsProbeResult(
                False,
                "google",
                f"Google Cloud credential is not ready ({str(exc)[:160]}).",
                checks=[
                    {
                        "stage": "authentication",
                        "status": "failed",
                        "detail": f"Google OAuth setup failed ({str(exc)[:160]}).",
                    }
                ],
            )
    elif name == "google_gemini" and str(getattr(cfg, "credential_mode", "") or "").strip().lower() in {
        "google_service_account",
        "google_adc",
    }:
        from src.tts_pipeline.google_cloud_credentials import resolve_google_access_token
        from src.tts_pipeline.gemini_tts_provider import (
            VERTEX_GEMINI_DEFAULT_LOCATION,
            default_vertex_gemini_http_connector_options,
            vertex_gemini_base_url,
        )

        try:
            api_key = resolve_google_access_token(
                credential_mode=str(getattr(cfg, "credential_mode", "") or ""),
                service_account_json=getattr(cfg, "google_service_account_json", None),
                timeout_seconds=float(getattr(cfg, "timeout_seconds", 120.0) or 120.0),
            )
            vertex = dict(options.get("vertex_ai") or {})
            location = str(vertex.get("location") or VERTEX_GEMINI_DEFAULT_LOCATION)
            base_url = vertex_gemini_base_url(
                project_id=str(getattr(cfg, "google_service_account_project_id", "") or ""),
                location=location,
            )
            options = default_vertex_gemini_http_connector_options(options)
        except ValueError as exc:
            return TtsProbeResult(
                False,
                "google_gemini",
                f"Vertex Gemini credential is not ready ({str(exc)[:160]}).",
                checks=[
                    {
                        "stage": "authentication",
                        "status": "failed",
                        "detail": f"Vertex OAuth setup failed ({str(exc)[:160]}).",
                    }
                ],
            )
    result = _probe_named(
        name,
        api_key=api_key,
        base_url=base_url,
        cli_binary=getattr(cfg, "cli_binary", "") or "",
    )
    return _attach_catalog(
        result,
        language_code=language,
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=float(getattr(cfg, "timeout_seconds", 120.0) or 120.0),
        discover_remote=discover_remote,
        options=options,
    )


def _resolve_google_runtime_auth(
    workspace_tts: Any,
    *,
    api_key: str | None,
    options: dict[str, Any],
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    from src.tts_pipeline.google_cloud_credentials import (
        GOOGLE_CREDENTIAL_MODE_OAUTH_TOKEN,
        default_google_http_connector_options,
        normalize_google_credential_mode,
        resolve_google_access_token,
    )

    mode = normalize_google_credential_mode(
        getattr(workspace_tts, "credential_mode", ""),
        provider="google",
    )
    if mode == GOOGLE_CREDENTIAL_MODE_OAUTH_TOKEN:
        token = str(api_key or "").strip()
        if not token:
            raise ValueError("google_oauth_token_required")
    else:
        token = resolve_google_access_token(
            credential_mode=mode,
            service_account_json=getattr(workspace_tts, "google_service_account_json", None),
            timeout_seconds=timeout_seconds,
        )
    return token, default_google_http_connector_options(
        options,
        language_code=str(getattr(workspace_tts, "language_code", "") or ""),
    )


def _attach_catalog(
    result: TtsProbeResult,
    *,
    language_code: str,
    api_key: str | None = None,
    base_url: str = "",
    timeout_seconds: float = 120.0,
    discover_remote: bool = False,
    options: dict[str, Any] | None = None,
) -> TtsProbeResult:
    if not result.ok:
        return result

    # Remote discovery is intentionally opt-in for the explicit Ops Test request.
    # Worker/install probes keep the default so they never make surprise network calls.
    if discover_remote:
        discovery_kwargs: dict[str, Any] = {
            "base_url": (base_url or "").strip(),
            "api_key": (api_key or "").strip(),
            "language_code": language_code,
            "timeout_seconds": timeout_seconds,
        }
        connector = (options or {}).get("http_connector")
        if connector:
            discovery_kwargs["connector"] = connector
        remote_catalog = discover_remote_tts_catalog(result.provider, **discovery_kwargs)
        if remote_catalog is not None:
            result.catalog = remote_catalog.to_dict()
            discovery_error = (
                remote_catalog.discovery.error_code if remote_catalog.discovery is not None else ""
            )
            result.checks = (
                [dict(item) for item in remote_catalog.discovery.checks]
                if remote_catalog.discovery is not None
                else []
            )
            failed_connection_check = any(
                check.get("stage") in {"configuration", "authentication"}
                and check.get("status") == "failed"
                for check in result.checks
            )
            catalog_auth_rejected = any(
                str(check.get("stage") or "").startswith("catalog")
                and check.get("status") == "failed"
                and check.get("http_status") in {401, 403}
                for check in result.checks
            )
            if failed_connection_check or catalog_auth_rejected or discovery_error in {
                "authentication_failed",
                "connection_error",
                "cross_origin_endpoint",
                "cross_origin_redirect",
                "deadline_exceeded",
                "dns_failed",
                "insecure_credentials",
                "invalid_api_key",
                "invalid_connector_config",
                "invalid_base_url",
                "ssrf_blocked",
                "timeout",
            }:
                result.ok = False
                result.detail = remote_catalog.warning or "Remote TTS catalog connection was rejected."
            elif (options or {}).get("http_connector"):
                result.detail = "Universal HTTP connector check completed."
                if remote_catalog.warning:
                    result.detail = f"{result.detail} · {remote_catalog.warning}"
            elif remote_catalog.warning:
                result.detail = f"{result.detail} · {remote_catalog.warning}"
            if result.ok and result.provider == "google_gemini":
                # Gemini does not expose its prebuilt narrator list through the
                # generic catalog endpoints. Preserve transport/auth checks,
                # but never reuse Google Cloud Chirp ids as Gemini voice names.
                curated = discover_tts_catalog("google_gemini", language_code=language_code)
                curated.discovery = remote_catalog.discovery
                result.catalog = curated.to_dict()
            return result

    catalog_providers = {
        "edge",
        "vieneu",
        "auto",
        "omnivoice",
        "omnivoice_studio",
        "omnivoice-studio",
        "google_gemini",
        "google_cloud_tts",
    }
    if result.provider not in catalog_providers:
        return result
    # Curated catalog key is omnivoice for all OmniVoice Studio slugs
    catalog_key = "omnivoice" if result.provider.startswith("omnivoice") else result.provider
    catalog = discover_tts_catalog(catalog_key, language_code=language_code)
    result.catalog = catalog.to_dict()
    if catalog.warning and catalog.source == "curated":
        result.detail = f"{result.detail} · {catalog.warning}"
    return result


def _probe_named(
    name: str,
    *,
    api_key: str | None,
    base_url: str,
    cli_binary: str = "",
) -> TtsProbeResult:
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

    if name in {"omnivoice", "omnivoice_studio", "omnivoice-studio"}:
        if not _module_importable("omnivoice"):
            return TtsProbeResult(
                False,
                "omnivoice",
                "omnivoice not installed. Install OmniVoice-Studio / omnivoice via Ops.",
            )
        return TtsProbeResult(True, "omnivoice", "omnivoice import ready (k2-fsa synthesize adapter)")

    if name == "cli":
        if not (cli_binary or "").strip():
            return TtsProbeResult(False, "cli", "cli requires cli_binary")
        return TtsProbeResult(True, "cli", "CLI provider settings accepted (runtime adapter pending).")

    if name in {"openai_compatible", "http_custom"}:
        if not (base_url or "").strip():
            return TtsProbeResult(False, name, f"{name} requires base_url")
        return TtsProbeResult(
            True, name, f"{name} settings look valid (HTTP adapter pending for synthesis)."
        )

    if name == "google_cloud_tts":
        if not (api_key or "").strip():
            return TtsProbeResult(False, name, "google_cloud_tts requires an Agent Platform API key")
        try:
            from google import genai  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            return TtsProbeResult(False, name, "google-genai is not installed")
        return TtsProbeResult(True, name, "Agent Platform TTS SDK and API key are configured.")

    if name in {"google", "google_gemini", "azure", "elevenlabs", "openai"}:
        if not (api_key or "").strip():
            return TtsProbeResult(False, name, f"{name} requires api_key")
        return TtsProbeResult(
            True, name, f"{name} settings accepted (cloud adapter pending for synthesis)."
        )

    if name != "auto":
        return TtsProbeResult(
            False,
            name,
            f"Unknown local provider '{name}' — Install a known slug (edge/vieneu/omnivoice/cli) "
            "or use a Cloud/HTTP provider from the catalog.",
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
