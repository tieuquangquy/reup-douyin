from __future__ import annotations

import re
import tempfile
from pathlib import Path
from uuid import uuid4

from src.tts_pipeline.services.timing_fit import timing_fit_flags
from src.tts_pipeline.types import SubtitleDraftSegment, SynthesizedSegment, TranslationInputSegment

DEFAULT_MAX_CHARS_PER_LINE = 18
# Split wall-of-text cues that span too long with too much copy.
_SPLIT_MIN_DURATION_MS = 6_000
_SPLIT_MIN_CHARS = 48
_PHRASE_SPLIT_RE = re.compile(r"(?<=[\.\!\?…。！？;；])\s+|(?<=[,，])\s+")


class SubtitleBuilder:
    def __init__(self, *, layout_mode: str = "bottom_safe_area", track_kind: str = "vietnamese_hard_burn"):
        self.layout_mode = layout_mode
        self.track_kind = track_kind

    def build(self, segments: list[TranslationInputSegment], synthesized: list[SynthesizedSegment]) -> list[SubtitleDraftSegment]:
        synthesized_by_id = {item.input_segment.translation_segment_id: item for item in synthesized}
        subtitles: list[SubtitleDraftSegment] = []
        for segment in segments:
            synth = synthesized_by_id.get(segment.translation_segment_id)
            flags = list(segment.quality_flags)
            metadata = {
                "line_break_strategy": "balanced_18_chars",
                "max_chars_per_line": DEFAULT_MAX_CHARS_PER_LINE,
            }
            if synth:
                flags.extend(timing_fit_flags(synth.fit_status))
                metadata["tts_duration_seconds"] = synth.duration_seconds
                metadata["tts_fit_ratio"] = round(synth.fit_ratio, 3)
            subtitles.append(
                SubtitleDraftSegment(
                    translation_segment_id=segment.translation_segment_id,
                    segment_index=segment.segment_index,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.translated_text,
                    layout_mode=self.layout_mode,
                    track_kind=self.track_kind,
                    review_flags=list(dict.fromkeys(flags)),
                    metadata=metadata,
                )
            )
        return subtitles


def wrap_subtitle_lines(text: str, *, max_chars: int = DEFAULT_MAX_CHARS_PER_LINE) -> str:
    normalized = " ".join((text or "").replace("\n", " ").split())
    if not normalized:
        return ""
    if len(normalized) <= max_chars:
        return normalized
    words = normalized.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        if len(word) <= max_chars:
            current = word
        else:
            # Hard-split overlong tokens so burn never emits a single mega-line.
            while len(word) > max_chars:
                lines.append(word[:max_chars])
                word = word[max_chars:]
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines)


def prepare_subtitle_drafts_for_burn(
    drafts: list[SubtitleDraftSegment],
    *,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
) -> list[SubtitleDraftSegment]:
    prepared: list[SubtitleDraftSegment] = []
    for draft in drafts:
        pieces = _split_draft_if_needed(draft)
        for index, piece in enumerate(pieces):
            prepared.append(
                SubtitleDraftSegment(
                    translation_segment_id=piece.translation_segment_id,
                    segment_index=piece.segment_index if len(pieces) == 1 else piece.segment_index * 1000 + index,
                    start_ms=piece.start_ms,
                    end_ms=piece.end_ms,
                    text=wrap_subtitle_lines(piece.text, max_chars=max_chars_per_line),
                    layout_mode=piece.layout_mode,
                    track_kind=piece.track_kind,
                    review_flags=list(piece.review_flags),
                    metadata={
                        **dict(piece.metadata or {}),
                        "burn_prepared": True,
                        "max_chars_per_line": max_chars_per_line,
                    },
                )
            )
    return prepared


def build_srt(subtitles: list[SubtitleDraftSegment]) -> str:
    prepared = prepare_subtitle_drafts_for_burn(subtitles)
    blocks: list[str] = []
    for index, segment in enumerate(prepared, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_srt_time(segment.start_ms)} --> {_srt_time(segment.end_ms)}",
                    segment.text,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def prepare_srt_file_for_burn(subtitle_path: str) -> tuple[str, list[str]]:
    """Rewrite an on-disk SRT into burn-ready cues (split + wrap). Returns (path, warnings)."""
    source = Path(subtitle_path)
    raw = source.read_text(encoding="utf-8")
    drafts = parse_srt_to_drafts(raw)
    original_cue_count = len(drafts)
    prepared = prepare_subtitle_drafts_for_burn(drafts)
    warnings: list[str] = []
    if original_cue_count == 1 and (drafts[0].end_ms - drafts[0].start_ms) >= _SPLIT_MIN_DURATION_MS and len(drafts[0].text) >= _SPLIT_MIN_CHARS:
        warnings.append("subtitle_single_cue_wall")
    if len(prepared) > original_cue_count:
        warnings.append("subtitle_cue_split_for_burn")
    if any("\n" in item.text for item in prepared):
        warnings.append("subtitle_lines_wrapped_for_burn")

    out_text = build_srt_from_prepared(prepared)
    out_path = source.with_name(f"{source.stem}__burn_ready{source.suffix}")
    try:
        out_path.write_text(out_text, encoding="utf-8")
    except OSError:
        handle = tempfile.NamedTemporaryFile(prefix="reup_burn_srt_", suffix=".srt", delete=False)
        handle.write(out_text.encode("utf-8"))
        handle.close()
        out_path = Path(handle.name)
    return str(out_path), warnings


def build_srt_from_prepared(prepared: list[SubtitleDraftSegment]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(prepared, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_srt_time(segment.start_ms)} --> {_srt_time(segment.end_ms)}",
                    segment.text,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def parse_srt_to_drafts(srt_text: str) -> list[SubtitleDraftSegment]:
    blocks = re.split(r"\n\s*\n", (srt_text or "").strip())
    drafts: list[SubtitleDraftSegment] = []
    for index, block in enumerate(blocks):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        timing_line = lines[1] if "-->" in lines[1] else lines[0]
        if "-->" not in timing_line:
            continue
        start_raw, end_raw = [part.strip() for part in timing_line.split("-->")]
        text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
        text = " ".join(text_lines)
        drafts.append(
            SubtitleDraftSegment(
                translation_segment_id=uuid4(),
                segment_index=index,
                start_ms=_parse_srt_time(start_raw),
                end_ms=_parse_srt_time(end_raw),
                text=text,
                layout_mode="bottom_safe_area",
                track_kind="vietnamese_hard_burn",
                review_flags=[],
                metadata={"from_srt": True},
            )
        )
    return drafts


def _split_draft_if_needed(draft: SubtitleDraftSegment) -> list[SubtitleDraftSegment]:
    duration = max(0, draft.end_ms - draft.start_ms)
    text = " ".join((draft.text or "").replace("\n", " ").split())
    if duration < _SPLIT_MIN_DURATION_MS or len(text) < _SPLIT_MIN_CHARS:
        return [draft]
    phrases = _split_phrases(text)
    if len(phrases) <= 1:
        return [draft]
    weights = [max(1, len(phrase)) for phrase in phrases]
    total = sum(weights)
    cursor = draft.start_ms
    split: list[SubtitleDraftSegment] = []
    for index, phrase in enumerate(phrases):
        if index == len(phrases) - 1:
            end_ms = draft.end_ms
        else:
            span = int(round(duration * (weights[index] / total)))
            end_ms = min(draft.end_ms, cursor + max(800, span))
        if end_ms <= cursor:
            end_ms = min(draft.end_ms, cursor + 800)
        split.append(
            SubtitleDraftSegment(
                translation_segment_id=draft.translation_segment_id,
                segment_index=draft.segment_index,
                start_ms=cursor,
                end_ms=end_ms,
                text=phrase,
                layout_mode=draft.layout_mode,
                track_kind=draft.track_kind,
                review_flags=list(draft.review_flags),
                metadata={**(draft.metadata or {}), "split_from_wall_cue": True},
            )
        )
        cursor = end_ms
    if split:
        split[-1] = SubtitleDraftSegment(
            translation_segment_id=split[-1].translation_segment_id,
            segment_index=split[-1].segment_index,
            start_ms=split[-1].start_ms,
            end_ms=draft.end_ms,
            text=split[-1].text,
            layout_mode=split[-1].layout_mode,
            track_kind=split[-1].track_kind,
            review_flags=list(split[-1].review_flags),
            metadata=dict(split[-1].metadata or {}),
        )
    return split


def _split_phrases(text: str) -> list[str]:
    parts = [part.strip() for part in _PHRASE_SPLIT_RE.split(text) if part and part.strip()]
    if len(parts) >= 2:
        return parts
    # Fallback: pack ~2 lines worth of words into phrases.
    words = text.split()
    if len(words) < 8:
        return [text]
    chunk_size = max(4, len(words) // 4)
    phrases: list[str] = []
    for index in range(0, len(words), chunk_size):
        phrases.append(" ".join(words[index : index + chunk_size]))
    return phrases


def _srt_time(ms: int) -> str:
    total_ms = max(0, ms)
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    seconds = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def _parse_srt_time(value: str) -> int:
    cleaned = value.strip().replace(",", ".")
    hours_s, minutes_s, seconds_s = cleaned.split(":")
    seconds, millis = seconds_s.split(".")
    return (
        int(hours_s) * 3_600_000
        + int(minutes_s) * 60_000
        + int(seconds) * 1000
        + int(millis[:3].ljust(3, "0"))
    )
