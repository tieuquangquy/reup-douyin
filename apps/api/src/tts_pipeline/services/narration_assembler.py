from __future__ import annotations

import wave
from io import BytesIO

import numpy as np

from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.types import SynthesizedSegment


AUTHORITY_SAMPLE_RATE = 48_000
AUTHORITY_CHANNELS = 1
AUTHORITY_SAMPLE_WIDTH = 2


def normalize_wav_bytes(content: bytes) -> tuple[bytes, float]:
    pcm = _normalize_wav_pcm(content)
    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(AUTHORITY_CHANNELS)
        handle.setsampwidth(AUTHORITY_SAMPLE_WIDTH)
        handle.setframerate(AUTHORITY_SAMPLE_RATE)
        handle.writeframes(pcm.astype("<i2").tobytes())
    return output.getvalue(), len(pcm) / float(AUTHORITY_SAMPLE_RATE)


class NarrationAssembler:
    def assemble(
        self,
        segments: list[SynthesizedSegment],
        *,
        timeline_duration_seconds: float,
    ) -> tuple[bytes, dict]:
        duration = float(timeline_duration_seconds)
        if duration <= 0:
            raise TtsPipelineError(
                TtsPipelineErrorCode.NARRATION_ASSEMBLY_FAILED,
                "Narration timeline duration must be positive",
            )
        total_frames = max(1, int(round(duration * AUTHORITY_SAMPLE_RATE)))
        timeline = np.zeros(total_frames, dtype=np.int32)
        timing_map: list[dict] = []
        previous_end_ms = 0
        for segment in sorted(
            segments,
            key=lambda item: (
                item.input_segment.start_ms,
                item.input_segment.segment_index,
            ),
        ):
            source = segment.input_segment
            if source.start_ms < previous_end_ms or source.end_ms <= source.start_ms:
                raise TtsPipelineError(
                    TtsPipelineErrorCode.NARRATION_ASSEMBLY_FAILED,
                    "TTS segments overlap or have invalid timeline timing",
                )
            pcm = _normalize_wav_pcm(segment.audio_bytes)
            start_frame = int(round(source.start_ms * AUTHORITY_SAMPLE_RATE / 1000.0))
            slot_end_frame = int(round(source.end_ms * AUTHORITY_SAMPLE_RATE / 1000.0))
            if start_frame < 0 or slot_end_frame > total_frames:
                raise TtsPipelineError(
                    TtsPipelineErrorCode.NARRATION_ASSEMBLY_FAILED,
                    "TTS segment falls outside the source video timeline",
                )
            max_clip_frames = max(0, slot_end_frame - start_frame)
            tolerance = int(round(AUTHORITY_SAMPLE_RATE * 0.015))
            if len(pcm) > max_clip_frames + tolerance:
                raise TtsPipelineError(
                    TtsPipelineErrorCode.TIMING_FIT_BLOCKED,
                    "Fitted TTS clip still exceeds its source timeline slot",
                )
            if len(pcm) > max_clip_frames:
                pcm = pcm[:max_clip_frames]
            end_frame = start_frame + len(pcm)
            mixed = timeline[start_frame:end_frame] + pcm.astype(np.int32)
            timeline[start_frame:end_frame] = np.clip(mixed, -32768, 32767)
            timing_map.append(
                {
                    "translation_segment_id": str(source.translation_segment_id),
                    "segment_index": source.segment_index,
                    "source_start_seconds": round(source.start_ms / 1000.0, 6),
                    "source_end_seconds": round(source.end_ms / 1000.0, 6),
                    "output_start_seconds": round(start_frame / AUTHORITY_SAMPLE_RATE, 6),
                    "output_end_seconds": round(end_frame / AUTHORITY_SAMPLE_RATE, 6),
                    "fit_status": str(segment.fit_status),
                    "fit_ratio": round(float(segment.fit_ratio), 6),
                    "timing_quality_band": str(
                        segment.provider_metadata.get("timing_quality_band")
                        or segment.provider_metadata.get("speech_budget", {}).get(
                            "timing_quality_band"
                        )
                        or "no_speed_adjustment"
                    ),
                }
            )
            previous_end_ms = source.end_ms
        pcm16 = timeline.astype("<i2")
        output = BytesIO()
        with wave.open(output, "wb") as handle:
            handle.setnchannels(AUTHORITY_CHANNELS)
            handle.setsampwidth(AUTHORITY_SAMPLE_WIDTH)
            handle.setframerate(AUTHORITY_SAMPLE_RATE)
            handle.writeframes(pcm16.tobytes())
        return output.getvalue(), {
            "timing_map": timing_map,
            "assembly_strategy": "full_duration_timeline_mix",
            "duration_seconds": round(total_frames / AUTHORITY_SAMPLE_RATE, 6),
            "audio_format": {
                "codec": "pcm_s16le",
                "sample_rate_hz": AUTHORITY_SAMPLE_RATE,
                "channels": AUTHORITY_CHANNELS,
                "sample_width_bytes": AUTHORITY_SAMPLE_WIDTH,
            },
        }


def _normalize_wav_pcm(content: bytes) -> np.ndarray:
    try:
        with wave.open(BytesIO(content), "rb") as handle:
            if handle.getcomptype() != "NONE" or handle.getsampwidth() != 2:
                raise TtsPipelineError(
                    TtsPipelineErrorCode.NARRATION_ASSEMBLY_FAILED,
                    "TTS WAV must be uncompressed 16-bit PCM",
                )
            channels = int(handle.getnchannels())
            sample_rate = int(handle.getframerate())
            raw = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise TtsPipelineError(
            TtsPipelineErrorCode.NARRATION_ASSEMBLY_FAILED,
            "TTS clip is not a valid WAV file",
        ) from exc
    pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels < 1 or sample_rate < 1:
        raise TtsPipelineError(
            TtsPipelineErrorCode.NARRATION_ASSEMBLY_FAILED,
            "TTS WAV has invalid channel or sample-rate metadata",
        )
    if channels > 1:
        usable = len(pcm) - (len(pcm) % channels)
        pcm = pcm[:usable].reshape(-1, channels).mean(axis=1)
    if sample_rate != AUTHORITY_SAMPLE_RATE and len(pcm) > 1:
        output_length = max(1, int(round(len(pcm) * AUTHORITY_SAMPLE_RATE / sample_rate)))
        source_x = np.linspace(0.0, 1.0, num=len(pcm), endpoint=False)
        output_x = np.linspace(0.0, 1.0, num=output_length, endpoint=False)
        pcm = np.interp(output_x, source_x, pcm)
    return np.clip(np.rint(pcm), -32768, 32767).astype(np.int16)
