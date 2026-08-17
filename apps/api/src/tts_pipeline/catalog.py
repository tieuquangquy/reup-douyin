"""TTS provider catalog discovery for Ops Test Connection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TtsVoiceOption:
    id: str
    label: str
    # Optional metadata returned by remote providers.  Local/curated catalogs
    # leave these empty so the legacy {id, label} contract stays intact.
    languages: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    gender: str | None = None
    description: str | None = None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class TtsModelOption:
    id: str
    label: str = ""
    languages: list[str] = field(default_factory=list)
    voices: list[str] = field(default_factory=list)
    description: str | None = None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class TtsLanguageOption:
    code: str
    label: str = ""


@dataclass
class TtsCatalogDiscovery:
    status: str = "unavailable"  # complete | partial | unavailable
    endpoints: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Safe, additive stage results for Ops Test Connection. Entries never
    # contain credentials or response bodies.
    checks: list[dict[str, Any]] = field(default_factory=list)
    # Stable hash of the public connector manifest/base URL (never API key).
    config_fingerprint: str = ""
    # Internal signal for probe policy. Deliberately omitted from to_dict/API.
    error_code: str = ""


@dataclass
class TtsFieldCapabilities:
    voice: bool = False
    model: bool = False
    styles: bool = False
    api_key: bool = False
    base_url: bool = False
    local_backend: bool = False
    cli_binary: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "voice": self.voice,
            "model": self.model,
            "styles": self.styles,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "local_backend": self.local_backend,
            "cli_binary": self.cli_binary,
        }


@dataclass
class TtsProviderCatalog:
    source: str = "none"  # sdk | curated | none
    voices: list[TtsVoiceOption] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    model_options: list[TtsModelOption] = field(default_factory=list)
    languages: list[TtsLanguageOption] = field(default_factory=list)
    default_voice_id: str = ""
    default_model_id: str = ""
    default_language_code: str = ""
    warning: str = ""
    sample_rate: int | None = None
    backends: list[str] = field(default_factory=list)
    capabilities: TtsFieldCapabilities | None = None
    discovery: TtsCatalogDiscovery | None = None

    def to_dict(self) -> dict[str, Any]:
        caps = self.capabilities or capabilities_for_provider("custom")
        return {
            "source": self.source,
            "voices": [
                {
                    "id": v.id,
                    "label": v.label,
                    **({"languages": list(v.languages)} if v.languages else {}),
                    **({"models": list(v.models)} if v.models else {}),
                    **({"gender": v.gender} if v.gender else {}),
                    **({"description": v.description} if v.description else {}),
                    **({"capabilities": list(v.capabilities)} if v.capabilities else {}),
                }
                for v in self.voices
            ],
            "styles": list(self.styles),
            "models": list(self.models),
            "model_options": [
                {
                    "id": option.id,
                    "label": option.label or option.id,
                    **({"languages": list(option.languages)} if option.languages else {}),
                    **({"voices": list(option.voices)} if option.voices else {}),
                    **({"description": option.description} if option.description else {}),
                    **({"capabilities": list(option.capabilities)} if option.capabilities else {}),
                }
                for option in (
                    self.model_options
                    or [TtsModelOption(id=model, label=model) for model in self.models]
                )
            ],
            "languages": [
                {"code": language.code, "label": language.label or language.code}
                for language in self.languages
            ],
            "default_voice_id": self.default_voice_id,
            "default_model_id": self.default_model_id or (self.models[0] if self.models else ""),
            "default_language_code": self.default_language_code,
            "warning": self.warning,
            "sample_rate": self.sample_rate,
            "backends": list(self.backends),
            "capabilities": caps.to_dict(),
            **(
                {
                    "discovery": {
                        "status": self.discovery.status,
                        "endpoints": list(self.discovery.endpoints),
                        "warnings": list(self.discovery.warnings),
                        **(
                            {"checks": [dict(item) for item in self.discovery.checks]}
                            if self.discovery.checks
                            else {}
                        ),
                        **(
                            {"config_fingerprint": self.discovery.config_fingerprint}
                            if self.discovery.config_fingerprint
                            else {}
                        ),
                    }
                }
                if self.discovery is not None
                else {}
            ),
        }


VIENEU_STYLES = ("tu_nhien", "tin_tuc", "doc_truyen")
VIENEU_MODELS = ("v3turbo",)
VIENEU_BACKENDS = ("auto", "onnx", "pytorch", "remote")
VIENEU_SAMPLE_RATE = 48000
VIENEU_CURATED_VOICES = (
    ("Phạm Tuyên", "Phạm Tuyên"),
    ("Xuân Vĩnh", "Xuân Vĩnh"),
    ("Trúc Ly", "Trúc Ly"),
    ("Ngọc Lan", "Ngọc Lan"),
    ("Ngọc Linh", "Ngọc Linh"),
    ("Bình An", "Bình An"),
)

EDGE_FALLBACK_VOICES = (
    ("vi-VN-HoaiMyNeural", "vi-VN-HoaiMyNeural (Female)"),
    ("vi-VN-NamMinhNeural", "vi-VN-NamMinhNeural (Male)"),
)

# Gemini TTS exposes a fixed set of prebuilt narrator identities.  These ids
# are intentionally provider-native (``Kore``), not Google Cloud TTS voice
# resource ids (``vi-VN-Chirp3-HD-Kore``).
GEMINI_TTS_VOICES = (
    ("Zephyr", "Zephyr · bright"),
    ("Puck", "Puck · upbeat"),
    ("Charon", "Charon · informative"),
    ("Kore", "Kore · firm"),
    ("Fenrir", "Fenrir · excitable"),
    ("Leda", "Leda · youthful"),
    ("Orus", "Orus · firm"),
    ("Aoede", "Aoede · breezy"),
    ("Callirrhoe", "Callirrhoe · easy-going"),
    ("Autonoe", "Autonoe · bright"),
    ("Enceladus", "Enceladus · breathy"),
    ("Iapetus", "Iapetus · clear"),
    ("Umbriel", "Umbriel · easy-going"),
    ("Algieba", "Algieba · smooth"),
    ("Despina", "Despina · smooth"),
    ("Erinome", "Erinome · clear"),
    ("Algenib", "Algenib · gravelly"),
    ("Rasalgethi", "Rasalgethi · informative"),
    ("Laomedeia", "Laomedeia · upbeat"),
    ("Achernar", "Achernar · soft"),
    ("Alnilam", "Alnilam · firm"),
    ("Schedar", "Schedar · even"),
    ("Gacrux", "Gacrux · mature"),
    ("Pulcherrima", "Pulcherrima · forward"),
    ("Achird", "Achird · friendly"),
    ("Zubenelgenubi", "Zubenelgenubi · casual"),
    ("Vindemiatrix", "Vindemiatrix · gentle"),
    ("Sadachbia", "Sadachbia · lively"),
    ("Sadaltager", "Sadaltager · knowledgeable"),
    ("Sulafat", "Sulafat · warm"),
)

GEMINI_TTS_MODELS = (
    "gemini-2.5-flash-tts",
    "gemini-2.5-pro-tts",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
)

GOOGLE_CLOUD_AGENT_TTS_MODELS = (
    "gemini-2.5-flash-tts",
    "gemini-3.1-flash-preview-tts",
    "gemini-2.5-pro-tts",
    "gemini-2.5-flash-lite-preview-tts",
)


def normalize_gemini_voice_id(value: Any) -> str:
    """Return a canonical Gemini voice id, including legacy Cloud ids."""

    text = str(value or "").strip()
    if not text:
        return ""
    by_lower = {voice_id.lower(): voice_id for voice_id, _label in GEMINI_TTS_VOICES}
    direct = by_lower.get(text.lower())
    if direct:
        return direct
    marker = "-chirp3-hd-"
    lowered = text.lower()
    if marker in lowered:
        suffix = text[lowered.rfind(marker) + len(marker) :].strip()
        return by_lower.get(suffix.lower(), "")
    return ""

# Curated OmniVoice-Studio TTS engine ids (Settings → TTS Engine / OMNIVOICE_TTS_BACKEND).
# Not scraped from GitHub — kept in sync with the public engine matrix.
OMNIVOICE_MODELS = (
    "omnivoice",
    "k2-fsa/OmniVoice",  # HF alias for default OmniVoice weights
    "cosyvoice",
    "gpt-sovits",
    "voxcpm2",
    "moss-tts-nano",
    "kittentts",
    "sherpa-onnx",
    "mlx-audio",
    "indextts2",
    "omnivoice-gguf",
    "supertonic3",
    "moss-tts-v15",
    "dots-tts",
    "confucius4-tts",
)

# Voice ids: auto + OpenAI-compat names Studio accepts + instruct presets for VI/EN.
OMNIVOICE_VOICES = (
    ("auto", "Auto (model picks voice)"),
    ("alloy", "alloy (OpenAI-compat)"),
    ("echo", "echo (OpenAI-compat)"),
    ("fable", "fable (OpenAI-compat)"),
    ("onyx", "onyx (OpenAI-compat)"),
    ("nova", "nova (OpenAI-compat)"),
    ("shimmer", "shimmer (OpenAI-compat)"),
    ("instruct:vi_female_north", "VI · nữ miền Bắc (instruct)"),
    ("instruct:vi_female_south", "VI · nữ miền Nam (instruct)"),
    ("instruct:vi_male_north", "VI · nam miền Bắc (instruct)"),
    ("instruct:vi_male_south", "VI · nam miền Nam (instruct)"),
    ("instruct:vi_news", "VI · đọc tin (instruct)"),
    ("instruct:vi_warm", "VI · ấm / kể chuyện (instruct)"),
    ("instruct:en_female", "EN · female (instruct)"),
    ("instruct:en_male", "EN · male (instruct)"),
    ("instruct:en_british", "EN · British (instruct)"),
)


def capabilities_for_provider(provider: str, *, local_backend: str = "auto") -> TtsFieldCapabilities:
    name = (provider or "").strip().lower()
    if name == "edge":
        return TtsFieldCapabilities(voice=True)
    if name == "vieneu":
        return TtsFieldCapabilities(
            voice=True,
            model=True,
            styles=True,
            local_backend=True,
            base_url=(local_backend or "auto").strip().lower() == "remote",
        )
    if name == "cli":
        return TtsFieldCapabilities(voice=True, cli_binary=True)
    if name in {"google", "google_gemini", "google_cloud_tts", "elevenlabs"}:
        return TtsFieldCapabilities(voice=True, model=True, api_key=True)
    if name in {"azure", "openai"}:
        return TtsFieldCapabilities(voice=True, model=True, api_key=True, base_url=True)
    if name in {"openai_compatible", "http_custom"}:
        return TtsFieldCapabilities(voice=True, model=True, api_key=True, base_url=True)
    if name in {"auto", "placeholder"}:
        return TtsFieldCapabilities(voice=True)
    # Custom / OmniVoice / unknown local
    return TtsFieldCapabilities(voice=True, model=True)


def empty_catalog(*, warning: str = "", provider: str = "custom") -> TtsProviderCatalog:
    return TtsProviderCatalog(
        source="none",
        warning=warning,
        capabilities=capabilities_for_provider(provider),
    )


def discover_tts_catalog(
    provider: str,
    *,
    language_code: str = "vi",
    vieneu_list_voices: Callable[[], list[tuple[str, str]]] | None = None,
    edge_list_voices: Callable[[], list[dict[str, Any]]] | None = None,
) -> TtsProviderCatalog:
    """Return provider catalog. Prefer SDK lists; fall back to curated presets."""
    name = (provider or "").strip().lower()
    if name == "vieneu":
        return _discover_vieneu(vieneu_list_voices=vieneu_list_voices)
    if name == "edge":
        return _discover_edge(
            language_code=language_code or "vi",
            edge_list_voices=edge_list_voices,
        )
    if name == "auto":
        # Prefer vieneu catalog when available, else edge.
        vieneu = _discover_vieneu(vieneu_list_voices=vieneu_list_voices, allow_missing=True)
        if vieneu.voices:
            return vieneu
        return _discover_edge(
            language_code=language_code or "vi",
            edge_list_voices=edge_list_voices,
            allow_missing=True,
        )
    if name in {"omnivoice", "omnivoice_studio", "omnivoice-studio"}:
        return _discover_omnivoice()
    if name == "google_gemini":
        return _discover_google_gemini()
    if name == "google_cloud_tts":
        return _discover_google_cloud_agent_tts()
    if name in {
        "google",
        "azure",
        "elevenlabs",
        "openai",
        "openai_compatible",
        "http_custom",
        "cli",
        "placeholder",
    }:
        return empty_catalog(provider=name)
    # Generic local/custom: adaptive form capabilities without inventing Edge voices.
    return TtsProviderCatalog(
        source="curated" if name else "none",
        voices=[],
        models=[],
        default_voice_id="",
        warning="",
        capabilities=capabilities_for_provider(name or "custom"),
    )


def _discover_omnivoice() -> TtsProviderCatalog:
    voices = [TtsVoiceOption(id=vid, label=label) for vid, label in OMNIVOICE_VOICES]
    return TtsProviderCatalog(
        source="curated",
        voices=voices,
        models=list(OMNIVOICE_MODELS),
        default_voice_id="auto",
        warning=(
            "Curated OmniVoice-Studio engine + voice presets. "
            "Some engines need extra install/GPU; Preview needs a wired adapter."
        ),
        sample_rate=None,
        backends=list(OMNIVOICE_MODELS),
        capabilities=capabilities_for_provider("omnivoice"),
    )


def _discover_google_gemini() -> TtsProviderCatalog:
    voices = [
        TtsVoiceOption(
            id=voice_id,
            label=label,
            languages=["vi-VN"],
            models=list(GEMINI_TTS_MODELS),
            capabilities=["expressive", "single_speaker"],
        )
        for voice_id, label in GEMINI_TTS_VOICES
    ]
    models = [
        TtsModelOption(
            id=model_id,
            label=model_id,
            languages=["vi-VN"],
            voices=[voice.id for voice in voices],
            capabilities=["audio", "expressive_tts"],
        )
        for model_id in GEMINI_TTS_MODELS
    ]
    return TtsProviderCatalog(
        source="curated",
        voices=voices,
        models=list(GEMINI_TTS_MODELS),
        model_options=models,
        languages=[TtsLanguageOption(code="vi-VN", label="Tiếng Việt (Việt Nam)")],
        default_voice_id="Kore",
        default_model_id=GEMINI_TTS_MODELS[0],
        default_language_code="vi-VN",
        warning="Gemini voice choices are provider-native curated presets.",
        capabilities=capabilities_for_provider("google_gemini"),
    )


def _discover_google_cloud_agent_tts() -> TtsProviderCatalog:
    voices = [
        TtsVoiceOption(
            id=voice_id,
            label=label,
            languages=["vi-VN"],
            models=list(GOOGLE_CLOUD_AGENT_TTS_MODELS),
            capabilities=["expressive", "single_speaker", "agent_platform"],
        )
        for voice_id, label in GEMINI_TTS_VOICES
    ]
    voice_ids = [voice.id for voice in voices]
    model_options = [
        TtsModelOption(
            id=model_id,
            label=model_id,
            languages=["vi-VN"],
            voices=voice_ids,
            capabilities=["audio", "expressive_tts", "agent_platform"],
        )
        for model_id in GOOGLE_CLOUD_AGENT_TTS_MODELS
    ]
    return TtsProviderCatalog(
        source="curated",
        voices=voices,
        models=list(GOOGLE_CLOUD_AGENT_TTS_MODELS),
        model_options=model_options,
        languages=[TtsLanguageOption(code="vi-VN", label="Tiếng Việt (Việt Nam)")],
        default_voice_id="Achernar",
        default_model_id=GOOGLE_CLOUD_AGENT_TTS_MODELS[0],
        default_language_code="vi-VN",
        warning=(
            "Agent Platform API-key mode uses a curated catalog because Vertex models.list "
            "requires OAuth2. Refresh is offline; Test Connection performs a real audio "
            "generation request."
        ),
        capabilities=capabilities_for_provider("google_cloud_tts"),
    )


def _discover_vieneu(
    *,
    vieneu_list_voices: Callable[[], list[tuple[str, str]]] | None,
    allow_missing: bool = False,
) -> TtsProviderCatalog:
    voices: list[TtsVoiceOption] = []
    source = "curated"
    warning = ""
    try:
        lister = vieneu_list_voices or _default_vieneu_list_voices
        raw = lister()
        for item in raw:
            if not item:
                continue
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                label, voice_id = str(item[0]).strip(), str(item[1]).strip()
            else:
                continue
            if not voice_id:
                continue
            voices.append(TtsVoiceOption(id=voice_id, label=label or voice_id))
        if voices:
            source = "sdk"
    except Exception as exc:  # noqa: BLE001 — catalog must not fail Test
        warning = f"VieNeu voice list unavailable: {exc}"
        if allow_missing and not voices:
            return empty_catalog(warning=warning, provider="vieneu")

    if not voices:
        voices = [TtsVoiceOption(id=vid, label=label) for label, vid in VIENEU_CURATED_VOICES]
        source = "curated"
        if not warning:
            warning = "Using curated VieNeu voices (SDK list empty or unavailable)"

    return TtsProviderCatalog(
        source=source,
        voices=voices,
        styles=list(VIENEU_STYLES),
        models=list(VIENEU_MODELS),
        default_voice_id=voices[0].id if voices else "Phạm Tuyên",
        warning=warning,
        sample_rate=VIENEU_SAMPLE_RATE,
        backends=list(VIENEU_BACKENDS),
        capabilities=capabilities_for_provider("vieneu"),
    )


def _discover_edge(
    *,
    language_code: str,
    edge_list_voices: Callable[[], list[dict[str, Any]]] | None,
    allow_missing: bool = False,
) -> TtsProviderCatalog:
    voices: list[TtsVoiceOption] = []
    source = "curated"
    warning = ""
    lang = (language_code or "vi").strip().lower()
    prefix = "vi-VN" if lang.startswith("vi") else lang
    try:
        lister = edge_list_voices or _default_edge_list_voices
        raw = lister()
        for row in raw:
            short = str(row.get("ShortName") or row.get("short_name") or "").strip()
            locale = str(row.get("Locale") or row.get("locale") or "").strip()
            if not short:
                continue
            if prefix and not (short.startswith(prefix) or locale.lower().startswith(lang)):
                continue
            friendly = str(row.get("FriendlyName") or row.get("Name") or short).strip()
            voices.append(TtsVoiceOption(id=short, label=friendly or short))
        if voices:
            source = "sdk"
    except Exception as exc:  # noqa: BLE001
        warning = f"edge-tts voice list unavailable: {exc}"
        if allow_missing and not voices:
            return empty_catalog(warning=warning, provider="edge")

    if not voices:
        voices = [TtsVoiceOption(id=vid, label=label) for vid, label in EDGE_FALLBACK_VOICES]
        source = "curated"
        if not warning:
            warning = "Using curated edge Vietnamese voices"

    preferred = "vi-VN-HoaiMyNeural"
    default_id = preferred if any(v.id == preferred for v in voices) else voices[0].id
    return TtsProviderCatalog(
        source=source,
        voices=voices,
        styles=[],
        models=[],
        default_voice_id=default_id,
        warning=warning,
        sample_rate=24000,
        backends=[],
        capabilities=capabilities_for_provider("edge"),
    )


def _default_vieneu_list_voices() -> list[tuple[str, str]]:
    from vieneu import Vieneu  # type: ignore

    client = Vieneu()
    raw = client.list_preset_voices()
    if callable(raw):
        raw = raw()
    return list(raw or [])


def _default_edge_list_voices() -> list[dict[str, Any]]:
    import asyncio

    import edge_tts  # type: ignore

    async def _run() -> list[dict[str, Any]]:
        return list(await edge_tts.list_voices())

    try:
        return asyncio.run(_run())
    except RuntimeError:
        # Already in an event loop — use a new loop in a thread if needed.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
