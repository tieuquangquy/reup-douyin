"""Provider capability negotiation for the provider-neutral TTS Director."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ProviderCapabilities:
    schema_version: str = "tts-provider-capabilities-v1"
    provider: str = ""
    model_id: str = ""
    supports_voice_direction: bool = False
    supports_sample_context: bool = False
    supports_audio_tags: bool = False
    supports_ssml: bool = False
    supports_style: bool = False
    supports_pitch: bool = False
    supports_speaking_rate: bool = True
    supports_non_verbal_tags: bool = False
    supports_multi_speaker: bool = False
    adapter_version: str = "tts-provider-adapter-v1"

    @property
    def expressive(self) -> bool:
        return bool(
            self.supports_voice_direction
            or self.supports_audio_tags
            or self.supports_ssml
            or self.supports_style
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_provider_capabilities(
    provider: str,
    *,
    model_id: str = "",
    options: Mapping[str, Any] | None = None,
) -> ProviderCapabilities:
    """Resolve capabilities without making network/provider calls.

    Custom HTTP profiles may declare a conservative capability subset under
    ``options_json.http_connector.capabilities``. Unknown fields are ignored.
    """

    normalized = str(provider or "").strip().lower().replace("-", "_")
    model = str(model_id or "").strip()
    model_lower = model.lower()
    if normalized in {"gemini", "google_gemini", "google_cloud_tts"} or (
        normalized == "google" and "gemini" in model_lower
    ):
        base = ProviderCapabilities(
            provider=normalized,
            model_id=model,
            supports_voice_direction=True,
            supports_sample_context=True,
            supports_audio_tags=True,
            supports_style=True,
            supports_pitch=True,
            supports_non_verbal_tags=True,
            supports_multi_speaker=True,
            adapter_version="gemini-tts-adapter-v1",
        )
    elif normalized in {"edge", "edge_tts"}:
        base = ProviderCapabilities(
            provider=normalized,
            model_id=model,
            supports_speaking_rate=True,
            adapter_version="edge-tts-adapter-v1",
        )
    elif normalized in {"omnivoice", "omnivoice_studio", "vieneu"}:
        base = ProviderCapabilities(
            provider=normalized,
            model_id=model,
            supports_speaking_rate=True,
            adapter_version=f"{normalized}-adapter-v1",
        )
    elif normalized in {"azure", "google", "google_cloud", "google_classic"}:
        base = ProviderCapabilities(
            provider=normalized,
            model_id=model,
            supports_ssml=True,
            supports_pitch=True,
            supports_speaking_rate=True,
            adapter_version="classic-ssml-adapter-v1",
        )
    elif normalized in {"elevenlabs", "eleven_labs"}:
        base = ProviderCapabilities(
            provider=normalized,
            model_id=model,
            supports_audio_tags=True,
            supports_non_verbal_tags=True,
            supports_speaking_rate=True,
            adapter_version="elevenlabs-audio-tags-adapter-v1",
        )
    else:
        base = ProviderCapabilities(
            provider=normalized,
            model_id=model,
            adapter_version="basic-provider-adapter-v1",
        )

    raw_options = dict(options or {})
    connector = raw_options.get("http_connector")
    declared = connector.get("capabilities") if isinstance(connector, Mapping) else None
    if not isinstance(declared, Mapping):
        declared = raw_options.get("capabilities")
    if not isinstance(declared, Mapping):
        return base
    values = base.to_dict()
    for field_name in (
        "supports_voice_direction",
        "supports_sample_context",
        "supports_audio_tags",
        "supports_ssml",
        "supports_style",
        "supports_pitch",
        "supports_speaking_rate",
        "supports_non_verbal_tags",
        "supports_multi_speaker",
    ):
        if field_name in declared:
            values[field_name] = bool(declared[field_name])
    if declared.get("adapter_version"):
        values["adapter_version"] = str(declared["adapter_version"])
    return ProviderCapabilities(**values)
