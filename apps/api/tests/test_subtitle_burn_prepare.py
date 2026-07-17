"""Contracts for burn-ready SRT preparation (wrap + split long cues)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from src.tts_pipeline.services.subtitle_builder import (
    SubtitleBuilder,
    build_srt,
    prepare_srt_file_for_burn,
    prepare_subtitle_drafts_for_burn,
    wrap_subtitle_lines,
)
from src.tts_pipeline.types import SubtitleDraftSegment, TranslationInputSegment


class SubtitleBurnPrepareTests(unittest.TestCase):
    def test_wrap_subtitle_lines_respects_max_chars(self) -> None:
        text = "Đây là món giảm mỡ kiểu Trung ăn đã mà nhẹ bụng"
        wrapped = wrap_subtitle_lines(text, max_chars=18)
        lines = wrapped.split("\n")
        self.assertGreaterEqual(len(lines), 2)
        self.assertTrue(all(len(line) <= 22 for line in lines))  # small slack for word boundaries

    def test_long_single_cue_splits_into_timed_phrases(self) -> None:
        draft = SubtitleDraftSegment(
            translation_segment_id=uuid4(),
            segment_index=0,
            start_ms=0,
            end_ms=29_000,
            text=(
                "Đây là món giảm mỡ kiểu Trung, ăn đã mà nhẹ bụng. "
                "Cắt dưa leo lát, chần với mộc nhĩ. "
                "Xịt dầu, đảo tơi trứng rồi để riêng."
            ),
            layout_mode="bottom_safe_area",
            track_kind="vietnamese_hard_burn",
            review_flags=[],
            metadata={},
        )
        prepared = prepare_subtitle_drafts_for_burn([draft])
        self.assertGreater(len(prepared), 1)
        self.assertEqual(prepared[0].start_ms, 0)
        self.assertEqual(prepared[-1].end_ms, 29_000)
        srt = build_srt([draft])
        self.assertGreater(srt.count("-->"), 1)
        for block in srt.strip().split("\n\n"):
            lines = block.splitlines()
            body_lines = lines[2:]
            self.assertTrue(body_lines)
            self.assertLessEqual(max(len(line) for line in body_lines), 22)

    def test_prepare_srt_file_for_burn_rewrites_wall_cue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "wall.srt"
            src.write_text(
                "1\n00:00:00,000 --> 00:00:29,000\n"
                "Đây là món giảm mỡ kiểu Trung, ăn đã mà nhẹ bụng. "
                "Cắt dưa leo lát, chần với mộc nhĩ, cà rốt cho vừa chín.\n",
                encoding="utf-8",
            )
            out_path, warnings = prepare_srt_file_for_burn(str(src))
            self.assertTrue(Path(out_path).exists())
            body = Path(out_path).read_text(encoding="utf-8")
            self.assertGreater(body.count("-->"), 1)
            self.assertIn("subtitle_cue_split_for_burn", warnings)

    def test_short_cue_unchanged_count(self) -> None:
        translation_id = uuid4()
        segment = TranslationInputSegment(
            translation_segment_id=translation_id,
            transcript_segment_id=uuid4(),
            source_video_id=uuid4(),
            segment_index=0,
            start_ms=1200,
            end_ms=3400,
            translated_text="Xin chào mọi người",
            duration_budget_ms=2200,
            translation_version=1,
            translation_preset="natural_viral",
            quality_flags=[],
        )
        drafts = SubtitleBuilder().build([segment], [])
        prepared = prepare_subtitle_drafts_for_burn(drafts)
        self.assertEqual(len(prepared), 1)


if __name__ == "__main__":
    unittest.main()
