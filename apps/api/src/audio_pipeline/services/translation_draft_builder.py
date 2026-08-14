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
from src.audio_pipeline.translation_v3 import (
    DEFAULT_TRANSLATION_V3_POLICY,
    TranslationV3Policy,
    build_context_blocks,
    draft_from_checkpoint,
)

logger = logging.getLogger(__name__)

DEFAULT_TRANSLATION_MAX_CONCURRENCY = 4

ProgressCallback = Callable[..., None]
CheckpointCallback = Callable[[str, list[TranslationDraftSegment], int, int], None]


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
        batch_size: int = 8,
        policy: TranslationV3Policy = DEFAULT_TRANSLATION_V3_POLICY,
        glossary: dict[str, str] | None = None,
        translation_memory: dict[int, str] | None = None,
        checkpoint: dict[str, list[dict]] | None = None,
        on_checkpoint: CheckpointCallback | None = None,
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

            context_method = getattr(self.provider, "translate_context_batch", None)
            if callable(context_method):
                blocks = build_context_blocks(transcript_segments, policy=policy)
                position_by_segment = {
                    segment.segment_index: position
                    for position, segment in enumerate(transcript_segments)
                }
                checkpoint_rows = checkpoint or {}
                for block_number, block in enumerate(blocks, start=1):
                    batch_started = time.monotonic()
                    restored_payloads = checkpoint_rows.get(block.block_id) or []
                    restored = [
                        draft_from_checkpoint(payload)
                        for payload in restored_payloads
                        if isinstance(payload, dict)
                    ]
                    expected_indices = [row.segment_index for row in block.core_segments]
                    if sorted(row.segment_index for row in restored) == sorted(expected_indices):
                        block_rows = restored
                        checkpoint_status = "checkpoint_hit"
                    else:
                        request_payload = block.request_payload(
                            glossary=glossary,
                            translation_memory=translation_memory,
                            policy=policy,
                        )
                        try:
                            block_rows = list(
                                context_method(
                                    request_payload,
                                    preset=preset,
                                    policy=policy,
                                )
                            )
                        except RuntimeError as exc:
                            if "translation_context_output_" not in str(exc):
                                raise
                            logger.warning(
                                "translation_context_parse_failed_fallback_per_beat",
                                extra={"block_id": block.block_id, "error": str(exc)},
                            )
                            block_rows = [
                                self.provider.translate(
                                    segment.normalized_source_text,
                                    preset=preset,
                                    duration_budget_seconds=segment.duration_seconds,
                                    source_confidence=segment.confidence,
                                )
                                for segment in block.core_segments
                            ]
                        checkpoint_status = "translated"
                        if on_checkpoint is not None:
                            on_checkpoint(block.block_id, block_rows, block_number, len(blocks))

                    if len(block_rows) != len(block.core_segments):
                        raise RuntimeError(
                            "translation_context_result_count_mismatch:"
                            f"block={block.block_id} expected={len(block.core_segments)} actual={len(block_rows)}"
                        )
                    rows_by_index = {row.segment_index: row for row in block_rows}
                    # Per-beat fallback providers may return segment_index=0; bind by order in that case.
                    if set(rows_by_index) != set(expected_indices):
                        rows_by_index = {
                            segment.segment_index: replace(row, segment_index=segment.segment_index)
                            for segment, row in zip(block.core_segments, block_rows, strict=True)
                        }
                    for segment in block.core_segments:
                        row = rows_by_index[segment.segment_index]
                        flags = list(
                            dict.fromkeys([*row.quality_flags, *self._review_flags(segment, row)])
                        )
                        position = position_by_segment[segment.segment_index]
                        translations[position] = replace(
                            row,
                            segment_index=segment.segment_index,
                            quality_flags=flags,
                            metadata={
                                **row.metadata,
                                "source_segment_index": segment.segment_index,
                                "translation_checkpoint_status": checkpoint_status,
                                "translation_block_elapsed_ms": round(
                                    (time.monotonic() - batch_started) * 1000.0,
                                    1,
                                ),
                            },
                        )
                        completed += 1
                        if on_progress is not None:
                            on_progress(
                                completed,
                                total,
                                phase=f"translate_block|{block_number}|{len(blocks)}",
                                block_id=block.block_id,
                                block_index=block_number,
                                block_total=len(blocks),
                                elapsed_ms=(time.monotonic() - batch_started) * 1000.0,
                                segment_index=segment.segment_index,
                            )
                return [row for row in translations if row is not None]

            batch_method = getattr(self.provider, "translate_batch", None)
            resolved_batch_size = max(1, min(16, int(batch_size or 1)))
            if callable(batch_method) and total > 1 and resolved_batch_size > 1:
                for offset in range(0, total, resolved_batch_size):
                    chunk = transcript_segments[offset : offset + resolved_batch_size]
                    requests = [
                        {
                            "id": str(position),
                            "source_text": segment.normalized_source_text,
                            "duration_budget_seconds": segment.duration_seconds,
                            "source_confidence": segment.confidence,
                        }
                        for position, segment in enumerate(chunk, start=offset)
                    ]
                    batch_started = time.monotonic()
                    try:
                        batch_rows = list(batch_method(requests, preset=preset))
                    except RuntimeError as exc:
                        if "translation_batch_output_" not in str(exc):
                            raise
                        logger.warning(
                            "translation_batch_parse_failed_fallback_per_beat",
                            extra={
                                "offset": offset,
                                "batch_size": len(chunk),
                                "error": str(exc),
                            },
                        )
                        batch_rows = [
                            self.provider.translate(
                                segment.normalized_source_text,
                                preset=preset,
                                duration_budget_seconds=segment.duration_seconds,
                                source_confidence=segment.confidence,
                            )
                            for segment in chunk
                        ]
                    if len(batch_rows) != len(chunk):
                        raise RuntimeError(
                            "translation_batch_result_count_mismatch:"
                            f"expected={len(chunk)} actual={len(batch_rows)}"
                        )
                    for position, (segment, translated) in enumerate(
                        zip(chunk, batch_rows, strict=True), start=offset
                    ):
                        flags = list(
                            dict.fromkeys(
                                [
                                    *translated.quality_flags,
                                    *self._review_flags(segment, translated),
                                ]
                            )
                        )
                        translations[position] = replace(
                            translated,
                            segment_index=segment.segment_index,
                            quality_flags=flags,
                            metadata={
                                **translated.metadata,
                                "source_segment_index": segment.segment_index,
                            },
                        )
                        completed += 1
                        if on_progress is not None:
                            on_progress(
                                completed,
                                total,
                                elapsed_ms=(time.monotonic() - batch_started) * 1000.0,
                                segment_index=segment.segment_index,
                            )
                return [row for row in translations if row is not None]

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
