"""Regression coverage for food-texture false positives in local OCR proposals."""

from __future__ import annotations

import unittest

import numpy as np

from src.media_pipeline.frame_sampling.local_text_verifier import (
    EventDrivenTextVerifier,
    LocalRecognition,
    filter_verified_text_lines,
    group_text_lines,
)
from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox


class _BottomSubtitleRecognizer:
    """Deterministic recognizer double: only wide subtitle crops contain text."""

    def recognize(self, _crop: np.ndarray) -> LocalRecognition:
        height, width = _crop.shape[:2]
        if width >= max(80, height * 4):
            return LocalRecognition(
                text="测试字幕",
                confidence=0.94,
                valid_char_ratio=1.0,
            )
        return LocalRecognition(text="", confidence=0.02, valid_char_ratio=0.0)


class _CountingRecognizer:
    def __init__(self) -> None:
        self.calls = 0

    def recognize(self, _crop: np.ndarray) -> LocalRecognition:
        self.calls += 1
        return LocalRecognition(text="稳定字幕", confidence=0.95, valid_char_ratio=1.0)


class _UncertainCountingRecognizer(_CountingRecognizer):
    def recognize(self, _crop: np.ndarray) -> LocalRecognition:
        self.calls += 1
        return LocalRecognition(text="疑似", confidence=0.45, valid_char_ratio=1.0)


class _BatchCountingRecognizer(_CountingRecognizer):
    def __init__(self) -> None:
        super().__init__()
        self.batch_calls = 0

    def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
        self.batch_calls += 1
        self.calls += len(crops)
        return [
            LocalRecognition(text="批量字幕", confidence=0.95, valid_char_ratio=1.0)
            for _crop in crops
        ]


class LocalTextVerifierRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.recognizer = _BottomSubtitleRecognizer()

    def _verify(self, boxes: list[TimedBox]) -> list[TimedBox]:
        return filter_verified_text_lines(
            self.frame,
            boxes,
            recognizer=self.recognizer,
            mode="hardsub",
        )

    def test_f361_keeps_subtitle_and_rejects_egg_yolk(self) -> None:
        verified = self._verify(
            [
                TimedBox(0.42, 0.19, 0.06, 0.05),  # egg-yolk highlight
                TimedBox(0.34, 0.90, 0.34, 0.055),  # visible subtitle
            ]
        )

        self.assertEqual(len(verified), 1)
        self.assertGreater(verified[0].y, 0.80)
        self.assertEqual(verified[0].text, "测试字幕")

    def test_f512_food_only_frame_emits_no_verified_lines(self) -> None:
        food_boxes = [
            TimedBox(0.44, 0.19, 0.25, 0.58),
            TimedBox(0.61, 0.23, 0.17, 0.16),
            TimedBox(0.71, 0.48, 0.14, 0.17),
            TimedBox(0.31, 0.70, 0.05, 0.07),
            TimedBox(0.36, 0.40, 0.06, 0.08),
        ]

        self.assertEqual(self._verify(food_boxes), [])

    def test_f671_keeps_bottom_subtitle_and_rejects_food_strands(self) -> None:
        verified = self._verify(
            [
                TimedBox(0.23, 0.64, 0.14, 0.17),
                TimedBox(0.37, 0.48, 0.24, 0.29),
                TimedBox(0.46, 0.52, 0.02, 0.03),
                TimedBox(0.35, 0.90, 0.32, 0.055),
            ]
        )

        self.assertEqual(len(verified), 1)
        self.assertGreater(verified[0].y, 0.80)

    def test_f1533_preserves_single_visible_subtitle(self) -> None:
        verified = self._verify([TimedBox(0.40, 0.90, 0.25, 0.055)])

        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0].text, "测试字幕")

    def test_scattered_food_fragments_do_not_form_a_text_line(self) -> None:
        lines = group_text_lines(
            [
                TimedBox(0.10, 0.84, 0.02, 0.02),
                TimedBox(0.40, 0.88, 0.02, 0.02),
                TimedBox(0.76, 0.82, 0.03, 0.02),
            ],
            mode="hardsub",
        )

        self.assertEqual(lines, [])

    def test_small_isolated_food_texture_is_not_a_title_line(self) -> None:
        lines = group_text_lines(
            [TimedBox(0.42, 0.21, 0.047, 0.039)],
            mode="title",
        )

        self.assertEqual(lines, [])

    def test_narrow_title_rows_are_kept_when_they_form_a_vertical_stack(self) -> None:
        lines = group_text_lines(
            [
                TimedBox(0.14, 0.27, 0.020, 0.035),  # one-character ingredient
                TimedBox(0.09, 0.35, 0.129, 0.031),
                TimedBox(0.09, 0.42, 0.120, 0.024),
                TimedBox(0.12, 0.49, 0.055, 0.028),  # short ingredient
            ],
            mode="title",
        )

        self.assertEqual(len(lines), 4)

    def test_event_verifier_reuses_stable_visual_track(self) -> None:
        recognizer = _CountingRecognizer()
        verifier = EventDrivenTextVerifier(recognizer, checkpoint_frames=20)
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[148:154, 100:220] = 255
        box = TimedBox(0.30, 0.80, 0.40, 0.08)

        first = verifier.verify(frame, [box], mode="hardsub", frame_index=0)
        second = verifier.verify(frame, [box], mode="hardsub", frame_index=1)

        self.assertEqual(recognizer.calls, 1)
        self.assertEqual(first[0].decision, "verified")
        self.assertEqual(second[0].decision, "verified")
        self.assertTrue(second[0].recognition_reused)

    def test_event_verifier_invalidates_when_current_glyphs_change(self) -> None:
        recognizer = _CountingRecognizer()
        verifier = EventDrivenTextVerifier(recognizer, checkpoint_frames=20)
        first_frame = np.zeros((180, 320, 3), dtype=np.uint8)
        first_frame[148:154, 100:220] = 255
        changed_frame = np.zeros_like(first_frame)
        changed_frame[144:158, 145:175] = 255
        box = TimedBox(0.30, 0.80, 0.40, 0.08)

        verifier.verify(first_frame, [box], mode="hardsub", frame_index=0)
        changed = verifier.verify(changed_frame, [box], mode="hardsub", frame_index=1)

        self.assertEqual(recognizer.calls, 2)
        self.assertFalse(changed[0].recognition_reused)

    def test_event_verifier_refreshes_at_bounded_checkpoint(self) -> None:
        recognizer = _CountingRecognizer()
        verifier = EventDrivenTextVerifier(
            recognizer,
            checkpoint_frames=3,
            stable_checkpoint_frames=3,
        )
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[148:154, 100:220] = 255
        box = TimedBox(0.30, 0.80, 0.40, 0.08)

        for frame_index in range(4):
            verifier.verify(frame, [box], mode="hardsub", frame_index=frame_index)

        self.assertEqual(recognizer.calls, 2)

    def test_event_verifier_does_not_reuse_borderline_recognition(self) -> None:
        recognizer = _UncertainCountingRecognizer()
        verifier = EventDrivenTextVerifier(recognizer, checkpoint_frames=20)
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[148:154, 100:220] = 255
        box = TimedBox(0.30, 0.80, 0.40, 0.08)

        first = verifier.verify(frame, [box], mode="hardsub", frame_index=0)
        second = verifier.verify(frame, [box], mode="hardsub", frame_index=1)

        self.assertEqual(first[0].decision, "uncertain")
        self.assertEqual(second[0].decision, "uncertain")
        self.assertEqual(recognizer.calls, 2)
        self.assertFalse(second[0].recognition_reused)

    def test_event_verifier_batches_multiple_refreshes_on_same_frame(self) -> None:
        recognizer = _BatchCountingRecognizer()
        verifier = EventDrivenTextVerifier(recognizer)
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[132:138, 80:240] = 255
        frame[158:164, 90:230] = 255

        results = verifier.verify(
            frame,
            [
                TimedBox(0.24, 0.70, 0.52, 0.08),
                TimedBox(0.27, 0.84, 0.46, 0.08),
            ],
            mode="hardsub",
            frame_index=0,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(recognizer.batch_calls, 1)
        self.assertEqual(recognizer.calls, 2)

    def test_blank_frame_with_no_live_tracks_skips_ctc(self) -> None:
        recognizer = _CountingRecognizer()
        verifier = EventDrivenTextVerifier(recognizer)
        blank = np.zeros((180, 320, 3), dtype=np.uint8)

        results = verifier.verify(
            blank,
            [TimedBox(0.30, 0.80, 0.40, 0.08)],
            mode="hardsub",
            frame_index=0,
        )

        self.assertEqual(results, [])
        self.assertEqual(recognizer.calls, 0)
        self.assertEqual(verifier.blank_frame_skips, 1)

    def test_two_frame_confirm_backfills_first_subtitle_frame(self) -> None:
        from src.media_pipeline.frame_sampling.local_text_verifier import (
            TwoFrameConfirmationGate,
        )

        gate = TwoFrameConfirmationGate()
        box = TimedBox(0.30, 0.80, 0.40, 0.08, text="稳定字幕", confidence=0.95)

        first = gate.accept(
            frame_index=10,
            mode="hardsub",
            verified_boxes=[box],
            recognition_reused_flags=[False],
        )
        second = gate.accept(
            frame_index=11,
            mode="hardsub",
            verified_boxes=[box],
            recognition_reused_flags=[True],
        )

        self.assertEqual(first.accepted, [])
        self.assertEqual(first.pending, [box])
        self.assertEqual(second.accepted, [box])
        self.assertEqual(second.backfill_frame_index, 10)
        self.assertEqual(list(second.backfill_boxes), [box])

    def test_title_mode_skips_two_frame_hold(self) -> None:
        from src.media_pipeline.frame_sampling.local_text_verifier import (
            requires_two_frame_confirmation,
        )

        self.assertTrue(requires_two_frame_confirmation("hardsub"))
        self.assertFalse(requires_two_frame_confirmation("title"))
        self.assertFalse(requires_two_frame_confirmation("endcard"))


if __name__ == "__main__":
    unittest.main()
