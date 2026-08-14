import unittest
from uuid import uuid4

from src.tts_pipeline.services.gemini_whole_video import (
    boundary_pause_tag,
    build_gemini_narration_blocks,
    resolve_gemini_synthesis_strategy,
    select_whole_video_candidates,
)
from src.tts_pipeline.types import TranslationInputSegment


def _segment(index: int, start_ms: int, end_ms: int, text: str, *candidates: str):
    return TranslationInputSegment(
        translation_segment_id=uuid4(),
        transcript_segment_id=uuid4(),
        source_video_id=uuid4(),
        segment_index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        translated_text=text,
        duration_budget_ms=end_ms - start_ms,
        translation_version=1,
        translation_preset="natural_viral",
        candidate_texts=tuple(candidates),
    )


class GeminiWholeVideoPlanningTests(unittest.TestCase):
    def test_strategy_is_provider_scoped_and_requires_single_voice(self) -> None:
        self.assertEqual(
            resolve_gemini_synthesis_strategy(
                provider="google_gemini",
                expressive_options={
                    "single_voice_mode": "required",
                    "synthesis_strategy": "whole_video",
                },
            ),
            "whole_video",
        )
        self.assertEqual(
            resolve_gemini_synthesis_strategy(
                provider="google",
                expressive_options={"single_voice_mode": "required"},
            ),
            "segment",
        )
        self.assertEqual(
            resolve_gemini_synthesis_strategy(
                provider="google_gemini",
                expressive_options={"single_voice_mode": "off"},
            ),
            "segment",
        )

    def test_short_form_video_becomes_one_provider_block(self) -> None:
        rows = [
            _segment(0, 0, 4_000, "Xin chào"),
            _segment(1, 4_200, 9_000, "Mời bạn theo dõi"),
            _segment(2, 9_200, 14_000, "Cảm ơn bạn"),
        ]
        blocks = build_gemini_narration_blocks(
            rows,
            strategy="whole_video",
            max_whole_video_seconds=180,
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual(len(blocks[0].segments), 3)
        self.assertEqual(blocks[0].start_ms, 0)
        self.assertEqual(blocks[0].end_ms, 14_000)

    def test_long_video_falls_back_to_bounded_blocks(self) -> None:
        rows = [
            _segment(index, index * 20_000, index * 20_000 + 18_000, f"Câu {index}")
            for index in range(5)
        ]
        blocks = build_gemini_narration_blocks(
            rows,
            strategy="whole_video",
            max_whole_video_seconds=60,
            max_block_seconds=45,
        )
        self.assertGreater(len(blocks), 1)
        self.assertLessEqual(max(block.duration_seconds for block in blocks), 45.0)

    def test_dense_primary_uses_only_an_approved_compact_candidate(self) -> None:
        primary = "Xin chào bạn, hôm nay chúng ta sẽ cùng nhau xem toàn bộ nội dung hướng dẫn rất chi tiết này."
        compact = "Xin chào bạn, cùng xem hướng dẫn này."
        row = _segment(0, 0, 2_000, primary, primary, compact)
        selected = select_whole_video_candidates(
            [row],
            units_per_second=4.0,
            compact_trigger_ratio=0.80,
        )
        self.assertEqual(selected[0].translated_text, compact)
        self.assertIn(
            "gemini_whole_video_compact_preflight",
            selected[0].repair_actions,
        )

    def test_pause_tags_are_bounded(self) -> None:
        self.assertEqual(boundary_pause_tag(50), "")
        self.assertEqual(boundary_pause_tag(200), "[short pause]")
        self.assertEqual(boundary_pause_tag(800), "[long pause]")


if __name__ == "__main__":
    unittest.main()
