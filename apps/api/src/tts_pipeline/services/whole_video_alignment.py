"""Silence-aware sentence boundary recovery for whole-video TTS audio."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from typing import Sequence
import wave

import numpy as np

from src.audio_pipeline.speech_budget import count_spoken_units
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.types import TranslationInputSegment


WHOLE_VIDEO_ALIGNMENT_VERSION = "whole-video-silence-alignment-v2"


@dataclass(frozen=True)
class AlignedNarrationSlice:
    segment: TranslationInputSegment
    audio_bytes: bytes
    duration_seconds: float
    start_frame: int
    end_frame: int
    boundary_confidence: float
    boundary_shift_ms: int


def split_whole_video_wav(
    content: bytes,
    segments: Sequence[TranslationInputSegment],
    *,
    search_window_ms: int = 6_000,
    energy_window_ms: int = 160,
) -> list[AlignedNarrationSlice]:
    """Split canonical PCM WAV at stable pauses using global sequence matching.

    Gemini is explicitly prompted to pause between transcript paragraphs.  The
    source timeline and relative text density provide weak priors, while broad
    low-energy valleys provide the acoustic evidence.  Boundaries are selected
    jointly so a short intra-word valley cannot make later sentences drift.
    This avoids ASR/model cost and never reorders or changes approved text.
    """

    rows = sorted(segments, key=lambda row: (row.start_ms, row.segment_index))
    if not rows:
        return []
    pcm, sample_rate = _read_mono_pcm16(content)
    if len(rows) == 1:
        return [_slice(rows[0], pcm, sample_rate, 0, len(pcm), 1.0, 0)]
    block_start = rows[0].start_ms
    block_end = rows[-1].end_ms
    source_span_ms = max(1, block_end - block_start)
    search_frames = max(1, int(round(sample_rate * max(500, search_window_ms) / 1000.0)))
    energy_frames = max(8, int(round(sample_rate * max(80, energy_window_ms) / 1000.0)))
    absolute = np.abs(pcm.astype(np.int32)).astype(np.float64)
    global_energy = float(np.mean(absolute)) if len(absolute) else 1.0
    cumulative = np.concatenate(([0.0], np.cumsum(absolute, dtype=np.float64)))

    minimum_slice_frames = max(1, int(round(sample_rate * 0.18)))
    expected_frames = [
        int(
            round(
                ((((left.end_ms + right.start_ms) / 2.0) - block_start) / source_span_ms)
                * len(pcm)
            )
        )
        for left, right in zip(rows[:-1], rows[1:], strict=True)
    ]
    valley_candidates = _stable_valley_candidates(
        absolute,
        cumulative,
        sample_rate=sample_rate,
        energy_frames=energy_frames,
        global_energy=global_energy,
    )
    selected = _select_boundary_sequence(
        valley_candidates,
        expected_frames=expected_frames,
        rows=rows,
        total_frames=len(pcm),
        search_frames=search_frames,
        minimum_slice_frames=minimum_slice_frames,
        global_energy=global_energy,
    )
    if selected is None:
        selected = _fallback_boundaries(
            cumulative,
            expected_frames=expected_frames,
            total_frames=len(pcm),
            sample_rate=sample_rate,
            energy_frames=energy_frames,
            search_frames=search_frames,
            minimum_slice_frames=minimum_slice_frames,
            global_energy=global_energy,
        )
    boundary_frames, boundary_energies = selected
    cuts = [0, *boundary_frames, len(pcm)]
    confidences = []
    shifts = []
    for cut, valley, expected_frame in zip(
        boundary_frames,
        boundary_energies,
        expected_frames,
        strict=True,
    ):
        energy_confidence = 1.0 - min(1.0, valley / max(1.0, global_energy))
        distance_confidence = 1.0 - min(
            1.0,
            abs(cut - expected_frame) / max(1, search_frames),
        )
        confidences.append(
            max(0.0, min(1.0, 0.85 * energy_confidence + 0.15 * distance_confidence))
        )
        shifts.append(int(round((cut - expected_frame) * 1000.0 / sample_rate)))

    output: list[AlignedNarrationSlice] = []
    for index, row in enumerate(rows):
        confidence = min(
            confidences[index - 1] if index > 0 else 1.0,
            confidences[index] if index < len(confidences) else 1.0,
        )
        shift_candidates = []
        if index > 0:
            shift_candidates.append(shifts[index - 1])
        if index < len(shifts):
            shift_candidates.append(shifts[index])
        shift = max(shift_candidates, key=abs) if shift_candidates else 0
        output.append(
            _slice(
                row,
                pcm,
                sample_rate,
                cuts[index],
                cuts[index + 1],
                confidence,
                shift,
            )
        )
    return output


def _stable_valley_candidates(
    absolute: np.ndarray,
    cumulative: np.ndarray,
    *,
    sample_rate: int,
    energy_frames: int,
    global_energy: float,
) -> list[tuple[int, float]]:
    """Return broad, deep valleys and reject brief phoneme-level minima."""

    if len(absolute) <= energy_frames:
        return []
    hop = max(1, int(round(sample_rate * 0.01)))
    half = energy_frames // 2
    centers = np.arange(half, len(absolute) - half, hop, dtype=np.int64)
    if len(centers) == 0:
        return []
    energies = (
        cumulative[centers + half] - cumulative[centers - half]
    ) / max(1, energy_frames)
    # A stable TTS paragraph pause is normally far below both the global
    # signal energy and the lowest decile of broad-window energy.  Requiring
    # both prevents a quiet spoken syllable from masquerading as a boundary.
    threshold = min(
        float(np.quantile(energies, 0.10)),
        max(1.0, float(global_energy) * 0.03),
    )
    below = energies <= threshold
    candidates: list[tuple[int, float]] = []
    start: int | None = None
    for index, is_below in enumerate(below):
        if bool(is_below) and start is None:
            start = index
        at_end = index == len(below) - 1
        if start is None or (bool(is_below) and not at_end):
            continue
        end = index + 1 if bool(is_below) and at_end else index
        if end > start:
            offset = start + int(np.argmin(energies[start:end]))
            candidates.append((int(centers[offset]), float(energies[offset])))
        start = None
    return candidates


def _select_boundary_sequence(
    candidates: Sequence[tuple[int, float]],
    *,
    expected_frames: Sequence[int],
    rows: Sequence[TranslationInputSegment],
    total_frames: int,
    search_frames: int,
    minimum_slice_frames: int,
    global_energy: float,
) -> tuple[list[int], list[float]] | None:
    """Choose all paragraph boundaries jointly with text-density priors."""

    boundary_count = len(expected_frames)
    if boundary_count == 0:
        return ([], [])
    if len(candidates) < boundary_count:
        return None
    spoken_units = [
        max(1, int(count_spoken_units(str(row.translated_text or ""))))
        for row in rows
    ]
    total_units = max(1, sum(spoken_units))
    target_frames = [
        max(minimum_slice_frames, total_frames * units / total_units)
        for units in spoken_units
    ]
    # Each state is candidate_index -> (cost, selected candidate indices).
    states: dict[int, tuple[float, list[int]]] = {}
    for boundary_index, expected in enumerate(expected_frames):
        next_states: dict[int, tuple[float, list[int]]] = {}
        remaining = len(rows) - boundary_index - 1
        for candidate_index, (position, energy) in enumerate(candidates):
            if (
                abs(position - expected) > search_frames
                or position < minimum_slice_frames
                or total_frames - position < remaining * minimum_slice_frames
            ):
                continue
            predecessors = [(-1, 0.0, [])] if boundary_index == 0 else [
                (index, value[0], value[1]) for index, value in states.items()
            ]
            best: tuple[float, list[int]] | None = None
            for previous_index, previous_cost, path in predecessors:
                previous_position = 0 if previous_index < 0 else candidates[previous_index][0]
                if position - previous_position < minimum_slice_frames:
                    continue
                duration_ratio = (position - previous_position) / max(
                    1.0, target_frames[boundary_index]
                )
                duration_cost = 0.70 * math.log(max(0.1, duration_ratio)) ** 2
                acoustic_cost = 0.20 * min(
                    1.0, float(energy) / max(1.0, global_energy * 0.03)
                )
                location_cost = 0.04 * (
                    (position - expected) / max(1, search_frames)
                ) ** 2
                cost = previous_cost + duration_cost + acoustic_cost + location_cost
                if best is None or cost < best[0]:
                    best = (cost, [*path, candidate_index])
            if best is not None:
                next_states[candidate_index] = best
        if not next_states:
            return None
        states = next_states

    best_final: tuple[float, list[int]] | None = None
    for last_index, (cost, path) in states.items():
        last_duration = total_frames - candidates[last_index][0]
        ratio = last_duration / max(1.0, target_frames[-1])
        final_cost = cost + 0.70 * math.log(max(0.1, ratio)) ** 2
        if best_final is None or final_cost < best_final[0]:
            best_final = (final_cost, path)
    if best_final is None:
        return None
    return (
        [int(candidates[index][0]) for index in best_final[1]],
        [float(candidates[index][1]) for index in best_final[1]],
    )


def _fallback_boundaries(
    cumulative: np.ndarray,
    *,
    expected_frames: Sequence[int],
    total_frames: int,
    sample_rate: int,
    energy_frames: int,
    search_frames: int,
    minimum_slice_frames: int,
    global_energy: float,
) -> tuple[list[int], list[float]]:
    """Monotonic broad-window fallback when explicit pauses are unavailable."""

    cuts: list[int] = []
    energies_out: list[float] = []
    step = max(1, int(round(sample_rate * 0.01)))
    half = energy_frames // 2
    for index, expected in enumerate(expected_frames):
        lower = max((cuts[-1] if cuts else 0) + minimum_slice_frames, expected - search_frames)
        remaining = len(expected_frames) - index
        upper = min(total_frames - remaining * minimum_slice_frames, expected + search_frames)
        if upper <= lower:
            cut = max(lower, min(total_frames - remaining, expected))
            valley = float(global_energy)
        else:
            positions = np.arange(lower, upper + 1, step, dtype=np.int64)
            starts = np.maximum(0, positions - half)
            ends = np.minimum(total_frames, positions + half)
            energies = (cumulative[ends] - cumulative[starts]) / np.maximum(1, ends - starts)
            distance = np.abs(positions - expected) / max(1, search_frames)
            score = energies / max(1.0, global_energy) + 0.08 * distance**2
            chosen = int(np.argmin(score))
            cut = int(positions[chosen])
            valley = float(energies[chosen])
            if 1.0 - min(1.0, valley / max(1.0, global_energy)) < 0.15:
                cut = max(lower, min(upper, expected))
                valley = float(global_energy)
        cuts.append(cut)
        energies_out.append(valley)
    return cuts, energies_out


def _slice(
    segment: TranslationInputSegment,
    pcm: np.ndarray,
    sample_rate: int,
    start: int,
    end: int,
    confidence: float,
    shift_ms: int,
) -> AlignedNarrationSlice:
    clipped = pcm[max(0, start) : max(start + 1, end)]
    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(clipped.astype("<i2").tobytes())
    return AlignedNarrationSlice(
        segment=segment,
        audio_bytes=output.getvalue(),
        duration_seconds=len(clipped) / float(sample_rate),
        start_frame=max(0, start),
        end_frame=max(start + 1, end),
        boundary_confidence=round(float(confidence), 6),
        boundary_shift_ms=int(shift_ms),
    )


def _read_mono_pcm16(content: bytes) -> tuple[np.ndarray, int]:
    try:
        with wave.open(BytesIO(content), "rb") as handle:
            channels = int(handle.getnchannels())
            width = int(handle.getsampwidth())
            sample_rate = int(handle.getframerate())
            raw = handle.readframes(handle.getnframes())
    except (EOFError, wave.Error) as exc:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
            "Whole-video alignment received invalid WAV audio",
        ) from exc
    if channels != 1 or width != 2 or sample_rate <= 0:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
            "Whole-video alignment requires canonical mono PCM16 WAV audio",
        )
    return np.frombuffer(raw, dtype="<i2").copy(), sample_rate
