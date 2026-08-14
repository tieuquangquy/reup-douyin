"""Benchmark the provider-free Translation Draft -> TTS handoff.

This intentionally performs no network or TTS-provider calls. It measures the
normalizer, candidate ranking, duration planning and preflight manifest build.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from uuid import NAMESPACE_URL, uuid5

from src.audio_pipeline.speech_budget import DEFAULT_VI_UNITS_PER_SECOND
from src.tts_pipeline.services.input_preflight import build_tts_input_preflight
from src.tts_pipeline.types import TranslationInputSegment, VoiceConfig


_CORPUS = (
    "Ngày 12/08/2026 lúc 8:30, giá 25.000đ, giảm 10%.",
    "Dùng 15 ml sốt cho 200 g cơm.",
    "RTX-4090 chạy nhanh hơn từ 10–15 lần.",
    "Gửi email tới ops@example.com và xem https://example.com/faq.",
    "Nhiệt độ từ -5 đến 12 độ.",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--segments", type=int, default=100)
    args = parser.parse_args()
    iterations = max(1, int(args.iterations))
    segment_count = max(1, int(args.segments))
    source_id = uuid5(NAMESPACE_URL, "reup-douyin:tts-handoff-benchmark")
    segments = [_segment(source_id, index) for index in range(segment_count)]
    elapsed_ms: list[float] = []
    last_manifest: dict = {}
    for _ in range(iterations):
        started = time.perf_counter()
        last_manifest = build_tts_input_preflight(
            segments,
            source_video_id=source_id,
            timeline_duration_ms=segment_count * 3000,
            translation_input_sha256="benchmark-input",
            translation_authority_sha256="benchmark-authority",
            voice_config=VoiceConfig(),
            voice_authority={"profile_id": "benchmark"},
            units_per_second=DEFAULT_VI_UNITS_PER_SECOND,
            pronunciation_glossary={"RTX": "rờ tê ích"},
        )
        elapsed_ms.append((time.perf_counter() - started) * 1000.0)
    ordered = sorted(elapsed_ms)
    result = {
        "schema_version": "tts-handoff-benchmark-v1",
        "provider_calls": 0,
        "iterations": iterations,
        "segments_per_iteration": segment_count,
        "median_ms": round(statistics.median(ordered), 4),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 4),
        "segments_per_second": round(
            (iterations * segment_count) / max(0.000001, sum(elapsed_ms) / 1000.0),
            2,
        ),
        "last_status_counts": dict(last_manifest.get("status_counts") or {}),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _segment(source_id, index: int) -> TranslationInputSegment:
    start_ms = index * 3000
    return TranslationInputSegment(
        translation_segment_id=uuid5(source_id, f"translation:{index}"),
        transcript_segment_id=uuid5(source_id, f"transcript:{index}"),
        source_video_id=source_id,
        segment_index=index,
        start_ms=start_ms,
        end_ms=start_ms + 3000,
        translated_text=_CORPUS[index % len(_CORPUS)],
        duration_budget_ms=3000,
        translation_version=1,
        translation_preset="benchmark",
        translation_status="APPROVED",
    )


if __name__ == "__main__":
    raise SystemExit(main())
