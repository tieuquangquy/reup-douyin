"""Local-first, provider-neutral Context-Aware TTS Director."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence

from src.audio_pipeline.speech_budget import count_spoken_units
from src.tts_pipeline.types import (
    ProsodySegment,
    ProsodySpan,
    ProsodyState,
    TranslationInputSegment,
    TtsDirectorPlan,
    VoiceBible,
    VoiceConfig,
)
from src.tts_pipeline.services.emotion_planner import EmotionDecision


TTS_DIRECTOR_VERSION = "context-aware-tts-director-v2"
_EMOTION_TERMS = {
    "serious": ("đáng sợ", "nguy hiểm", "cảnh báo", "nghiêm trọng", "sự thật"),
    "positive": ("cơ hội", "tuyệt vời", "thành công", "hy vọng", "tin tốt"),
    "reflective": ("suy nghĩ", "bài học", "nhớ rằng", "tôi nghĩ", "nhìn lại"),
    "excited": ("bất ngờ", "không thể tin", "quá", "thật tuyệt"),
}
_TRANSITION_TERMS = {
    "contrast": ("nhưng", "tuy nhiên", "trái lại", "không phải"),
    "conclusion": ("vì vậy", "do đó", "cuối cùng", "tóm lại", "chính là"),
    "explanation": ("bởi vì", "nghĩa là", "cụ thể", "ví dụ"),
}
_EMPHASIS_TERMS = (
    "đáng sợ",
    "quan trọng",
    "không phải",
    "chính là",
    "ngừng học",
    "duy nhất",
)


def build_voice_bible(
    *,
    voice_config: VoiceConfig,
    runtime_authority: Mapping[str, object] | None,
    options: Mapping[str, object] | None = None,
) -> VoiceBible:
    authority = dict(runtime_authority or {})
    raw_options = dict(options or {})
    raw = raw_options.get("voice_bible")
    configured = dict(raw) if isinstance(raw, Mapping) else {}
    rules = tuple(
        str(value).strip()
        for value in list(configured.get("director_rules") or [])
        if str(value).strip()
    ) or (
        "preserve natural Vietnamese conversational flow",
        "use emotion as a genuine reaction, never theatrical acting",
        "keep chunk boundaries emotionally continuous",
        "do not speak control tags aloud",
    )
    return VoiceBible(
        voice_id=str(authority.get("voice_id") or voice_config.voice_id),
        language_code=str(authority.get("language_code") or voice_config.language_code or "vi"),
        provider=str(authority.get("provider") or ""),
        model_id=str(authority.get("model_id") or ""),
        persona=str(configured.get("persona") or "engaging Vietnamese narrator"),
        accent=str(configured.get("accent") or _default_accent(voice_config.voice_id)),
        speaking_style=str(
            configured.get("speaking_style") or "natural conversational narration"
        ),
        baseline_pace=_bounded(configured.get("baseline_pace"), 0.7, 1.3, 1.0),
        energy=_bounded(configured.get("energy"), 0.0, 1.0, 0.5),
        articulation=str(configured.get("articulation") or "clear but not stiff"),
        breathing_behavior=str(
            configured.get("breathing_behavior") or "natural breathing between complete thoughts"
        ),
        pause_behavior=str(
            configured.get("pause_behavior") or "brief pauses at semantic boundaries"
        ),
        director_rules=rules,
        recipe_version=str(configured.get("recipe_version") or TTS_DIRECTOR_VERSION),
    )


def build_local_director_plan(
    segments: Sequence[TranslationInputSegment],
    *,
    source_video_id,
    voice_bible: VoiceBible,
    source_context: Mapping[str, object] | None = None,
    emotion_decisions: Mapping[int, EmotionDecision] | None = None,
    emotion_enabled: bool | None = None,
) -> TtsDirectorPlan:
    context = dict(source_context or {})
    event_windows = _event_windows(context)
    state = ProsodyState(
        speaker="narrator_01",
        current_emotion="neutral",
        energy=voice_bible.energy,
        pace=voice_bible.baseline_pace,
        pitch_state="mid",
        previous_intent="establishing",
    )
    output: list[ProsodySegment] = []
    previous_end = 0
    for segment in sorted(segments, key=lambda row: (row.start_ms, row.segment_index)):
        text = " ".join(str(segment.translated_text or "").split())
        overlap = _overlapping_event_summary(
            event_windows,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
        )
        decision = (emotion_decisions or {}).get(int(segment.segment_index))
        if emotion_enabled is False:
            emotion = "neutral"
        elif emotion_enabled is True:
            emotion = decision.emotion if decision is not None else "neutral"
        else:
            # Backwards-compatible direct callers/tests retain the historical
            # local heuristic; production orchestration passes an explicit
            # provider-scoped gate.
            emotion = _emotion(text, overlap)
        transition = _transition(text)
        semantic_weight = _semantic_weight(text, transition)
        intensity = (
            float(decision.intensity)
            if emotion_enabled is True and decision is not None
            else (_intensity(text, emotion, semantic_weight, overlap) if emotion_enabled is not False else 0.4)
        )
        pace = _pace(voice_bible.baseline_pace, emotion, semantic_weight)
        gap_ms = max(0, int(segment.start_ms) - int(previous_end))
        pause_before = min(450, gap_ms)
        pause_after = _pause_after(text, transition, semantic_weight)
        emphasis = tuple(term for term in _EMPHASIS_TERMS if term in text.casefold())[:3]
        if not emphasis and semantic_weight >= 0.82:
            emphasis = _fallback_emphasis(text)
        speaker = str(segment.speaker_label or state.speaker or "narrator_01")
        target_state = ProsodyState(
            speaker=speaker,
            current_emotion=emotion,
            energy=intensity,
            pace=pace,
            pitch_state=_pitch_state(emotion, intensity),
            previous_intent=transition,
        )
        tags = _canonical_tags(
            emotion=emotion,
            pace=pace,
            pause_after_ms=pause_after,
            emphasis=emphasis,
        )
        confidence = (
            float(decision.confidence)
            if emotion_enabled is True and decision is not None
            else min(
                0.96,
                0.58
                + (0.12 if emotion != "neutral" else 0.0)
                + (0.10 if overlap else 0.0)
                + (0.08 if transition != "continue" else 0.0),
            )
        )
        spans = _build_prosody_spans(
            text,
            baseline_pace=voice_bible.baseline_pace,
            overlap=overlap,
            span_decisions=(decision.span_decisions if emotion_enabled is True and decision is not None else ()),
            emotion_enabled=emotion_enabled,
        )
        output.append(
            ProsodySegment(
                translation_segment_id=segment.translation_segment_id,
                segment_index=segment.segment_index,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                emotion=emotion,
                intensity=intensity,
                pace=pace,
                pause_before_ms=pause_before,
                pause_after_ms=pause_after,
                emphasis=emphasis,
                breath="natural",
                transition=transition,
                semantic_weight=semantic_weight,
                speaker_state="engaged" if intensity >= 0.55 else "composed",
                audio_tags=tags,
                confidence=confidence,
                previous_state=state,
                target_state=target_state,
                source=(
                    "text_conditioned_emotion_planner"
                    if emotion_enabled is True
                    else "local_audio_semantic_director"
                ),
                spans=spans,
            )
        )
        state = target_state
        previous_end = segment.end_ms
    context_hash = _sha256_json(
        {
            "audio_event_timeline": context.get("audio_event_timeline"),
            "semantic_dialogue_segmentation": context.get(
                "semantic_dialogue_segmentation"
            ),
            "target_speech_authority_sha256": context.get(
                "target_speech_authority_sha256"
            ),
        }
    )
    return TtsDirectorPlan(
        source_video_id=source_video_id,
        voice_bible=voice_bible,
        prosody_segments=tuple(output),
        source_context_sha256=context_hash,
        director_version=TTS_DIRECTOR_VERSION,
    )


def _build_prosody_spans(
    text: str,
    *,
    baseline_pace: float,
    overlap: list[dict],
    span_decisions: Sequence[Mapping[str, object]] = (),
    emotion_enabled: bool | None = None,
) -> tuple[ProsodySpan, ...]:
    """Create clause-level direction without changing subtitle/timeline rows."""
    parts = [
        " ".join(part.split())
        for part in re.split(r"(?<=[.!?;:\u2026])\s+", str(text or "").strip())
        if part.strip()
    ]
    if not parts:
        return ()
    spans: list[ProsodySpan] = []
    for part_index, part in enumerate(parts):
        transition = _transition(part)
        weight = _semantic_weight(part, transition)
        planned = (
            dict(span_decisions[part_index])
            if part_index < len(span_decisions)
            else {}
        )
        if emotion_enabled is False:
            emotion = "neutral"
            intensity = 0.4
        elif emotion_enabled is True:
            emotion = str(planned.get("emotion") or "neutral")
            intensity = _bounded(planned.get("intensity"), 0.15, 0.9, 0.4)
        else:
            emotion = _emotion(part, overlap)
            intensity = _intensity(part, emotion, weight, overlap)
        pace = _pace(baseline_pace, emotion, weight)
        pause = _pause_after(part, transition, weight)
        emphasis = tuple(
            term for term in _EMPHASIS_TERMS if term in part.casefold()
        )[:3]
        if not emphasis and weight >= 0.82:
            emphasis = _fallback_emphasis(part)
        spans.append(
            ProsodySpan(
                text=part,
                emotion=emotion,
                intensity=intensity,
                pace=pace,
                pause_after_ms=pause,
                emphasis=emphasis,
                audio_tags=_canonical_tags(
                    emotion=emotion,
                    pace=pace,
                    pause_after_ms=pause,
                    emphasis=emphasis,
                ),
            )
        )
    return tuple(spans)


def _emotion(text: str, overlap: list[dict]) -> str:
    lowered = text.casefold()
    for emotion, terms in _EMOTION_TERMS.items():
        if any(term in lowered for term in terms):
            return emotion
    if "?" in text:
        return "curious"
    if "!" in text:
        return "excited"
    labels = {str(row.get("label") or "").upper() for row in overlap}
    if "REACTION_OR_SFX" in labels:
        return "excited"
    return "neutral"


def _transition(text: str) -> str:
    lowered = text.casefold().lstrip("–—- ")
    for transition, terms in _TRANSITION_TERMS.items():
        if any(lowered.startswith(term) or f" {term} " in lowered for term in terms):
            return transition
    if "?" in text:
        return "question"
    return "continue"


def _semantic_weight(text: str, transition: str) -> float:
    units = count_spoken_units(text)
    base = 0.38 + min(0.30, units / 80.0)
    if transition in {"contrast", "conclusion"}:
        base += 0.16
    if any(term in text.casefold() for term in _EMPHASIS_TERMS):
        base += 0.14
    return round(min(1.0, base), 6)


def _intensity(
    text: str,
    emotion: str,
    semantic_weight: float,
    overlap: list[dict],
) -> float:
    value = 0.38 + (semantic_weight * 0.22)
    if emotion in {"excited", "positive"}:
        value += 0.18
    elif emotion == "serious":
        value += 0.08
    if "!" in text:
        value += 0.10
    rms_values = [
        float(dict(row.get("features") or {}).get("rms_dbfs"))
        for row in overlap
        if isinstance(row.get("features"), Mapping)
        and dict(row.get("features") or {}).get("rms_dbfs") is not None
    ]
    if rms_values and max(rms_values) > -20.0:
        value += 0.08
    return round(max(0.15, min(0.95, value)), 6)


def _pace(baseline: float, emotion: str, semantic_weight: float) -> float:
    value = float(baseline)
    if emotion == "excited":
        value *= 1.06
    elif emotion in {"serious", "reflective"}:
        value *= 0.94
    if semantic_weight >= 0.85:
        value *= 0.97
    return round(max(0.75, min(1.18, value)), 6)


def _pause_after(text: str, transition: str, semantic_weight: float) -> int:
    if text.rstrip().endswith(("!", "?")):
        return 320
    if transition == "conclusion" or semantic_weight >= 0.88:
        return 420
    if text.rstrip().endswith((".", ";", ":")):
        return 240
    return 120


def _canonical_tags(
    *, emotion: str, pace: float, pause_after_ms: int, emphasis: tuple[str, ...]
) -> tuple[str, ...]:
    tags: list[str] = []
    if emotion != "neutral":
        tags.append(emotion)
    if pace <= 0.92:
        tags.append("slow")
    elif pace >= 1.08:
        tags.append("fast")
    if emphasis:
        tags.append("emphasis")
    if pause_after_ms >= 400:
        tags.append("long pause")
    elif pause_after_ms >= 220:
        tags.append("short pause")
    return tuple(dict.fromkeys(tags))


def _fallback_emphasis(text: str) -> tuple[str, ...]:
    words = [value.strip(".,!?;:…") for value in text.split() if len(value.strip(".,!?;:…")) >= 5]
    return tuple(words[-2:])


def _pitch_state(emotion: str, intensity: float) -> str:
    if emotion in {"excited", "positive", "curious"} and intensity >= 0.6:
        return "mid-high"
    if emotion in {"serious", "reflective"}:
        return "mid-low"
    return "mid"


def _event_windows(context: Mapping[str, object]) -> list[dict]:
    timeline = context.get("audio_event_timeline")
    if not isinstance(timeline, Mapping):
        target = context.get("target_speech_authority")
        timeline = target.get("audio_event_timeline") if isinstance(target, Mapping) else None
    if not isinstance(timeline, Mapping):
        return []
    return [dict(row) for row in list(timeline.get("windows") or []) if isinstance(row, Mapping)]


def _overlapping_event_summary(
    windows: Sequence[Mapping[str, object]], *, start_ms: int, end_ms: int
) -> list[dict]:
    output: list[dict] = []
    for raw in windows:
        row = dict(raw)
        try:
            start = float(row.get("start_seconds") or 0.0) * 1000.0
            end = float(row.get("end_seconds") or 0.0) * 1000.0
        except (TypeError, ValueError):
            continue
        if min(float(end_ms), end) > max(float(start_ms), start):
            output.append(row)
    return output


def _default_accent(voice_id: str) -> str:
    lowered = str(voice_id or "").casefold()
    if "south" in lowered:
        return "Southern Vietnamese"
    if "north" in lowered or "hanoi" in lowered:
        return "Hanoi Vietnamese"
    return "natural Vietnamese"


def _bounded(value: object, minimum: float, maximum: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(minimum, min(maximum, parsed)), 6)


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
