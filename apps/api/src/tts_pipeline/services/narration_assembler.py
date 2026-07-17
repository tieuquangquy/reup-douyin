from __future__ import annotations

import wave
from io import BytesIO

from src.tts_pipeline.types import SynthesizedSegment


class NarrationAssembler:
    def assemble(self, segments: list[SynthesizedSegment]) -> tuple[bytes, dict]:
        if not segments:
            return b"", {"segments": []}
        # Phase 1 concatenates generated WAV clips in timeline order. Render step will use
        # timing_map for exact placement; no destructive time-stretch is done here.
        chunks: list[bytes] = []
        timing_map: list[dict] = []
        cursor_seconds = 0.0
        for segment in sorted(segments, key=lambda item: item.input_segment.start_ms):
            pcm, params = _read_wav_pcm(segment.audio_bytes)
            if not chunks:
                first_params = params
            chunks.append(pcm)
            timing_map.append(
                {
                    "translation_segment_id": str(segment.input_segment.translation_segment_id),
                    "source_start_seconds": segment.input_segment.start_ms / 1000,
                    "source_end_seconds": segment.input_segment.end_ms / 1000,
                    "joined_start_seconds": round(cursor_seconds, 3),
                    "joined_end_seconds": round(cursor_seconds + segment.duration_seconds, 3),
                    "fit_status": segment.fit_status,
                }
            )
            cursor_seconds += segment.duration_seconds
        output = BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setparams(first_params)
            for chunk in chunks:
                wav.writeframes(chunk)
        return output.getvalue(), {"timing_map": timing_map, "assembly_strategy": "concat_with_timing_map"}


def _read_wav_pcm(content: bytes):
    with wave.open(BytesIO(content), "rb") as wav:
        params = wav.getparams()
        frames = wav.readframes(wav.getnframes())
    return frames, params
