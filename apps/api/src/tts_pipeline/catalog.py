"""TTS provider catalog discovery for Ops Test Connection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TtsVoiceOption:
    id: str
    label: str


@dataclass
class TtsProviderCatalog:
    source: str = "none"  # sdk | curated | none
    voices: list[TtsVoiceOption] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    default_voice_id: str = ""
    warning: str = ""
    sample_rate: int | None = None
    backends: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "voices": [{"id": v.id, "label": v.label} for v in self.voices],
            "styles": list(self.styles),
            "models": list(self.models),
            "default_voice_id": self.default_voice_id,
            "warning": self.warning,
            "sample_rate": self.sample_rate,
            "backends": list(self.backends),
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


def empty_catalog(*, warning: str = "") -> TtsProviderCatalog:
    return TtsProviderCatalog(source="none", warning=warning)


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
    return empty_catalog()


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
            return empty_catalog(warning=warning)

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
            return empty_catalog(warning=warning)

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
