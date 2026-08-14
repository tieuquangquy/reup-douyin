"""Lower provider-neutral prosody into safe provider-specific instructions."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from src.tts_pipeline.provider_capabilities import ProviderCapabilities
from src.tts_pipeline.types import ProsodySegment, VoiceBible


PROVIDER_LOWERING_VERSION = "tts-provider-lowering-v2"


@dataclass(frozen=True)
class CompiledTtsInstruction:
    speech_text: str
    rendered_text: str
    voice_direction: str | None
    sample_context: str | None
    audio_tags: tuple[str, ...]
    ssml_text: str | None
    prosody_state: dict
    applied_features: tuple[str, ...]
    degraded_features: tuple[str, ...]
    compiler_version: str = PROVIDER_LOWERING_VERSION

    def to_metadata(self) -> dict:
        return {
            "compiler_version": self.compiler_version,
            "audio_tags": list(self.audio_tags),
            "voice_direction_applied": bool(self.voice_direction),
            "sample_context_applied": bool(self.sample_context),
            "ssml_applied": bool(self.ssml_text),
            "prosody_state": dict(self.prosody_state),
            "applied_features": list(self.applied_features),
            "degraded_features": list(self.degraded_features),
        }


def compile_provider_instruction(
    speech_text: str,
    *,
    voice_bible: VoiceBible,
    prosody: ProsodySegment,
    capabilities: ProviderCapabilities,
    sample_context: str | None = None,
    base_speaking_rate: float = 1.0,
) -> CompiledTtsInstruction:
    raw_text = " ".join(str(speech_text or "").split())
    supported_tags = tuple(prosody.audio_tags) if capabilities.supports_audio_tags else ()
    rendered = raw_text
    if supported_tags:
        if prosody.spans:
            rendered = "\n".join(
                f"[{', '.join(span.audio_tags)}]\n{span.text}"
                if span.audio_tags
                else span.text
                for span in prosody.spans
            )
        else:
            rendered = f"[{', '.join(supported_tags)}]\n{raw_text}"
    direction = (
        _voice_direction(
            voice_bible,
            prosody,
            base_speaking_rate=base_speaking_rate,
        )
        if capabilities.supports_voice_direction
        else None
    )
    context = (
        str(sample_context or "").strip() or None
        if capabilities.supports_sample_context
        else None
    )
    ssml = (
        _ssml(raw_text, prosody, base_speaking_rate=base_speaking_rate)
        if capabilities.supports_ssml
        else None
    )
    applied: list[str] = []
    if supported_tags:
        applied.append("audio_tags")
    if direction:
        applied.append("voice_direction")
    if context:
        applied.append("sample_context")
    if ssml:
        applied.extend(("ssml", "emotion_pitch_volume", "prosody_pause"))
    if capabilities.supports_speaking_rate:
        applied.append("speaking_rate")
    degraded: list[str] = []
    if prosody.audio_tags and not (
        capabilities.supports_audio_tags or capabilities.supports_ssml
    ):
        degraded.append("audio_tags_not_supported")
    if prosody.emphasis and not (
        capabilities.supports_audio_tags or capabilities.supports_ssml
    ):
        degraded.append("explicit_emphasis_not_supported")
    if prosody.emotion != "neutral" and not (
        capabilities.supports_audio_tags or capabilities.supports_ssml
    ):
        degraded.append("emotion_not_supported")
    if prosody.pause_after_ms and not (
        capabilities.supports_audio_tags or capabilities.supports_ssml
    ):
        degraded.append("provider_pause_control_not_supported")
    if sample_context and not capabilities.supports_sample_context:
        degraded.append("sample_context_not_supported")
    return CompiledTtsInstruction(
        speech_text=raw_text,
        rendered_text=rendered,
        voice_direction=direction,
        sample_context=context,
        audio_tags=supported_tags,
        ssml_text=ssml,
        prosody_state=prosody.previous_state.to_dict(),
        applied_features=tuple(dict.fromkeys(applied)),
        degraded_features=tuple(dict.fromkeys(degraded)),
    )


def _voice_direction(
    voice_bible: VoiceBible,
    prosody: ProsodySegment,
    *,
    base_speaking_rate: float = 1.0,
) -> str:
    rules = "; ".join(voice_bible.director_rules)
    emphasis = ", ".join(prosody.emphasis) or "none"
    previous = prosody.previous_state
    effective_pace = max(0.5, min(2.0, float(base_speaking_rate) * float(prosody.pace)))
    return (
        f"Audio profile: {voice_bible.persona}; accent: {voice_bible.accent}; "
        f"style: {voice_bible.speaking_style}. "
        f"Director notes: target delivery speed {effective_pace:.2f}x; "
        f"prosody pace {prosody.pace:.2f}; emotion {prosody.emotion}; "
        f"intensity {prosody.intensity:.2f}; breathing {prosody.breath}; "
        f"emphasize: {emphasis}; pauses: before {int(prosody.pause_before_ms)}ms, "
        f"after {int(prosody.pause_after_ms)}ms. "
        f"Previous delivery: {previous.current_emotion}, energy {previous.energy:.2f}, "
        f"pace {previous.pace:.2f}, intent {previous.previous_intent}. "
        f"Continue naturally from that state. Rules: {rules}"
    )


def _ssml(
    text: str,
    prosody: ProsodySegment,
    *,
    base_speaking_rate: float = 1.0,
) -> str:
    combined_rate = max(
        0.5,
        min(2.0, float(base_speaking_rate) * float(prosody.pace)),
    )
    rate_percent = int(round((combined_rate - 1.0) * 100.0))
    rate = f"{rate_percent:+d}%"
    body = escape(text)
    for phrase in sorted(prosody.emphasis, key=len, reverse=True):
        escaped = escape(phrase)
        body = body.replace(escaped, f'<emphasis level="moderate">{escaped}</emphasis>')
    before = (
        f'<break time="{int(prosody.pause_before_ms)}ms"/>'
        if prosody.pause_before_ms > 0
        else ""
    )
    after = (
        f'<break time="{int(prosody.pause_after_ms)}ms"/>'
        if prosody.pause_after_ms > 0
        else ""
    )
    pitch, volume = _emotion_controls(prosody.emotion, prosody.intensity)
    controls = f' rate="{rate}" pitch="{pitch}" volume="{volume}"'
    if prosody.spans:
        span_parts: list[str] = []
        for span_index, span in enumerate(prosody.spans):
            span_body = escape(span.text)
            for phrase in sorted(span.emphasis, key=len, reverse=True):
                escaped = escape(phrase)
                span_body = span_body.replace(
                    escaped,
                    f'<emphasis level="moderate">{escaped}</emphasis>',
                )
            span_rate = max(
                0.5,
                min(2.0, float(base_speaking_rate) * float(span.pace)),
            )
            span_rate_text = f"{int(round((span_rate - 1.0) * 100.0)):+d}%"
            span_pitch, span_volume = _emotion_controls(span.emotion, span.intensity)
            span_parts.append(
                f'<prosody rate="{span_rate_text}" pitch="{span_pitch}" volume="{span_volume}">'
                f"{span_body}</prosody>"
            )
            pause_after = (
                span.pause_after_ms
                if span_index < len(prosody.spans) - 1
                else prosody.pause_after_ms
            )
            if pause_after > 0:
                span_parts.append(f'<break time="{int(pause_after)}ms"/>')
        return f"<speak>{before}{''.join(span_parts)}</speak>"
    return f'<speak>{before}<prosody{controls}>{body}</prosody>{after}</speak>'


def _emotion_controls(emotion: str, intensity: float) -> tuple[str, str]:
    strength = max(0.0, min(1.0, float(intensity)))
    if emotion == "excited":
        return f"+{max(1, round(2.0 * strength))}st", f"+{max(1, round(2.5 * strength))}dB"
    if emotion == "serious":
        return f"-{max(1, round(1.5 * strength))}st", "0dB"
    if emotion == "curious":
        return f"+{max(1, round(1.5 * strength))}st", "0dB"
    if emotion == "reflective":
        return f"-{max(1, round(1.0 * strength))}st", f"-{max(1, round(1.5 * strength))}dB"
    return "0st", "0dB"
