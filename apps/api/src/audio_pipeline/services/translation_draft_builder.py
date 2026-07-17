from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from dataclasses import replace

from src.audio_pipeline.providers import TranslationProvider
from src.audio_pipeline.types import (
    TranscriptDraftSegment,
    TranslationDraftSegment,
    TranslationPreset,
)

logger = logging.getLogger(__name__)

DEFAULT_TRANSLATION_MAX_CONCURRENCY = 4

ProgressCallback = Callable[..., None]


class TranslationDraftBuilder:
    def __init__(self, provider: TranslationProvider):
        self.provider = provider

    def build(
        self,
        transcript_segments: list[TranscriptDraftSegment],
        *,
        preset: TranslationPreset,
        user_prompt: str | None = None,
        max_concurrency: int = DEFAULT_TRANSLATION_MAX_CONCURRENCY,
        on_progress: ProgressCallback | None = None,
    ) -> list[TranslationDraftSegment]:
        """
        Build VI drafts. ``user_prompt`` (usually from workspace DB) overrides
        file/env/builtin system prompts on DurationConstrainedTranslationProvider.

        Beats are translated with a bounded thread pool (default 4) to cut wall time
        while preserving segment_index order in the returned list.
        """
        previous_prompt = getattr(self.provider, "user_prompt", None)
        if user_prompt is not None and hasattr(self.provider, "user_prompt"):
            self.provider.user_prompt = user_prompt

        workers = max(1, int(max_concurrency or 1))
        total = len(transcript_segments)
        translations: list[TranslationDraftSegment | None] = [None] * total
        completed = 0
        build_started = time.monotonic()

        try:
            if total == 0:
                return []

            def _translate_one(position: int, segment: TranscriptDraftSegment) -> tuple[int, TranslationDraftSegment, float]:
                started = time.monotonic()
                translated = self.provider.translate(
                    segment.normalized_source_text,
                    preset=preset,
                    duration_budget_seconds=segment.duration_seconds,
                    source_confidence=segment.confidence,
                )
                flags = list(dict.fromkeys([*translated.quality_flags, *self._review_flags(segment, translated)]))
                row = replace(
                    translated,
                    segment_index=segment.segment_index,
                    quality_flags=flags,
                    metadata={
                        **translated.metadata,
                        "source_segment_index": segment.segment_index,
                    },
                )
                elapsed_ms = (time.monotonic() - started) * 1000.0
                return position, row, elapsed_ms

            with ThreadPoolExecutor(max_workers=min(workers, total), thread_name_prefix="translate-beat") as pool:
                futures = {
                    pool.submit(_translate_one, index, segment): index
                    for index, segment in enumerate(transcript_segments)
                }
                for future in as_completed(futures):
                    position, row, elapsed_ms = future.result()
                    translations[position] = row
                    completed += 1
                    logger.info(
                        "translation_beat_completed",
                        extra={
                            "segment_index": row.segment_index,
                            "completed": completed,
                            "total": total,
                            "elapsed_ms": round(elapsed_ms, 1),
                            "max_concurrency": workers,
                        },
                    )
                    if on_progress is not None:
                        on_progress(
                            completed,
                            total,
                            elapsed_ms=elapsed_ms,
                            segment_index=row.segment_index,
                        )
        finally:
            if hasattr(self.provider, "user_prompt"):
                self.provider.user_prompt = previous_prompt

        total_ms = (time.monotonic() - build_started) * 1000.0
        logger.info(
            "translation_draft_build_completed",
            extra={
                "total": total,
                "elapsed_ms": round(total_ms, 1),
                "max_concurrency": workers,
            },
        )
        return [row for row in translations if row is not None]

    def _review_flags(
        self,
        segment: TranscriptDraftSegment,
        translation: TranslationDraftSegment,
    ) -> list[str]:
        flags: list[str] = []
        if "low_confidence" in segment.difficulty_flags:
            flags.append("low_confidence_source")
        if segment.duration_seconds < 0.8:
            flags.append("awkward_short_segment")
        if (
            translation.estimated_tts_duration_seconds is not None
            and translation.estimated_tts_duration_seconds > segment.duration_seconds * 1.2
        ):
            flags.append("translation_too_long_for_slot")
        return flags
