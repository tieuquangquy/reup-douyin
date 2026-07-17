"""Bounded parallel translation in TranslationDraftBuilder."""

from __future__ import annotations

import threading
import time
import unittest
from dataclasses import dataclass

from src.audio_pipeline.services.translation_draft_builder import TranslationDraftBuilder
from src.audio_pipeline.types import TranscriptDraftSegment, TranslationDraftSegment, TranslationPreset


@dataclass
class _SlowProvider:
    delay_seconds: float = 0.12
    max_inflight: int = 0
    _lock: threading.Lock = threading.Lock()
    _inflight: int = 0

    def translate(
        self,
        source_text: str,
        *,
        preset: TranslationPreset,
        duration_budget_seconds: float | None = None,
        source_confidence: float | None = None,
    ) -> TranslationDraftSegment:
        with self._lock:
            self._inflight += 1
            self.max_inflight = max(self.max_inflight, self._inflight)
        try:
            time.sleep(self.delay_seconds)
            return TranslationDraftSegment(
                segment_index=-1,
                translated_text=f"VI:{source_text}",
                translation_preset=preset,
                duration_budget_seconds=duration_budget_seconds,
                estimated_tts_duration_seconds=duration_budget_seconds,
                quality_flags=["provider_test"],
                metadata={"source_text": source_text},
            )
        finally:
            with self._lock:
                self._inflight -= 1


def _beats(n: int) -> list[TranscriptDraftSegment]:
    return [
        TranscriptDraftSegment(
            segment_index=i,
            start_seconds=float(i),
            end_seconds=float(i) + 1.0,
            source_text=f"源{i}",
            normalized_source_text=f"源{i}",
            confidence=0.9,
            speaker_label=None,
            difficulty_flags=[],
            metadata={},
        )
        for i in range(n)
    ]


class TranslationParallelTests(unittest.TestCase):
    def test_parallel_build_preserves_order_and_uses_concurrency(self) -> None:
        provider = _SlowProvider(delay_seconds=0.15)
        builder = TranslationDraftBuilder(provider)
        progress: list[tuple[int, int]] = []

        started = time.monotonic()
        rows = builder.build(
            _beats(4),
            preset=TranslationPreset.LITERAL_SAFE,
            max_concurrency=4,
            on_progress=lambda done, total, **_: progress.append((done, total)),
        )
        elapsed = time.monotonic() - started

        self.assertEqual([row.segment_index for row in rows], [0, 1, 2, 3])
        self.assertEqual([row.translated_text for row in rows], ["VI:源0", "VI:源1", "VI:源2", "VI:源3"])
        # Sequential would need ~0.60s; bounded parallel of 4 should finish near one delay.
        self.assertLess(elapsed, 0.45, f"expected parallel wall time, got {elapsed:.3f}s")
        self.assertGreaterEqual(provider.max_inflight, 2)
        self.assertLessEqual(provider.max_inflight, 4)
        self.assertEqual(progress[-1], (4, 4))

    def test_concurrency_one_matches_sequential_wall_time(self) -> None:
        provider = _SlowProvider(delay_seconds=0.08)
        builder = TranslationDraftBuilder(provider)
        started = time.monotonic()
        rows = builder.build(_beats(3), preset=TranslationPreset.LITERAL_SAFE, max_concurrency=1)
        elapsed = time.monotonic() - started
        self.assertEqual([row.segment_index for row in rows], [0, 1, 2])
        self.assertGreaterEqual(elapsed, 0.20)
        self.assertEqual(provider.max_inflight, 1)


if __name__ == "__main__":
    unittest.main()
