"""Compact target-speech ASR input and source-timeline remapping."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from src.audio_pipeline.demucs_runner import run_captured
from src.audio_pipeline.target_speech_authority import (
    TARGET_SPEECH_RECIPE_VERSION,
    TargetSpeechInterval,
)
from src.audio_pipeline.types import TranscriptionUnit
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend, to_windows_long_path


TARGET_SPEECH_AUDIO_RECIPE_VERSION = "target-speech-compact-audio-v2"
_LEAD_SILENCE_SECONDS = 0.18
_GAP_SILENCE_SECONDS = 0.24


@dataclass(frozen=True)
class TargetSpeechTimeMap:
    source_start_seconds: float
    source_end_seconds: float
    compact_start_seconds: float
    compact_end_seconds: float


@dataclass(frozen=True)
class TargetSpeechAudioResult:
    storage_key: str
    compact_duration_seconds: float
    source_duration_seconds: float
    mappings: tuple[TargetSpeechTimeMap, ...]
    cache_hit: bool
    checksum_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_version": TARGET_SPEECH_AUDIO_RECIPE_VERSION,
            "storage_key": self.storage_key,
            "compact_duration_seconds": self.compact_duration_seconds,
            "source_duration_seconds": self.source_duration_seconds,
            "cache_hit": self.cache_hit,
            "checksum_sha256": self.checksum_sha256,
            "mappings": [
                {
                    "source_start_seconds": row.source_start_seconds,
                    "source_end_seconds": row.source_end_seconds,
                    "compact_start_seconds": row.compact_start_seconds,
                    "compact_end_seconds": row.compact_end_seconds,
                }
                for row in self.mappings
            ],
        }


def materialize_compact_target_audio(
    storage: StorageBackend,
    *,
    input_storage_key: str,
    intervals: Sequence[TargetSpeechInterval],
    source_duration_seconds: float,
) -> TargetSpeechAudioResult | None:
    """Concatenate only accepted dialogue windows while retaining a time map."""

    if not isinstance(storage, LocalStorageBackend) or not intervals:
        return None
    source_path = to_windows_long_path(
        storage.resolve(input_storage_key).absolute_path
    )
    if not source_path.is_file() or shutil.which("ffmpeg") is None:
        return None
    normalized = [
        row
        for row in sorted(intervals, key=lambda value: value.start_seconds)
        if row.end_seconds > row.start_seconds
    ]
    if not normalized:
        return None
    source_meta = storage.metadata(input_storage_key)
    identity = {
        "recipe_version": TARGET_SPEECH_AUDIO_RECIPE_VERSION,
        "authority_recipe_version": TARGET_SPEECH_RECIPE_VERSION,
        "source_storage_key": input_storage_key,
        "source_sha256": source_meta.checksum_sha256,
        "intervals": [
            [round(row.start_seconds, 3), round(row.end_seconds, 3)]
            for row in normalized
        ],
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    key = f".cache/target-speech/{digest[:2]}/{digest}.wav"
    mappings = _mappings(normalized)
    compact_duration = (
        mappings[-1].compact_end_seconds if mappings else _LEAD_SILENCE_SECONDS
    )
    if storage.exists(key):
        metadata = storage.metadata(key)
        return TargetSpeechAudioResult(
            storage_key=key,
            compact_duration_seconds=round(compact_duration, 3),
            source_duration_seconds=round(source_duration_seconds, 3),
            mappings=tuple(mappings),
            cache_hit=True,
            checksum_sha256=metadata.checksum_sha256,
        )

    filter_parts = [
        f"anullsrc=r=16000:cl=mono:d={_LEAD_SILENCE_SECONDS:.3f}[lead]"
    ]
    concat_inputs = ["[lead]"]
    for index, row in enumerate(normalized):
        filter_parts.append(
            f"[0:a]atrim=start={row.start_seconds:.3f}:end={row.end_seconds:.3f},"
            "asetpts=PTS-STARTPTS,aresample=16000,aformat=channel_layouts=mono"
            f"[speech{index}]"
        )
        concat_inputs.append(f"[speech{index}]")
        if index < len(normalized) - 1:
            filter_parts.append(
                f"anullsrc=r=16000:cl=mono:d={_GAP_SILENCE_SECONDS:.3f}[gap{index}]"
            )
            concat_inputs.append(f"[gap{index}]")
    filter_parts.append(
        "".join(concat_inputs)
        + f"concat=n={len(concat_inputs)}:v=0:a=1[out]"
    )
    with tempfile.TemporaryDirectory(prefix="target_speech_") as temporary:
        output = Path(temporary) / "target_speech.wav"
        completed = run_captured(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[out]",
                "-c:a",
                "pcm_s16le",
                str(output),
            ]
        )
        if completed.returncode != 0 or not output.is_file():
            return None
        write = storage.write_file(key, output)
    return TargetSpeechAudioResult(
        storage_key=write.storage_key,
        compact_duration_seconds=round(compact_duration, 3),
        source_duration_seconds=round(source_duration_seconds, 3),
        mappings=tuple(mappings),
        cache_hit=False,
        checksum_sha256=write.checksum_sha256,
    )


def remap_compact_transcription_units(
    units: Sequence[TranscriptionUnit],
    *,
    audio: TargetSpeechAudioResult,
) -> list[TranscriptionUnit]:
    output: list[TranscriptionUnit] = []
    for unit in units:
        timed_pieces = _split_timed_unit_across_mappings(
            unit,
            mappings=audio.mappings,
        )
        if timed_pieces is not None:
            output.extend(timed_pieces)
            continue
        overlapping = _overlapping_mappings(unit, audio.mappings)
        if len(overlapping) > 1:
            output.extend(
                _split_untimed_unit_across_mappings(
                    unit,
                    mappings=overlapping,
                )
            )
            continue
        mapping = _best_mapping(unit, audio.mappings)
        if mapping is None:
            continue
        compact_start = max(mapping.compact_start_seconds, float(unit.start_seconds))
        compact_end = min(mapping.compact_end_seconds, float(unit.end_seconds))
        if compact_end <= compact_start:
            continue
        source_start = mapping.source_start_seconds + (
            compact_start - mapping.compact_start_seconds
        )
        source_end = mapping.source_start_seconds + (
            compact_end - mapping.compact_start_seconds
        )
        raw = _remap_raw_timestamps(
            dict(unit.raw_payload or {}),
            mapping=mapping,
        )
        raw["target_speech_remap"] = {
            "recipe_version": TARGET_SPEECH_AUDIO_RECIPE_VERSION,
            "compact_start_seconds": round(compact_start, 3),
            "compact_end_seconds": round(compact_end, 3),
            "source_start_seconds": round(source_start, 3),
            "source_end_seconds": round(source_end, 3),
        }
        output.append(
            replace(
                unit,
                start_seconds=round(source_start, 3),
                end_seconds=round(max(source_start + 0.05, source_end), 3),
                flags=list(
                    dict.fromkeys(
                        [*(unit.flags or []), "target_speech_interval_asr"]
                    )
                ),
                raw_payload=raw,
            )
        )
    return output


def _split_timed_unit_across_mappings(
    unit: TranscriptionUnit,
    *,
    mappings: Sequence[TargetSpeechTimeMap],
) -> list[TranscriptionUnit] | None:
    raw = dict(unit.raw_payload or {})
    values = raw.get("timestamps")
    if not isinstance(values, list) or not values:
        return None
    timings: list[tuple[float, float]] = []
    offset = (
        0.0
        if raw.get("timestamps_are_absolute") is True
        else max(0.0, float(raw.get("chunk_start_seconds") or 0.0))
    )
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        try:
            start = float(value[0]) / 1000.0 + offset
            end = float(value[1]) / 1000.0 + offset
        except (TypeError, ValueError):
            return None
        if start < 0.0 or end <= start:
            return None
        timings.append((start, end))
    split_tokens = [piece for piece in str(unit.text or "").split() if piece]
    compact_text = "".join(str(unit.text or "").split())
    tokens = (
        split_tokens
        if len(split_tokens) == len(timings)
        else list(compact_text)
        if len(compact_text) == len(timings)
        else []
    )
    if len(tokens) != len(timings):
        return None

    assigned: list[tuple[int, str, float, float]] = []
    for token, (start, end) in zip(tokens, timings, strict=True):
        best_index = _best_mapping_index(start, end, mappings)
        if best_index is None:
            continue
        assigned.append((best_index, token, start, end))
    if not assigned:
        return []

    groups: list[list[tuple[int, str, float, float]]] = []
    for value in assigned:
        if groups and groups[-1][-1][0] == value[0]:
            groups[-1].append(value)
        else:
            groups.append([value])
    crossed_mapping = len({value[0] for value in assigned}) > 1
    compact_original = not any(character.isspace() for character in str(unit.text or ""))
    output: list[TranscriptionUnit] = []
    for group in groups:
        mapping_index = group[0][0]
        mapping = mappings[mapping_index]
        source_timestamps: list[list[float]] = []
        kept_tokens: list[str] = []
        compact_starts: list[float] = []
        compact_ends: list[float] = []
        for _index, token, start, end in group:
            clipped_start = max(start, mapping.compact_start_seconds)
            clipped_end = min(end, mapping.compact_end_seconds)
            if clipped_end <= clipped_start:
                continue
            source_start = mapping.source_start_seconds + (
                clipped_start - mapping.compact_start_seconds
            )
            source_end = mapping.source_start_seconds + (
                clipped_end - mapping.compact_start_seconds
            )
            kept_tokens.append(token)
            compact_starts.append(clipped_start)
            compact_ends.append(clipped_end)
            source_timestamps.append(
                [round(source_start * 1000.0, 3), round(source_end * 1000.0, 3)]
            )
        if not kept_tokens:
            continue
        piece_raw = dict(raw)
        piece_raw["timestamps"] = source_timestamps
        piece_raw["timestamps_are_absolute"] = True
        piece_raw["target_speech_remap"] = {
            "recipe_version": TARGET_SPEECH_AUDIO_RECIPE_VERSION,
            "mode": "word_timestamp_mapping_split",
            "mapping_index": mapping_index,
            "compact_start_seconds": round(compact_starts[0], 3),
            "compact_end_seconds": round(compact_ends[-1], 3),
            "source_start_seconds": round(source_timestamps[0][0] / 1000.0, 3),
            "source_end_seconds": round(source_timestamps[-1][1] / 1000.0, 3),
        }
        flags = [*(unit.flags or []), "target_speech_interval_asr"]
        if crossed_mapping:
            flags.append("target_speech_cross_mapping_split")
        output.append(
            replace(
                unit,
                text=("".join(kept_tokens) if compact_original else " ".join(kept_tokens)),
                start_seconds=round(source_timestamps[0][0] / 1000.0, 3),
                end_seconds=round(source_timestamps[-1][1] / 1000.0, 3),
                flags=list(dict.fromkeys(flags)),
                raw_payload=piece_raw,
            )
        )
    return output


def _split_untimed_unit_across_mappings(
    unit: TranscriptionUnit,
    *,
    mappings: Sequence[TargetSpeechTimeMap],
) -> list[TranscriptionUnit]:
    """Preserve text when a provider omits word timestamps across compact cuts."""

    raw_text = str(unit.text or "")
    compact = "".join(raw_text.split())
    tokens = list(compact) if compact else []
    if not tokens:
        return []
    weights = [
        max(
            0.0,
            min(float(unit.end_seconds), row.compact_end_seconds)
            - max(float(unit.start_seconds), row.compact_start_seconds),
        )
        for row in mappings
    ]
    total_weight = sum(weights)
    if total_weight <= 0:
        return []
    counts: list[int] = []
    remaining = len(tokens)
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            count = remaining
        else:
            count = min(
                remaining,
                max(1, int(round(len(tokens) * weight / total_weight))),
            )
        counts.append(count)
        remaining -= count
    if remaining < 0:
        counts[-1] += remaining

    output: list[TranscriptionUnit] = []
    cursor = 0
    for mapping, count in zip(mappings, counts, strict=True):
        piece_tokens = tokens[cursor : cursor + max(0, count)]
        cursor += max(0, count)
        if not piece_tokens:
            continue
        compact_start = max(float(unit.start_seconds), mapping.compact_start_seconds)
        compact_end = min(float(unit.end_seconds), mapping.compact_end_seconds)
        if compact_end <= compact_start:
            continue
        source_start = mapping.source_start_seconds + (
            compact_start - mapping.compact_start_seconds
        )
        source_end = mapping.source_start_seconds + (
            compact_end - mapping.compact_start_seconds
        )
        piece_raw = dict(unit.raw_payload or {})
        piece_raw["target_speech_remap"] = {
            "recipe_version": TARGET_SPEECH_AUDIO_RECIPE_VERSION,
            "mode": "duration_weighted_text_split",
            "compact_start_seconds": round(compact_start, 3),
            "compact_end_seconds": round(compact_end, 3),
            "source_start_seconds": round(source_start, 3),
            "source_end_seconds": round(source_end, 3),
        }
        output.append(
            replace(
                unit,
                text="".join(piece_tokens),
                start_seconds=round(source_start, 3),
                end_seconds=round(source_end, 3),
                flags=list(
                    dict.fromkeys(
                        [
                            *(unit.flags or []),
                            "target_speech_interval_asr",
                            "target_speech_cross_mapping_heuristic_split",
                            "needs_operator_review",
                        ]
                    )
                ),
                raw_payload=piece_raw,
            )
        )
    return output


def filter_units_to_target_intervals(
    units: Sequence[TranscriptionUnit],
    intervals: Sequence[TargetSpeechInterval],
) -> list[TranscriptionUnit]:
    """Fail-closed fallback when compact materialization is unavailable."""

    output: list[TranscriptionUnit] = []
    for unit in units:
        midpoint = (float(unit.start_seconds) + float(unit.end_seconds)) / 2.0
        if any(
            row.start_seconds - 0.10 <= midpoint <= row.end_seconds + 0.10
            for row in intervals
        ):
            output.append(
                replace(
                    unit,
                    flags=list(
                        dict.fromkeys(
                            [*(unit.flags or []), "target_speech_postfilter"]
                        )
                    ),
                )
            )
    return output


def materialize_preserved_background(
    storage: StorageBackend,
    *,
    original_storage_key: str,
    demucs_background_storage_key: str,
    target_intervals: Sequence[TargetSpeechInterval],
) -> str | None:
    """Use no-vocals only during target speech; preserve all other source audio."""

    if (
        not isinstance(storage, LocalStorageBackend)
        or not target_intervals
        or shutil.which("ffmpeg") is None
    ):
        return None
    original = to_windows_long_path(storage.resolve(original_storage_key).absolute_path)
    background = to_windows_long_path(
        storage.resolve(demucs_background_storage_key).absolute_path
    )
    if not original.is_file() or not background.is_file():
        return None
    identity = {
        "recipe_version": "target-speech-preserved-background-v1",
        "original_sha256": storage.metadata(original_storage_key).checksum_sha256,
        "background_sha256": storage.metadata(
            demucs_background_storage_key
        ).checksum_sha256,
        "intervals": [
            [round(row.start_seconds, 3), round(row.end_seconds, 3)]
            for row in target_intervals
        ],
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    key = f".cache/target-speech-background/{digest[:2]}/{digest}.wav"
    if storage.exists(key):
        return key
    conditions = "+".join(
        f"between(t\\,{row.start_seconds:.3f}\\,{row.end_seconds:.3f})"
        for row in target_intervals
    )
    condition = f"gt({conditions}\\,0)"
    filter_complex = (
        f"[0:a]volume='if({condition}\\,0\\,1)':eval=frame[original];"
        f"[1:a]volume='if({condition}\\,1\\,0)':eval=frame[bed];"
        "[original][bed]amix=inputs=2:duration=first:normalize=0[out]"
    )
    with tempfile.TemporaryDirectory(prefix="target_background_") as temporary:
        output = Path(temporary) / "preserved_background.wav"
        completed = run_captured(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(original),
                "-i",
                str(background),
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                "-c:a",
                "pcm_s16le",
                str(output),
            ]
        )
        if completed.returncode != 0 or not output.is_file():
            return None
        write = storage.write_file(key, output)
    return write.storage_key


def _mappings(
    intervals: Sequence[TargetSpeechInterval],
) -> list[TargetSpeechTimeMap]:
    cursor = _LEAD_SILENCE_SECONDS
    output: list[TargetSpeechTimeMap] = []
    for index, row in enumerate(intervals):
        duration = row.end_seconds - row.start_seconds
        output.append(
            TargetSpeechTimeMap(
                source_start_seconds=round(row.start_seconds, 3),
                source_end_seconds=round(row.end_seconds, 3),
                compact_start_seconds=round(cursor, 3),
                compact_end_seconds=round(cursor + duration, 3),
            )
        )
        cursor += duration
        if index < len(intervals) - 1:
            cursor += _GAP_SILENCE_SECONDS
    return output


def _best_mapping(
    unit: TranscriptionUnit,
    mappings: Sequence[TargetSpeechTimeMap],
) -> TargetSpeechTimeMap | None:
    best: tuple[float, TargetSpeechTimeMap] | None = None
    for row in mappings:
        overlap = max(
            0.0,
            min(float(unit.end_seconds), row.compact_end_seconds)
            - max(float(unit.start_seconds), row.compact_start_seconds),
        )
        if best is None or overlap > best[0]:
            best = (overlap, row)
    return best[1] if best is not None and best[0] > 0 else None


def _overlapping_mappings(
    unit: TranscriptionUnit,
    mappings: Sequence[TargetSpeechTimeMap],
) -> list[TargetSpeechTimeMap]:
    return [
        row
        for row in mappings
        if min(float(unit.end_seconds), row.compact_end_seconds)
        - max(float(unit.start_seconds), row.compact_start_seconds)
        > 0
    ]


def _best_mapping_index(
    start_seconds: float,
    end_seconds: float,
    mappings: Sequence[TargetSpeechTimeMap],
) -> int | None:
    best: tuple[float, int] | None = None
    for index, row in enumerate(mappings):
        overlap = max(
            0.0,
            min(end_seconds, row.compact_end_seconds)
            - max(start_seconds, row.compact_start_seconds),
        )
        if best is None or overlap > best[0]:
            best = (overlap, index)
    return best[1] if best is not None and best[0] > 0 else None


def _remap_raw_timestamps(
    raw: dict[str, Any],
    *,
    mapping: TargetSpeechTimeMap,
) -> dict[str, Any]:
    values = raw.get("timestamps")
    if not isinstance(values, list):
        return raw
    remapped: list[list[float]] = []
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return raw
        try:
            start_ms, end_ms = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return raw
        compact_start = start_ms / 1000.0
        compact_end = end_ms / 1000.0
        if compact_end <= mapping.compact_start_seconds or compact_start >= mapping.compact_end_seconds:
            continue
        source_start = mapping.source_start_seconds + (
            max(compact_start, mapping.compact_start_seconds)
            - mapping.compact_start_seconds
        )
        source_end = mapping.source_start_seconds + (
            min(compact_end, mapping.compact_end_seconds)
            - mapping.compact_start_seconds
        )
        remapped.append([round(source_start * 1000.0, 3), round(source_end * 1000.0, 3)])
    if remapped:
        raw["timestamps"] = remapped
        raw["timestamps_are_absolute"] = True
    return raw
