"""Local multi-evidence authority for dialogue-worthy speech.

Silero answers whether a waveform resembles human voice.  It cannot decide
whether that voice is narration, singing, a jingle, a reaction, or speech from
another source inside the scene.  This module combines the measured VAD
intervals with inexpensive acoustic evidence and emits a fail-closed temporal
authority before ASR is allowed to create DialogueBeats.

The implementation is intentionally local: a pinned YAMNet ONNX AudioSet model
and NumPy/SciPy features run against the already-decoded PCM WAV.
"""

from __future__ import annotations

import math
import wave
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.signal import resample_poly

from src.audio_pipeline.types import VadResult
from src.audio_pipeline.yamnet_audio_events import (
    YamnetEvidence,
    score_yamnet_waveform,
)


TARGET_SPEECH_RECIPE_VERSION = "target-speech-authority-v2"
TARGET_SPEECH_SCHEMA_VERSION = "target_speech_authority_v1"
AUDIO_EVENT_TIMELINE_SCHEMA_VERSION = "audio_event_timeline_v1"

_ANALYSIS_SAMPLE_RATE = 16_000
_WINDOW_SECONDS = 0.96
_HOP_SECONDS = 0.48
_MIN_INTERVAL_SECONDS = 0.28
_MERGE_GAP_SECONDS = 0.22
_PAD_SECONDS = 0.12
_STRONG_SINGING_ABSOLUTE_SCORE = 0.82
_STRONG_SINGING_CONSENSUS_SCORE = 0.68
_STRONG_SINGING_MIN_WINDOW_RATIO = 0.55


class AudioEventLabel(StrEnum):
    PRIMARY_DIALOGUE = "PRIMARY_DIALOGUE"
    SPEECH_MUSIC_AMBIGUOUS = "SPEECH_MUSIC_AMBIGUOUS"
    SINGING_OR_RAP = "SINGING_OR_RAP"
    MUSIC = "MUSIC"
    REACTION_OR_SFX = "REACTION_OR_SFX"
    SILENCE = "SILENCE"
    UNCERTAIN = "UNCERTAIN"


class TargetSpeechStatus(StrEnum):
    READY = "READY"
    PARTIAL_UNCERTAIN = "PARTIAL_UNCERTAIN"
    NO_TARGET_SPEECH = "NO_TARGET_SPEECH"
    UNCERTAIN = "UNCERTAIN"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AcousticFeatures:
    rms_dbfs: float
    spectral_flatness: float
    voice_band_ratio: float
    harmonicity: float
    voiced_ratio: float
    pitch_stability: float
    chroma_concentration: float
    rhythmicity: float
    stereo_side_ratio: float


@dataclass(frozen=True)
class AudioEventWindow:
    start_seconds: float
    end_seconds: float
    label: AudioEventLabel
    confidence: float
    vad_overlap: float
    speech_score: float
    music_score: float
    singing_score: float
    features: AcousticFeatures


@dataclass(frozen=True)
class TargetSpeechInterval:
    start_seconds: float
    end_seconds: float
    decision: str
    confidence: float
    speech_score: float
    music_score: float
    singing_score: float
    reasons: tuple[str, ...]
    requires_separation: bool = False

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)


@dataclass(frozen=True)
class TargetSpeechAuthority:
    status: TargetSpeechStatus
    provider: str
    duration_seconds: float
    target_intervals: tuple[TargetSpeechInterval, ...]
    ambiguous_intervals: tuple[TargetSpeechInterval, ...]
    rejected_intervals: tuple[TargetSpeechInterval, ...]
    event_windows: tuple[AudioEventWindow, ...]
    requires_separation: bool
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TARGET_SPEECH_SCHEMA_VERSION,
            "recipe_version": TARGET_SPEECH_RECIPE_VERSION,
            "status": self.status.value,
            "provider": self.provider,
            "duration_seconds": self.duration_seconds,
            "requires_separation": self.requires_separation,
            "target_intervals": [_interval_dict(row) for row in self.target_intervals],
            "ambiguous_intervals": [
                _interval_dict(row) for row in self.ambiguous_intervals
            ],
            "rejected_intervals": [
                _interval_dict(row) for row in self.rejected_intervals
            ],
            "audio_event_timeline": {
                "schema_version": AUDIO_EVENT_TIMELINE_SCHEMA_VERSION,
                "windows": [_window_dict(row) for row in self.event_windows],
            },
            "diagnostics": dict(self.diagnostics),
        }


def analyze_target_speech(
    path: str | Path,
    *,
    vad: VadResult,
    duration_seconds: float | None = None,
    provider: str = "local_dsp_silero_consensus",
) -> TargetSpeechAuthority:
    """Classify measured voice intervals before ASR can create dialogue."""

    signal, stereo_side_ratio, sample_rate, measured_duration = _read_pcm(path)
    duration = max(float(duration_seconds or 0.0), measured_duration)
    intervals = _vad_intervals(vad, duration_seconds=duration)
    yamnet = score_yamnet_waveform(signal)
    effective_provider = (
        "local_dsp_silero_yamnet"
        if yamnet is not None
        else provider
    )
    windows = _event_windows(
        signal,
        sample_rate=sample_rate,
        stereo_side_ratio=stereo_side_ratio,
        vad_intervals=intervals,
        duration_seconds=duration,
        yamnet=yamnet,
    )
    if not vad.has_speech or not intervals:
        return _authority(
            status=TargetSpeechStatus.NO_TARGET_SPEECH,
            provider=effective_provider,
            duration=duration,
            windows=windows,
            target=(),
            ambiguous=(),
            rejected=(),
            reasons=["vad_no_measured_speech"],
            event_model_version=(yamnet.model_version if yamnet else None),
        )

    target: list[TargetSpeechInterval] = []
    ambiguous: list[TargetSpeechInterval] = []
    rejected: list[TargetSpeechInterval] = []
    for start, end in intervals:
        evidence = _aggregate_interval(windows, start=start, end=end)
        speech = evidence["speech_score"]
        music = evidence["music_score"]
        singing = evidence["singing_score"]
        labels = set(evidence["labels"])
        reasons: list[str] = []
        if _strong_singing_interval(evidence):
            reasons.extend(["singing_or_rap_acoustic_signature", "preserve_non_dialogue_vocal"])
            rejected.append(
                _interval(start, end, "REJECT_NON_DIALOGUE", singing, speech, music, singing, reasons)
            )
            continue
        mixed = bool(
            music >= 0.48
            or singing >= 0.42
            or AudioEventLabel.SPEECH_MUSIC_AMBIGUOUS.value in labels
        )
        if speech >= 0.50:
            reasons.append("measured_vad_and_acoustic_speech_consensus")
            if (
                AudioEventLabel.SINGING_OR_RAP.value in labels
                and float(evidence.get("singing_label_ratio") or 0.0)
                < _STRONG_SINGING_MIN_WINDOW_RATIO
            ):
                reasons.append("isolated_singing_windows_overridden_by_speech_consensus")
            if mixed:
                reasons.append("foreground_speech_over_music_requires_separation")
            target.append(
                _interval(
                    start,
                    end,
                    "ACCEPT_DIALOGUE",
                    min(0.99, 0.65 * speech + 0.35 * (1.0 - singing)),
                    speech,
                    music,
                    singing,
                    reasons,
                    requires_separation=mixed,
                )
            )
            continue
        reasons.append("speech_music_or_source_provenance_uncertain")
        ambiguous.append(
            _interval(
                start,
                end,
                "UNCERTAIN",
                max(speech, music, singing),
                speech,
                music,
                singing,
                reasons,
                requires_separation=True,
            )
        )

    target = _merge_intervals(target, duration_seconds=duration)
    ambiguous = _merge_intervals(ambiguous, duration_seconds=duration)
    rejected = _merge_intervals(rejected, duration_seconds=duration, pad=False)
    if target and not ambiguous:
        status = TargetSpeechStatus.READY
    elif target:
        status = TargetSpeechStatus.PARTIAL_UNCERTAIN
    elif ambiguous:
        status = TargetSpeechStatus.UNCERTAIN
    else:
        status = TargetSpeechStatus.NO_TARGET_SPEECH
    return _authority(
        status=status,
        provider=effective_provider,
        duration=duration,
        windows=windows,
        target=target,
        ambiguous=ambiguous,
        rejected=rejected,
        reasons=["local_multi_evidence_target_speech_gate"],
        event_model_version=(yamnet.model_version if yamnet else None),
    )


def resolve_after_separation(
    original: TargetSpeechAuthority,
    separated: TargetSpeechAuthority,
) -> TargetSpeechAuthority:
    """Resolve mixed intervals without allowing a song vocal to become dialogue."""

    if not original.requires_separation:
        return original
    candidates = [*original.target_intervals, *original.ambiguous_intervals]
    target: list[TargetSpeechInterval] = []
    ambiguous: list[TargetSpeechInterval] = []
    rejected = list(original.rejected_intervals)
    for candidate in candidates:
        if _overlaps_any(candidate, original.rejected_intervals, minimum_ratio=0.35):
            rejected.append(
                _with_decision(
                    candidate,
                    decision="REJECT_NON_DIALOGUE",
                    reasons=[*candidate.reasons, "original_mix_singing_veto"],
                )
            )
            continue
        vocal_matches = _overlapping_intervals(
            candidate,
            separated.target_intervals,
            minimum_ratio=0.20,
        )
        vocal_rejected = _overlapping_intervals(
            candidate,
            separated.rejected_intervals,
            minimum_ratio=0.30,
        )
        if vocal_rejected and not vocal_matches:
            rejected.append(
                _with_decision(
                    candidate,
                    decision="REJECT_NON_DIALOGUE",
                    reasons=[*candidate.reasons, "vocal_stem_singing_veto"],
                )
            )
            continue
        if vocal_matches:
            confidence = max(row.confidence for row in vocal_matches)
            target.append(
                TargetSpeechInterval(
                    start_seconds=candidate.start_seconds,
                    end_seconds=candidate.end_seconds,
                    decision="ACCEPT_DIALOGUE",
                    confidence=round(min(0.99, 0.45 * candidate.confidence + 0.55 * confidence), 6),
                    speech_score=max(row.speech_score for row in vocal_matches),
                    music_score=min(candidate.music_score, max(row.music_score for row in vocal_matches)),
                    singing_score=max(row.singing_score for row in vocal_matches),
                    reasons=tuple(
                        dict.fromkeys(
                            [*candidate.reasons, "separated_vocal_speech_consensus"]
                        )
                    ),
                    requires_separation=False,
                )
            )
            continue
        ambiguous.append(
            _with_decision(
                candidate,
                decision="UNCERTAIN",
                reasons=[*candidate.reasons, "separated_vocal_did_not_resolve"],
            )
        )

    duration = max(original.duration_seconds, separated.duration_seconds)
    target = _merge_intervals(target, duration_seconds=duration, pad=False)
    ambiguous = _merge_intervals(ambiguous, duration_seconds=duration, pad=False)
    rejected = _merge_intervals(rejected, duration_seconds=duration, pad=False)
    if target and not ambiguous:
        status = TargetSpeechStatus.READY
    elif target:
        status = TargetSpeechStatus.PARTIAL_UNCERTAIN
    elif ambiguous:
        status = TargetSpeechStatus.UNCERTAIN
    else:
        status = TargetSpeechStatus.NO_TARGET_SPEECH
    return _authority(
        status=status,
        provider="local_dsp_silero_demucs_consensus",
        duration=duration,
        windows=original.event_windows,
        target=target,
        ambiguous=ambiguous,
        rejected=rejected,
        reasons=["post_separation_target_speech_consensus"],
        separated_diagnostics=separated.diagnostics,
    )


def unavailable_target_speech_authority(
    *,
    duration_seconds: float,
    reason: str,
) -> TargetSpeechAuthority:
    return _authority(
        status=TargetSpeechStatus.UNAVAILABLE,
        provider="unavailable_fail_closed",
        duration=max(0.0, float(duration_seconds or 0.0)),
        windows=(),
        target=(),
        ambiguous=(),
        rejected=(),
        reasons=[str(reason)],
    )


def _read_pcm(path: str | Path) -> tuple[np.ndarray, float, int, float]:
    with wave.open(str(Path(path)), "rb") as handle:
        channels = int(handle.getnchannels())
        sample_rate = int(handle.getframerate())
        source_sample_rate = sample_rate
        sample_width = int(handle.getsampwidth())
        frames = int(handle.getnframes())
        if sample_width != 2 or sample_rate <= 0 or frames <= 0:
            raise ValueError("target_speech_requires_pcm16_wav")
        raw = handle.readframes(frames)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    samples = samples[: samples.size - (samples.size % channels)]
    matrix = samples.reshape(-1, channels)
    mono = matrix.mean(axis=1)
    if channels > 1:
        mid = matrix[:, 0] + matrix[:, 1]
        side = matrix[:, 0] - matrix[:, 1]
        side_ratio = float(
            np.sqrt(np.mean(np.square(side), dtype=np.float64))
            / max(1e-8, np.sqrt(np.mean(np.square(mid), dtype=np.float64)))
        )
    else:
        side_ratio = 0.0
    if sample_rate != _ANALYSIS_SAMPLE_RATE:
        divisor = math.gcd(sample_rate, _ANALYSIS_SAMPLE_RATE)
        mono = resample_poly(
            mono,
            _ANALYSIS_SAMPLE_RATE // divisor,
            sample_rate // divisor,
        ).astype(np.float32)
        sample_rate = _ANALYSIS_SAMPLE_RATE
    return (
        mono,
        min(1.0, side_ratio),
        sample_rate,
        frames / max(1, source_sample_rate),
    )


def _vad_intervals(vad: VadResult, *, duration_seconds: float) -> list[tuple[float, float]]:
    values = list(dict(vad.metadata or {}).get("speech_intervals") or [])
    parsed: list[tuple[float, float]] = []
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            continue
        try:
            start, end = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            continue
        start = max(0.0, min(duration_seconds, start))
        end = max(start, min(duration_seconds, end))
        if end - start >= 0.05:
            parsed.append((start, end))
    if not parsed and vad.has_speech and duration_seconds > 0:
        parsed.append((0.0, duration_seconds))
    return _merge_spans(parsed)


def _event_windows(
    signal: np.ndarray,
    *,
    sample_rate: int,
    stereo_side_ratio: float,
    vad_intervals: Sequence[tuple[float, float]],
    duration_seconds: float,
    yamnet: YamnetEvidence | None,
) -> tuple[AudioEventWindow, ...]:
    window_samples = max(1, int(round(_WINDOW_SECONDS * sample_rate)))
    hop_samples = max(1, int(round(_HOP_SECONDS * sample_rate)))
    frame_count = 1 + int(
        math.ceil(max(0, signal.size - window_samples) / max(1, hop_samples))
    )
    starts = [index * hop_samples for index in range(max(1, frame_count))]
    rows: list[AudioEventWindow] = []
    for start_sample in sorted(set(starts)):
        end_sample = min(signal.size, start_sample + window_samples)
        chunk = signal[start_sample:end_sample]
        start = start_sample / sample_rate
        end = max(start + 0.01, end_sample / sample_rate)
        features = _features(
            chunk,
            sample_rate=sample_rate,
            stereo_side_ratio=stereo_side_ratio,
        )
        vad_overlap = _span_overlap_ratio(start, end, vad_intervals)
        frame_index = int(start_sample // hop_samples)
        yamnet_row = (
            yamnet.frames[frame_index]
            if yamnet is not None and frame_index < len(yamnet.frames)
            else None
        )
        label, confidence, speech, music, singing = _classify(
            features,
            vad_overlap=vad_overlap,
            yamnet=yamnet_row,
        )
        rows.append(
            AudioEventWindow(
                start_seconds=round(start, 3),
                end_seconds=round(min(duration_seconds, end), 3),
                label=label,
                confidence=round(confidence, 6),
                vad_overlap=round(vad_overlap, 6),
                speech_score=round(speech, 6),
                music_score=round(music, 6),
                singing_score=round(singing, 6),
                features=features,
            )
        )
    return tuple(rows)


def _features(
    signal: np.ndarray,
    *,
    sample_rate: int,
    stereo_side_ratio: float,
) -> AcousticFeatures:
    if signal.size < 256:
        signal = np.pad(signal, (0, 256 - signal.size))
    rms = float(np.sqrt(np.mean(np.square(signal), dtype=np.float64)))
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-9))
    frame = 512
    hop = 256
    framed = _frame_signal(signal, frame=frame, hop=hop)
    window = np.hanning(frame).astype(np.float32)
    power = np.square(np.abs(np.fft.rfft(framed * window, axis=1))) + 1e-12
    flatness = np.exp(np.mean(np.log(power), axis=1)) / np.mean(power, axis=1)
    frequencies = np.fft.rfftfreq(frame, d=1.0 / sample_rate)
    voice_mask = (frequencies >= 250.0) & (frequencies <= 3_800.0)
    voice_ratio = float(np.median(power[:, voice_mask].sum(axis=1) / power.sum(axis=1)))
    harmonicity, voiced_ratio, pitch_stability = _pitch_features(
        signal,
        sample_rate=sample_rate,
    )
    chroma_concentration = _chroma_concentration(power.mean(axis=0), frequencies)
    rhythmicity = _rhythmicity(framed)
    return AcousticFeatures(
        rms_dbfs=round(rms_dbfs, 3),
        spectral_flatness=round(float(np.median(flatness)), 6),
        voice_band_ratio=round(voice_ratio, 6),
        harmonicity=round(harmonicity, 6),
        voiced_ratio=round(voiced_ratio, 6),
        pitch_stability=round(pitch_stability, 6),
        chroma_concentration=round(chroma_concentration, 6),
        rhythmicity=round(rhythmicity, 6),
        stereo_side_ratio=round(stereo_side_ratio, 6),
    )


def _classify(
    features: AcousticFeatures,
    *,
    vad_overlap: float,
    yamnet: Any | None = None,
) -> tuple[AudioEventLabel, float, float, float, float]:
    if features.rms_dbfs <= -52.0:
        return AudioEventLabel.SILENCE, 0.98, 0.0, 0.0, 0.0
    tonal = (
        0.30 * features.harmonicity
        + 0.22 * features.chroma_concentration
        + 0.18 * features.rhythmicity
        + 0.15 * (1.0 - min(1.0, features.spectral_flatness * 2.0))
        + 0.10 * features.voiced_ratio
        + 0.05 * features.stereo_side_ratio
    )
    music_score = max(0.0, min(1.0, tonal))
    speech_score = max(
        0.0,
        min(
            1.0,
            vad_overlap
            * (
                0.48
                + 0.25 * features.voice_band_ratio
                + 0.17 * (1.0 - features.pitch_stability)
                + 0.10 * features.harmonicity
            ),
        ),
    )
    singing_score = max(
        0.0,
        min(
            1.0,
            vad_overlap
            * (
                0.34 * music_score
                + 0.27 * features.pitch_stability
                + 0.22 * features.voiced_ratio
                + 0.17 * features.rhythmicity
            ),
        ),
    )
    if yamnet is not None:
        speech_score = max(
            speech_score,
            min(
                1.0,
                vad_overlap * (0.50 * float(yamnet.speech) + 0.25),
            ),
        )
        music_score = max(music_score, float(yamnet.music))
        singing_score = max(
            singing_score,
            min(
                1.0,
                0.70 * float(yamnet.singing)
                + 0.20 * float(yamnet.music)
                + 0.10 * float(yamnet.reaction),
            ),
        )
        if (
            float(yamnet.reaction) >= 0.55
            and float(yamnet.speech) < 0.45
            and singing_score < 0.55
        ):
            return (
                AudioEventLabel.REACTION_OR_SFX,
                float(yamnet.reaction),
                speech_score,
                music_score,
                singing_score,
            )
    if vad_overlap < 0.15:
        if music_score >= 0.42:
            return AudioEventLabel.MUSIC, music_score, speech_score, music_score, singing_score
        confidence = min(0.95, 0.55 + (0.42 - music_score))
        return AudioEventLabel.REACTION_OR_SFX, confidence, speech_score, music_score, singing_score
    if singing_score >= 0.58:
        return AudioEventLabel.SINGING_OR_RAP, singing_score, speech_score, music_score, singing_score
    if music_score >= 0.48 and (features.rhythmicity >= 0.42 or singing_score >= 0.42):
        confidence = max(music_score, speech_score, singing_score)
        return AudioEventLabel.SPEECH_MUSIC_AMBIGUOUS, confidence, speech_score, music_score, singing_score
    if speech_score >= 0.48:
        return AudioEventLabel.PRIMARY_DIALOGUE, speech_score, speech_score, music_score, singing_score
    confidence = max(speech_score, music_score, singing_score, 0.5)
    return AudioEventLabel.UNCERTAIN, confidence, speech_score, music_score, singing_score


def _pitch_features(signal: np.ndarray, *, sample_rate: int) -> tuple[float, float, float]:
    frame = max(320, int(round(sample_rate * 0.04)))
    hop = max(160, int(round(sample_rate * 0.02)))
    frames = _frame_signal(signal, frame=frame, hop=hop)
    min_lag = max(1, int(sample_rate / 420.0))
    max_lag = min(frame - 2, int(sample_rate / 70.0))
    harmonicities: list[float] = []
    pitches: list[float] = []
    for raw in frames:
        centered = raw - float(np.mean(raw))
        energy = float(np.dot(centered, centered))
        if energy <= 1e-8:
            continue
        fft_size = 1 << int(math.ceil(math.log2(frame * 2 - 1)))
        spectrum = np.fft.rfft(centered, n=fft_size)
        correlation = np.fft.irfft(
            spectrum * np.conjugate(spectrum), n=fft_size
        )[:frame]
        region = correlation[min_lag : max_lag + 1]
        if region.size == 0:
            continue
        relative = int(np.argmax(region))
        lag = min_lag + relative
        strength = float(region[relative] / max(1e-8, correlation[0]))
        harmonicities.append(max(0.0, min(1.0, strength)))
        if strength >= 0.28:
            pitches.append(sample_rate / lag)
    harmonicity = float(np.median(harmonicities)) if harmonicities else 0.0
    voiced_ratio = len(pitches) / max(1, len(harmonicities))
    if len(pitches) < 2:
        stability = 0.0
    else:
        semitones = 12.0 * np.log2(np.asarray(pitches) / max(1e-6, float(np.median(pitches))))
        stability = float(math.exp(-max(0.0, float(np.std(semitones))) / 3.0))
    return harmonicity, voiced_ratio, max(0.0, min(1.0, stability))


def _chroma_concentration(power: np.ndarray, frequencies: np.ndarray) -> float:
    chroma = np.zeros(12, dtype=np.float64)
    for value, frequency in zip(power, frequencies, strict=True):
        if frequency < 80.0 or frequency > 4_000.0:
            continue
        midi = int(round(69 + 12 * math.log2(float(frequency) / 440.0)))
        chroma[midi % 12] += float(value)
    total = float(chroma.sum())
    if total <= 0:
        return 0.0
    probability = chroma / total
    entropy = -float(np.sum(probability * np.log(probability + 1e-12))) / math.log(12.0)
    return max(0.0, min(1.0, 1.0 - entropy))


def _rhythmicity(frames: np.ndarray) -> float:
    energy = np.sqrt(np.mean(np.square(frames), axis=1, dtype=np.float64))
    if energy.size < 6 or float(np.max(energy)) <= 1e-8:
        return 0.0
    onset = np.maximum(0.0, np.diff(energy, prepend=energy[0]))
    if float(np.sum(onset)) <= 1e-8:
        return 0.0
    onset = onset - float(np.mean(onset))
    correlation = np.correlate(onset, onset, mode="full")[onset.size - 1 :]
    if correlation.size < 4 or correlation[0] <= 1e-8:
        return 0.0
    peak = float(np.max(correlation[2:])) if correlation.size > 2 else 0.0
    return max(0.0, min(1.0, peak / float(correlation[0])))


def _frame_signal(signal: np.ndarray, *, frame: int, hop: int) -> np.ndarray:
    if signal.size < frame:
        signal = np.pad(signal, (0, frame - signal.size))
    count = 1 + max(0, (signal.size - frame) // hop)
    output = np.empty((count, frame), dtype=np.float32)
    for index in range(count):
        start = index * hop
        output[index] = signal[start : start + frame]
    return output


def _aggregate_interval(
    windows: Sequence[AudioEventWindow],
    *,
    start: float,
    end: float,
) -> dict[str, Any]:
    weighted: list[tuple[AudioEventWindow, float]] = []
    for row in windows:
        overlap = max(0.0, min(end, row.end_seconds) - max(start, row.start_seconds))
        if overlap > 0:
            weighted.append((row, overlap))
    if not weighted:
        return {
            "speech_score": 0.0,
            "music_score": 0.0,
            "singing_score": 0.0,
            "labels": [AudioEventLabel.UNCERTAIN.value],
            "label_ratios": {AudioEventLabel.UNCERTAIN.value: 1.0},
            "singing_label_ratio": 0.0,
        }
    total = sum(weight for _row, weight in weighted)
    label_weights: dict[str, float] = {}
    for row, weight in weighted:
        label_weights[row.label.value] = label_weights.get(row.label.value, 0.0) + weight
    label_ratios = {
        label: weight / total for label, weight in label_weights.items()
    }
    return {
        "speech_score": sum(row.speech_score * weight for row, weight in weighted) / total,
        "music_score": sum(row.music_score * weight for row, weight in weighted) / total,
        "singing_score": sum(row.singing_score * weight for row, weight in weighted) / total,
        "labels": [row.label.value for row, _weight in weighted],
        "label_ratios": label_ratios,
        "singing_label_ratio": label_ratios.get(
            AudioEventLabel.SINGING_OR_RAP.value,
            0.0,
        ),
    }


def _strong_singing_interval(evidence: Mapping[str, Any]) -> bool:
    """Require sustained evidence before rejecting a measured speech interval.

    A single 960 ms YAMNet/DSP window is not allowed to veto a complete Silero
    interval. This matters for narration over music, where pitch and rhythmic
    features can briefly resemble singing even though speech dominates the
    interval. Very strong aggregate evidence can still reject immediately;
    otherwise a majority of the interval must agree on singing/rap.
    """

    singing = max(0.0, min(1.0, float(evidence.get("singing_score") or 0.0)))
    singing_ratio = max(
        0.0,
        min(1.0, float(evidence.get("singing_label_ratio") or 0.0)),
    )
    return bool(
        singing >= _STRONG_SINGING_ABSOLUTE_SCORE
        or (
            singing >= _STRONG_SINGING_CONSENSUS_SCORE
            and singing_ratio >= _STRONG_SINGING_MIN_WINDOW_RATIO
        )
    )


def _interval(
    start: float,
    end: float,
    decision: str,
    confidence: float,
    speech: float,
    music: float,
    singing: float,
    reasons: Sequence[str],
    *,
    requires_separation: bool = False,
) -> TargetSpeechInterval:
    return TargetSpeechInterval(
        start_seconds=round(start, 3),
        end_seconds=round(end, 3),
        decision=decision,
        confidence=round(max(0.0, min(1.0, confidence)), 6),
        speech_score=round(max(0.0, min(1.0, speech)), 6),
        music_score=round(max(0.0, min(1.0, music)), 6),
        singing_score=round(max(0.0, min(1.0, singing)), 6),
        reasons=tuple(dict.fromkeys(str(value) for value in reasons if str(value))),
        requires_separation=requires_separation,
    )


def _merge_intervals(
    rows: Sequence[TargetSpeechInterval],
    *,
    duration_seconds: float,
    pad: bool = True,
) -> list[TargetSpeechInterval]:
    if not rows:
        return []
    output: list[TargetSpeechInterval] = []
    for row in sorted(rows, key=lambda value: (value.start_seconds, value.end_seconds)):
        start = max(0.0, row.start_seconds - (_PAD_SECONDS if pad else 0.0))
        end = min(duration_seconds, row.end_seconds + (_PAD_SECONDS if pad else 0.0))
        current = TargetSpeechInterval(
            start_seconds=round(start, 3),
            end_seconds=round(end, 3),
            decision=row.decision,
            confidence=row.confidence,
            speech_score=row.speech_score,
            music_score=row.music_score,
            singing_score=row.singing_score,
            reasons=row.reasons,
            requires_separation=row.requires_separation,
        )
        if current.duration_seconds < _MIN_INTERVAL_SECONDS:
            continue
        if (
            output
            and current.start_seconds <= output[-1].end_seconds + _MERGE_GAP_SECONDS
            and current.decision == output[-1].decision
        ):
            previous = output[-1]
            output[-1] = TargetSpeechInterval(
                start_seconds=previous.start_seconds,
                end_seconds=max(previous.end_seconds, current.end_seconds),
                decision=previous.decision,
                confidence=max(previous.confidence, current.confidence),
                speech_score=max(previous.speech_score, current.speech_score),
                music_score=max(previous.music_score, current.music_score),
                singing_score=max(previous.singing_score, current.singing_score),
                reasons=tuple(dict.fromkeys([*previous.reasons, *current.reasons])),
                requires_separation=previous.requires_separation or current.requires_separation,
            )
        else:
            output.append(current)
    return output


def _merge_spans(rows: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    output: list[tuple[float, float]] = []
    for start, end in sorted(rows):
        if output and start <= output[-1][1] + 0.08:
            output[-1] = (output[-1][0], max(output[-1][1], end))
        else:
            output.append((start, end))
    return output


def _span_overlap_ratio(
    start: float,
    end: float,
    intervals: Sequence[tuple[float, float]],
) -> float:
    overlap = sum(max(0.0, min(end, right) - max(start, left)) for left, right in intervals)
    return max(0.0, min(1.0, overlap / max(1e-6, end - start)))


def _overlap_ratio(left: TargetSpeechInterval, right: TargetSpeechInterval) -> float:
    overlap = max(
        0.0,
        min(left.end_seconds, right.end_seconds)
        - max(left.start_seconds, right.start_seconds),
    )
    return overlap / max(1e-6, min(left.duration_seconds, right.duration_seconds))


def _overlapping_intervals(
    row: TargetSpeechInterval,
    candidates: Sequence[TargetSpeechInterval],
    *,
    minimum_ratio: float,
) -> list[TargetSpeechInterval]:
    return [value for value in candidates if _overlap_ratio(row, value) >= minimum_ratio]


def _overlaps_any(
    row: TargetSpeechInterval,
    candidates: Sequence[TargetSpeechInterval],
    *,
    minimum_ratio: float,
) -> bool:
    return bool(_overlapping_intervals(row, candidates, minimum_ratio=minimum_ratio))


def _with_decision(
    row: TargetSpeechInterval,
    *,
    decision: str,
    reasons: Sequence[str],
) -> TargetSpeechInterval:
    return TargetSpeechInterval(
        start_seconds=row.start_seconds,
        end_seconds=row.end_seconds,
        decision=decision,
        confidence=row.confidence,
        speech_score=row.speech_score,
        music_score=row.music_score,
        singing_score=row.singing_score,
        reasons=tuple(dict.fromkeys(str(value) for value in reasons if str(value))),
        requires_separation=False,
    )


def _authority(
    *,
    status: TargetSpeechStatus,
    provider: str,
    duration: float,
    windows: Sequence[AudioEventWindow],
    target: Sequence[TargetSpeechInterval],
    ambiguous: Sequence[TargetSpeechInterval],
    rejected: Sequence[TargetSpeechInterval],
    reasons: Sequence[str],
    separated_diagnostics: Mapping[str, Any] | None = None,
    event_model_version: str | None = None,
) -> TargetSpeechAuthority:
    target_seconds = sum(row.duration_seconds for row in target)
    ambiguous_seconds = sum(row.duration_seconds for row in ambiguous)
    rejected_seconds = sum(row.duration_seconds for row in rejected)
    counts: dict[str, int] = {}
    for row in windows:
        counts[row.label.value] = counts.get(row.label.value, 0) + 1
    diagnostics = {
        "reasons": list(dict.fromkeys(str(value) for value in reasons if str(value))),
        "event_counts": counts,
        "target_seconds": round(target_seconds, 3),
        "ambiguous_seconds": round(ambiguous_seconds, 3),
        "rejected_non_dialogue_seconds": round(rejected_seconds, 3),
        "target_ratio": round(target_seconds / max(1e-6, duration), 6),
        "asr_allowed": bool(target),
    }
    if separated_diagnostics is not None:
        diagnostics["separated_vocal"] = dict(separated_diagnostics)
    if event_model_version:
        diagnostics["event_model_version"] = event_model_version
    return TargetSpeechAuthority(
        status=status,
        provider=provider,
        duration_seconds=round(duration, 3),
        target_intervals=tuple(target),
        ambiguous_intervals=tuple(ambiguous),
        rejected_intervals=tuple(rejected),
        event_windows=tuple(windows),
        requires_separation=bool(
            ambiguous or any(row.requires_separation for row in target)
        ),
        diagnostics=diagnostics,
    )


def _interval_dict(row: TargetSpeechInterval) -> dict[str, Any]:
    return {
        "start_seconds": row.start_seconds,
        "end_seconds": row.end_seconds,
        "decision": row.decision,
        "confidence": row.confidence,
        "speech_score": row.speech_score,
        "music_score": row.music_score,
        "singing_score": row.singing_score,
        "reasons": list(row.reasons),
        "requires_separation": row.requires_separation,
    }


def _window_dict(row: AudioEventWindow) -> dict[str, Any]:
    return {
        "start_seconds": row.start_seconds,
        "end_seconds": row.end_seconds,
        "label": row.label.value,
        "confidence": row.confidence,
        "vad_overlap": row.vad_overlap,
        "speech_score": row.speech_score,
        "music_score": row.music_score,
        "singing_score": row.singing_score,
        "features": asdict(row.features),
    }
