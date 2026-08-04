"""Phase1 precision/recall gates: wide hardsub keep; TARE/texture drop."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from src.media_pipeline.frame_sampling.local_text_detector import (
    TextBox,
    expand_text_boxes,
    merge_collinear_text_boxes,
)
from src.media_pipeline.frame_sampling.local_text_recognizer import LocalRecognition
from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    MergedTrack,
    filter_tracks_by_local_text,
    has_solid_colored_editor_panel,
    is_plausible_text_box,
    local_text_accepts_track,
    semantic_scene_label_background_signature,
)


class BareNumericUiGateTests(unittest.TestCase):
    def test_requires_independent_grid_split_evidence(self) -> None:
        recognition = LocalRecognition("441", 0.99, 1.0)

        self.assertFalse(
            local_text_accepts_track(recognition, role="mid_label")
        )
        self.assertTrue(
            local_text_accepts_track(
                recognition,
                role="mid_label",
                allow_bare_numeric_ui=True,
            )
        )


class WideHardsubRecallTests(unittest.TestCase):
    def test_post_expand_near_full_bottom_line_is_plausible(self) -> None:
        """
        Full-width hardsub after DBNet expand often exceeds 0.92 width.

        Must still pass geometry gate (all videos) — thin bottom band only.
        """
        # Pre-expand ~80% width × ~4% height near bottom → expand ≈ ×1.2 W.
        pre = TextBox(x=0.06, y=0.86, width=0.80, height=0.04)
        post = expand_text_boxes([pre])[0]
        x0 = post.x * 1920
        y0 = post.y * 1080
        x1 = (post.x + post.width) * 1920
        y1 = (post.y + post.height) * 1080
        self.assertGreater(post.width, 0.92)
        self.assertTrue(
            is_plausible_text_box((x0, y0, x1, y1), frame_w=1920, frame_h=1080)
        )

    def test_wide_tall_midframe_slab_still_rejected(self) -> None:
        # Near-full wide + tall mid → endcard / food slab, not hardsub line.
        self.assertFalse(
            is_plausible_text_box(
                (40.0, 300.0, 1880.0, 700.0), frame_w=1920, frame_h=1080
            )
        )

    def test_bottom_fragments_merge_across_six_percent_gap(self) -> None:
        """Orange title + white body often have a gap > 4% frame width."""
        left = TextBox(x=0.05, y=0.86, width=0.25, height=0.04)
        right = TextBox(x=0.36, y=0.865, width=0.50, height=0.038)  # gap ≈ 0.06
        merged = merge_collinear_text_boxes([left, right])
        self.assertEqual(len(merged), 1)
        self.assertLessEqual(merged[0].x, left.x + 1e-6)
        self.assertGreaterEqual(
            merged[0].x + merged[0].width, right.x + right.width - 1e-6
        )

    def test_bottom_fragments_merge_across_seventeen_percent_gap(self) -> None:
        left = TextBox(x=0.03, y=0.86, width=0.50, height=0.04)
        right = TextBox(x=0.70, y=0.865, width=0.22, height=0.038)  # gap ≈ 0.17
        merged = merge_collinear_text_boxes([left, right])
        self.assertEqual(len(merged), 1)


class LocalTextPrecisionGateTests(unittest.TestCase):
    def test_accepts_cjk_mid_label(self) -> None:
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="加盐", confidence=0.85, valid_char_ratio=1.0),
                role="mid_label",
            )
        )

    def test_rejects_tare_latin_ui(self) -> None:
        self.assertFalse(
            local_text_accepts_track(
                LocalRecognition(text="TARE", confidence=0.9, valid_char_ratio=1.0),
                role="ui_chip",
            )
        )

    def test_latin_copy_requires_independent_editor_card_evidence(self) -> None:
        recognition = LocalRecognition(
            text="Dark lines appear", confidence=0.97, valid_char_ratio=1.0
        )
        self.assertFalse(
            local_text_accepts_track(recognition, role="generic")
        )
        self.assertTrue(
            local_text_accepts_track(
                recognition,
                role="generic",
                allow_latin_editor_card=True,
            )
        )

    def test_solid_colored_panel_rejects_neutral_device_surface(self) -> None:
        purple = np.full((1080, 1920, 3), 10, dtype=np.uint8)
        purple[420:560, 260:1660] = (125, 22, 145)
        neutral = np.full((1080, 1920, 3), 45, dtype=np.uint8)
        box = [320.0, 460.0, 1580.0, 520.0]
        self.assertTrue(has_solid_colored_editor_panel(purple, box))
        self.assertFalse(has_solid_colored_editor_panel(neutral, box))

    def test_filter_rescues_changing_latin_copy_on_same_colored_card(self) -> None:
        def _track(start: int, end: int, frame_index: int) -> MergedTrack:
            box = [320.0, 460.0, 1580.0, 520.0]
            frames = list(range(start, min(end + 1, start + 10)))
            return MergedTrack(
                start_frame=start,
                end_frame=end,
                box_coords=box,
                best_frame_index=frame_index,
                best_sharpness=20.0,
                centroid=(950.0, 490.0),
                hit_count=len(frames),
                hit_boxes=[tuple(box)] * len(frames),
                hit_frames=frames,
                hit_sharpness=[20.0] * len(frames),
            )

        first = _track(0, 20, 10)
        second = _track(30, 50, 40)
        first_frame = np.full((1080, 1920, 3), 10, dtype=np.uint8)
        second_frame = first_frame.copy()
        first_frame[420:560, 260:1660] = (125, 22, 145)
        second_frame[420:560, 260:1660] = (125, 22, 145)
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition(
            "Changing caption", 0.98, 1.0
        )

        kept, audit = filter_tracks_by_local_text(
            [first, second],
            frame_cache={10: first_frame, 40: second_frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )

        self.assertEqual(len(kept), 2, msg=audit)
        self.assertEqual(audit["latin_editor_card"]["rescued_tracks"], 2)

    def test_rescues_concurrent_semantic_labels_on_distinct_diagram_regions(self) -> None:
        def _track(box: list[float]) -> MergedTrack:
            frames = list(range(20))
            return MergedTrack(
                start_frame=0,
                end_frame=19,
                box_coords=box,
                best_frame_index=10,
                best_sharpness=20.0,
                centroid=((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
                hit_count=len(frames),
                hit_boxes=[tuple(box)] * len(frames),
                hit_frames=frames,
                hit_sharpness=[20.0] * len(frames),
            )

        upper_box = [450.0, 300.0, 700.0, 340.0]
        lower_box = [460.0, 650.0, 650.0, 690.0]
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[260:380, 390:760] = (30, 30, 180)
        frame[610:730, 400:710] = (30, 170, 30)
        rec = MagicMock()
        rec.recognize.side_effect = [
            LocalRecognition("Ionosphere", 0.99, 1.0),
            LocalRecognition("Earth", 0.99, 1.0),
        ]

        kept, audit = filter_tracks_by_local_text(
            [_track(upper_box), _track(lower_box)],
            frame_cache={10: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )

        self.assertEqual(len(kept), 2, msg=audit)
        semantic = audit["semantic_scene_label"]
        self.assertEqual(semantic["peer_candidates"], 2)
        self.assertEqual(semantic["rescued_tracks"], 2)
        self.assertTrue(
            semantic_scene_label_background_signature(frame, upper_box)
        )

    def test_rejects_concurrent_latin_device_copy_on_same_panel(self) -> None:
        def _track(box: list[float]) -> MergedTrack:
            frames = list(range(20))
            return MergedTrack(
                start_frame=0,
                end_frame=19,
                box_coords=box,
                best_frame_index=10,
                best_sharpness=20.0,
                centroid=((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
                hit_count=len(frames),
                hit_boxes=[tuple(box)] * len(frames),
                hit_frames=frames,
                hit_sharpness=[20.0] * len(frames),
            )

        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        rec = MagicMock()
        rec.recognize.side_effect = [
            LocalRecognition("TARE", 0.99, 1.0),
            LocalRecognition("UNIT", 0.99, 1.0),
        ]

        kept, audit = filter_tracks_by_local_text(
            [
                _track([450.0, 300.0, 650.0, 340.0]),
                _track([460.0, 650.0, 640.0, 690.0]),
            ],
            frame_cache={10: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )

        self.assertEqual(kept, [], msg=audit)
        self.assertEqual(audit["semantic_scene_label"]["rescued_tracks"], 0)

    def test_rejects_scale_digits(self) -> None:
        self.assertFalse(
            local_text_accepts_track(
                LocalRecognition(text="181", confidence=0.9, valid_char_ratio=1.0),
                role="ui_chip",
            )
        )
        self.assertFalse(
            local_text_accepts_track(
                LocalRecognition(text="0.g", confidence=0.8, valid_char_ratio=0.7),
                role="ui_chip",
            )
        )

    def test_keeps_nutrition_unit_chips(self) -> None:
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="150克", confidence=0.99, valid_char_ratio=1.0),
                role="mid_label",
            )
        )
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="31%", confidence=0.99, valid_char_ratio=1.0),
                role="mid_label",
            )
        )

    def test_dense_endcard_cell_is_not_reanchored_as_bottom_hardsub(self) -> None:
        """A compact grid label in the upper bottom band keeps its own box."""

        def _track(box: tuple[float, float, float, float]) -> MergedTrack:
            frames = list(range(10))
            return MergedTrack(
                start_frame=0,
                end_frame=9,
                box_coords=list(box),
                best_frame_index=5,
                best_sharpness=20.0,
                centroid=((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
                hit_count=len(frames),
                hit_boxes=[box] * len(frames),
                hit_frames=frames,
                hit_sharpness=[20.0] * len(frames),
            )

        target_box = (153.6, 836.0, 230.4, 869.0)
        target = _track(target_box)
        tracks = [
            target,
            _track((152.4, 887.6, 243.6, 914.0)),
            _track((120.0, 560.0, 360.0, 610.0)),
            _track((520.0, 390.0, 1400.0, 455.0)),
            _track((920.0, 180.0, 1100.0, 220.0)),
            _track((1110.0, 680.0, 1270.0, 720.0)),
            _track((1690.0, 250.0, 1890.0, 295.0)),
        ]
        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition(
            "\u9e21\u817f", 0.99, 1.0
        )

        with patch(
            "src.media_pipeline.frame_sampling.master_phase1_extractor."
            "recover_hardsub_box_from_band_ink",
            return_value=[600.0, 995.0, 1320.0, 1045.0],
        ) as recover:
            kept, audit = filter_tracks_by_local_text(
                tracks,
                frame_cache={5: frame},
                frame_w=1920,
                frame_h=1080,
                recognizer=rec,
            )

        self.assertTrue(
            any(t.box_coords == list(target_box) for t in kept), msg=audit
        )
        self.assertFalse(recover.called, msg=recover.call_args_list)
        self.assertGreaterEqual(
            audit["hardsub_recovery"]["dense_ui_grid_skips"], 1
        )

    def test_lone_compact_bottom_stub_still_uses_hardsub_recovery(self) -> None:
        """The grid guard must not disable the existing lone-stub fallback."""
        seed_box = (153.6, 836.0, 230.4, 869.0)
        frames = list(range(10))
        track = MergedTrack(
            start_frame=0,
            end_frame=9,
            box_coords=list(seed_box),
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(192.0, 852.5),
            hit_count=len(frames),
            hit_boxes=[seed_box] * len(frames),
            hit_frames=frames,
            hit_sharpness=[20.0] * len(frames),
        )
        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        for x in range(620, 1300, 30):
            frame[1000:1040, x : x + 12] = 240
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition(
            "\u5b8c\u6574\u5b57\u5e55", 0.99, 1.0
        )
        recovered_box = [600.0, 995.0, 1320.0, 1045.0]

        with patch(
            "src.media_pipeline.frame_sampling.master_phase1_extractor."
            "recover_hardsub_box_from_band_ink",
            return_value=recovered_box,
        ) as recover:
            kept, audit = filter_tracks_by_local_text(
                [track],
                frame_cache={5: frame},
                frame_w=1920,
                frame_h=1080,
                recognizer=rec,
            )

        self.assertTrue(recover.called)
        self.assertEqual(len(kept), 1, msg=audit)
        self.assertEqual(kept[0].box_coords, recovered_box)
        self.assertEqual(audit["hardsub_recovery"]["applied"], 1)

    def test_rejects_low_conf_texture_garbage(self) -> None:
        self.assertFalse(
            local_text_accepts_track(
                LocalRecognition(text="的", confidence=0.2, valid_char_ratio=0.3),
                role="mid_label",
            )
        )

    def test_keeps_high_conf_single_cjk_chip(self) -> None:
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="虾", confidence=0.85, valid_char_ratio=1.0),
                role="ui_chip",
            )
        )
        # Chili/food texture fossil: 福 at ~0.74–0.79 must not pass.
        self.assertFalse(
            local_text_accepts_track(
                LocalRecognition(text="福", confidence=0.79, valid_char_ratio=1.0),
                role="ui_chip",
            )
        )

    def test_rejects_low_conf_single_cjk_fragment(self) -> None:
        self.assertFalse(
            local_text_accepts_track(
                LocalRecognition(text="中", confidence=0.4, valid_char_ratio=1.0),
                role="mid_label",
            )
        )

    def test_filter_drops_low_hit_mid_texture_keeps_stable_label(self) -> None:
        """Texture flicker n=1–2 must not enter SSOT; stable mid labels stay."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            min_hits_for_role,
        )

        # Mid/ui loosened to 3 for short editor chips; still reject 1–2-hit flicker.
        self.assertEqual(min_hits_for_role("mid_label"), 3)
        self.assertEqual(min_hits_for_role("ui_chip"), 3)
        self.assertLessEqual(min_hits_for_role("hardsub"), 2)

        flicker = MergedTrack(
            start_frame=100,
            end_frame=103,
            box_coords=[900.0, 700.0, 1050.0, 780.0],
            best_frame_index=101,
            best_sharpness=5.0,
            centroid=(975.0, 740.0),
            hit_count=2,
        )
        stable = MergedTrack(
            start_frame=90,
            end_frame=120,
            box_coords=[200.0, 480.0, 340.0, 560.0],
            best_frame_index=100,
            best_sharpness=20.0,
            centroid=(270.0, 520.0),
            hit_count=30,
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        frame[480:560, 200:340] = 240
        frame[700:780, 900:1050] = 200
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("加盐", 0.9, 1.0)
        kept, audit = filter_tracks_by_local_text(
            [flicker, stable],
            frame_cache={100: frame, 101: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].box_coords, stable.box_coords)
        self.assertTrue(any(r.get("reason") == "low_hits" for r in audit["rows"]))

    def test_hardsub_accepts_short_cjk_line(self) -> None:
        """Short burn-in (2 CJK) must pass local-text — not require 3+ glyphs."""
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="加盐", confidence=0.70, valid_char_ratio=1.0),
                role="hardsub",
            )
        )
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="盐2g", confidence=0.80, valid_char_ratio=1.0),
                role="hardsub",
            )
        )
        # High-conf single CJK burn-in chip in hardsub band.
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="盐", confidence=0.88, valid_char_ratio=1.0),
                role="hardsub",
            )
        )

    def test_wide_hardsub_keeps_when_ocr_blank_but_ink_strong(self) -> None:
        """Bright-food OCR blank must not drop a wide stroke hardsub line."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            filter_tracks_by_local_text,
            MergedTrack,
        )

        track = MergedTrack(
            start_frame=0,
            end_frame=30,
            box_coords=[400.0, 980.0, 1400.0, 1020.0],
            best_frame_index=10,
            best_sharpness=20.0,
            centroid=(900.0, 1000.0),
            hit_count=12,
            hit_boxes=[(400.0, 980.0, 1400.0, 1020.0)] * 8,
            hit_frames=list(range(10, 18)),
            hit_sharpness=[20.0] * 8,
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        for x in range(420, 1380, 8):
            frame[985:1015, x : x + 5] = 235
            frame[985:1015, x + 5 : x + 8] = 25
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("", 0.0, 0.0)
        kept, audit = filter_tracks_by_local_text(
            [track],
            frame_cache={10: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(len(kept), 1)
        self.assertFalse(
            any(r.get("reason") == "local_text_reject" for r in audit["rows"])
        )

    def test_filter_tracks_drops_oversized_midframe_blob(self) -> None:
        blob = MergedTrack(
            start_frame=0,
            end_frame=4,
            box_coords=[449.0, 453.0, 1468.0, 592.0],  # ~0.53×0.13 mid
            best_frame_index=2,
            best_sharpness=5.0,
            centroid=(958.0, 522.0),
            hit_count=12,
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("中式", 0.9, 1.0)
        kept, audit = filter_tracks_by_local_text(
            [blob],
            frame_cache={2: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(kept, [])
        self.assertEqual(audit["dropped"], 1)
        self.assertEqual(audit["rows"][0]["reason"], "oversized_blob")

    def test_filter_keeps_wide_mid_title_line(self) -> None:
        """Tall-ish mid burn-in titles (h≈0.09, wide aspect) must not die as oversized_blob."""
        title = MergedTrack(
            start_frame=0,
            end_frame=8,
            box_coords=[811.0, 521.0, 1308.0, 620.0],  # ~0.26×0.09
            best_frame_index=2,
            best_sharpness=20.0,
            centroid=(1059.5, 570.5),
            hit_count=8,
            hit_boxes=[(811.0, 521.0, 1308.0, 620.0)] * 4,
            hit_frames=[1, 2, 3, 4],
            hit_sharpness=[20.0] * 4,
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        frame[521:620, 811:1308] = 230
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("懒人无米饭包", 0.95, 1.0)
        kept, audit = filter_tracks_by_local_text(
            [title],
            frame_cache={2: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(len(kept), 1)
        self.assertFalse(
            any(r.get("reason") == "oversized_blob" for r in audit["rows"]),
            msg=f"mid title must keep audit={audit}",
        )

    def test_mid_title_does_not_merge_with_tall_rematch_blob(self) -> None:
        """Wide mid title must not absorb a 3× taller rematch slab a few frames later."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            DetectionHit,
            merge_tracks_by_centroid,
            PADDING,
        )

        title = (596.0, 493.0, 1337.0, 591.0)
        tall = (687.0, 257.0, 1449.0, 551.0)
        hits = [
            DetectionHit(0, title, 20.0),
            DetectionHit(1, title, 20.0),
            DetectionHit(2, title, 20.0),
            DetectionHit(3, title, 20.0),
            DetectionHit(4, tall, 15.0),
        ]
        tracks = merge_tracks_by_centroid(
            hits, frame_count=100, pad=PADDING, frame_w=1920, frame_h=1080
        )
        self.assertGreaterEqual(len(tracks), 2)
        title_tracks = [
            t
            for t in tracks
            if abs((t.box_coords[3] - t.box_coords[1]) - 98.0) < 20
        ]
        self.assertTrue(title_tracks, msg=f"title track missing tracks={tracks}")
        self.assertLessEqual(title_tracks[0].end_frame, 5)

    def test_mid_title_does_not_merge_with_double_height_mid_slab(self) -> None:
        """Same-band mid title must not absorb a ~2× taller rematch of similar width."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            DetectionHit,
            merge_tracks_by_centroid,
            PADDING,
        )

        title = (596.0, 493.0, 1337.0, 591.0)  # h≈98
        slab = (728.0, 383.0, 1465.0, 596.0)  # h≈213, similar width
        hits = [
            DetectionHit(0, title, 20.0),
            DetectionHit(1, title, 20.0),
            DetectionHit(2, title, 20.0),
            DetectionHit(6, slab, 15.0),
        ]
        tracks = merge_tracks_by_centroid(
            hits, frame_count=100, pad=PADDING, frame_w=1920, frame_h=1080
        )
        self.assertGreaterEqual(len(tracks), 2)
        self.assertTrue(
            any(
                t.end_frame <= 4
                and abs((t.box_coords[3] - t.box_coords[1]) - 98.0) < 20
                for t in tracks
            ),
            msg=f"title must stay short tracks={[(t.start_frame,t.end_frame,t.box_coords) for t in tracks]}",
        )

    def test_filter_tracks_drops_tare_keeps_jia_yan(self) -> None:
        tare = MergedTrack(
            start_frame=0,
            end_frame=10,
            box_coords=[1700.0, 720.0, 1765.0, 780.0],
            best_frame_index=5,
            best_sharpness=10.0,
            centroid=(1732.5, 750.0),
            hit_count=20,
        )
        jia = MergedTrack(
            start_frame=0,
            end_frame=10,
            box_coords=[200.0, 480.0, 340.0, 560.0],
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(270.0, 520.0),
            hit_count=30,
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        frame[480:560, 200:340] = 240
        frame[720:780, 1700:1765] = 200

        rec = MagicMock()

        def _recognize(crop: np.ndarray) -> LocalRecognition:
            if crop.shape[1] >= 100:
                return LocalRecognition("加盐", 0.9, 1.0)
            return LocalRecognition("TARE", 0.9, 1.0)

        rec.recognize.side_effect = _recognize
        kept, audit = filter_tracks_by_local_text(
            [tare, jia],
            frame_cache={5: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].box_coords, jia.box_coords)
        self.assertEqual(audit["dropped"], 1)


    def test_keeps_cjk_with_latin_gram_unit(self) -> None:
        """Burn-in recipes often use ASCII g/ml instead of 克."""
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="盐2g", confidence=0.98, valid_char_ratio=1.0),
                role="ui_chip",
            )
        )
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(text="生抽15g", confidence=0.95, valid_char_ratio=1.0),
                role="mid_label",
            )
        )
        # Ingredient cards commonly put the unit between the amount and name.
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(
                    text="150g里脊肉", confidence=0.99, valid_char_ratio=1.0
                ),
                role="ui_chip",
            )
        )
        self.assertTrue(
            local_text_accepts_track(
                LocalRecognition(
                    text="250g虾仁", confidence=0.99, valid_char_ratio=1.0
                ),
                role="ui_chip",
            )
        )
        # Still drop appliance Latin / junk.
        self.assertFalse(
            local_text_accepts_track(
                LocalRecognition(text="TARE", confidence=0.9, valid_char_ratio=1.0),
                role="ui_chip",
            )
        )

    def test_splits_tall_mid_blob_into_row_tracks(self) -> None:
        """Multi-line ingredient blob must become row boxes, not oversized_blob drop."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            split_mid_label_blob_rows,
        )

        # Two white text bands stacked in one tall mid box (蒜末 + 芝麻 class).
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        frame[220:270, 320:450] = 255
        frame[300:350, 320:450] = 255
        blob = MergedTrack(
            start_frame=0,
            end_frame=20,
            box_coords=[320.0, 218.0, 450.0, 374.0],  # h/H≈0.144 → oversized
            best_frame_index=10,
            best_sharpness=20.0,
            centroid=(385.0, 296.0),
            hit_count=30,
            hit_boxes=[(320.0, 218.0, 450.0, 374.0)],
            hit_frames=[10],
            hit_sharpness=[20.0],
        )
        rows = split_mid_label_blob_rows(blob, frame_bgr=frame, frame_h=1080)
        self.assertGreaterEqual(len(rows), 2)
        for r in rows:
            h = r.box_coords[3] - r.box_coords[1]
            self.assertLessEqual(h / 1080.0, 0.085)

    def test_splits_tall_blob_from_hit_box_y_clusters_without_frame(self) -> None:
        """
        When keyframe cache misses, stacked rows must still split via hit history.

        Over-merged ingredient tracks often carry thin per-frame boxes at two Y
        bands; ink projection cannot run without a frame.
        """
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            split_mid_label_blob_rows,
        )

        top = (320.0, 220.0, 450.0, 280.0)
        bot = (322.0, 310.0, 448.0, 370.0)
        hit_boxes = [top, bot, top, bot, top, bot]
        blob = MergedTrack(
            start_frame=0,
            end_frame=20,
            box_coords=[320.0, 218.0, 450.0, 374.0],
            best_frame_index=10,
            best_sharpness=20.0,
            centroid=(385.0, 296.0),
            hit_count=6,
            hit_boxes=hit_boxes,
            hit_frames=[0, 2, 4, 6, 8, 10],
            hit_sharpness=[20.0] * 6,
        )
        rows = split_mid_label_blob_rows(
            blob, frame_bgr=None, frame_h=1080
        )
        self.assertGreaterEqual(len(rows), 2, msg=f"got {[r.box_coords for r in rows]}")
        for r in rows:
            h = r.box_coords[3] - r.box_coords[1]
            self.assertLessEqual(h / 1080.0, 0.085)
        # Hits partitioned — not all copied onto every row.
        self.assertTrue(all(r.hit_count >= 2 for r in rows))

    def test_filter_splits_hit_cluster_blob_without_cache_frame(self) -> None:
        """Tall over-merge must not die as oversized_blob when best_frame missing."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            filter_tracks_by_local_text,
        )

        top = (320.0, 220.0, 450.0, 280.0)
        bot = (322.0, 310.0, 448.0, 370.0)
        blob = MergedTrack(
            start_frame=0,
            end_frame=40,
            box_coords=[320.0, 218.0, 450.0, 374.0],
            best_frame_index=99,  # not in cache
            best_sharpness=20.0,
            centroid=(385.0, 296.0),
            hit_count=12,
            hit_boxes=[top, bot] * 6,
            hit_frames=[0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22],
            hit_sharpness=[20.0] * 12,
        )
        peer = MergedTrack(
            start_frame=0,
            end_frame=40,
            box_coords=[274.0, 391.0, 503.0, 468.0],
            best_frame_index=10,
            best_sharpness=18.0,
            centroid=(388.0, 430.0),
            hit_count=40,
            hit_boxes=[(274.0, 391.0, 503.0, 468.0)] * 8,
            hit_frames=list(range(8)),
            hit_sharpness=[18.0] * 8,
        )
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        frame[220:280, 320:450] = 255
        frame[310:370, 320:450] = 255
        frame[391:468, 274:503] = 255
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("蒜末", 0.95, 1.0)
        kept, audit = filter_tracks_by_local_text(
            [blob, peer],
            # Hit frames present (production dense cache); best_frame 99 still missing.
            frame_cache={0: frame, 2: frame, 10: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertFalse(
            any(
                r.get("reason") == "oversized_blob"
                and abs(float((r.get("box") or [0])[1]) - 218) < 2
                for r in audit["rows"]
            ),
            msg=f"blob still oversized audit={audit}",
        )
        self.assertGreaterEqual(len(kept), 2)

    def test_filter_keeps_salt_2g_and_splits_blob(self) -> None:
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        frame[220:270, 320:450] = 255
        frame[300:350, 320:450] = 255
        frame[720:780, 320:460] = 255
        blob = MergedTrack(
            start_frame=0,
            end_frame=40,
            box_coords=[320.0, 218.0, 450.0, 374.0],
            best_frame_index=10,
            best_sharpness=20.0,
            centroid=(385.0, 296.0),
            hit_count=40,
            hit_boxes=[(320.0, 218.0, 450.0, 374.0)],
            hit_frames=[10],
            hit_sharpness=[20.0],
        )
        salt = MergedTrack(
            start_frame=0,
            end_frame=40,
            box_coords=[325.0, 720.0, 457.0, 784.0],
            best_frame_index=10,
            best_sharpness=15.0,
            centroid=(391.0, 752.0),
            hit_count=40,
            hit_boxes=[(325.0, 720.0, 457.0, 784.0)],
            hit_frames=[10],
            hit_sharpness=[15.0],
        )
        # Peer column anchor so n=3 mid can survive if present.
        peer = MergedTrack(
            start_frame=0,
            end_frame=40,
            box_coords=[274.0, 391.0, 503.0, 468.0],
            best_frame_index=10,
            best_sharpness=18.0,
            centroid=(388.0, 430.0),
            hit_count=40,
            hit_boxes=[(274.0, 391.0, 503.0, 468.0)],
            hit_frames=[10],
            hit_sharpness=[18.0],
        )

        rec = MagicMock()

        def _recognize(crop: np.ndarray) -> LocalRecognition:
            y_mean = float(np.mean(np.argmax(crop.shape) and crop[:, :, 0]))
            h = int(crop.shape[0])
            if h > 100:
                return LocalRecognition("蒜末芝麻", 0.9, 1.0)
            # Salt chip is shorter.
            if int(crop.shape[1]) < 160:
                return LocalRecognition("盐2g", 0.98, 1.0)
            return LocalRecognition("生抽15g", 0.95, 1.0)

        rec.recognize.side_effect = _recognize
        kept, audit = filter_tracks_by_local_text(
            [blob, salt, peer],
            frame_cache={10: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        # Salt kept (not local_text_reject).
        self.assertTrue(
            any(
                abs(t.box_coords[1] - 720) < 5 and abs(t.box_coords[3] - 784) < 5
                for t in kept
            ),
            msg=f"salt missing from kept={[t.box_coords for t in kept]} audit={audit}",
        )
        # Blob not dropped wholesale as oversized — either split kept or no oversized on original.
        self.assertFalse(
            any(
                r.get("reason") == "oversized_blob"
                and abs(float((r.get("box") or [0, 0, 0, 0])[1]) - 218) < 2
                for r in audit["rows"]
            )
        )
        self.assertGreaterEqual(len(kept), 3)



    def test_compact_list_name_chip_is_ui_chip_not_mid_label(self) -> None:
        """Single-glyph endcard names (虾) sit at cy~0.54 — must be ui_chip."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            classify_ocr_box_role,
        )

        shrimp = [154.0, 569.0, 179.0, 603.0]
        self.assertEqual(
            classify_ocr_box_role(shrimp, frame_w=1920, frame_h=1080),
            "ui_chip",
        )
        # Wide nutrient labels stay mid_label.
        carb = [224.0, 288.0, 454.0, 318.0]
        self.assertEqual(
            classify_ocr_box_role(carb, frame_w=1920, frame_h=1080),
            "mid_label",
        )

    def test_splits_narrow_percent_column_under_legacy_height(self) -> None:
        """21%+40% stack is h/H~0.08 — still must split (narrow column)."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            split_mid_label_blob_rows,
        )

        frame = np.full((1080, 1920, 3), 245, dtype=np.uint8)
        frame[235:265, 1110:1160] = 20
        frame[285:315, 1110:1160] = 20
        blob = MergedTrack(
            start_frame=701,
            end_frame=745,
            box_coords=[1100.0, 229.0, 1168.0, 316.0],  # h/H≈0.081 < 0.085
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(1134.0, 272.5),
            hit_count=24,
            hit_boxes=[
                (1100.0, 229.0, 1168.0, 265.0),
                (1102.0, 280.0, 1166.0, 316.0),
            ]
            * 3,
            hit_frames=[728, 729, 730, 731, 732, 733],
            hit_sharpness=[10.0] * 6,
        )
        rows = split_mid_label_blob_rows(blob, frame_bgr=frame, frame_h=1080)
        self.assertGreaterEqual(len(rows), 2, msg=f"got {[r.box_coords for r in rows]}")
        for r in rows:
            self.assertLessEqual((r.box_coords[3] - r.box_coords[1]) / 1080.0, 0.06)


    def test_narrow_percent_split_keeps_row_hit_density(self) -> None:
        """Splitting a dense tall %% column must not zero out temporal hits."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            filter_tracks_by_local_text,
            split_mid_label_blob_rows,
        )

        frame = np.full((1080, 1920, 3), 245, dtype=np.uint8)
        frame[235:265, 1110:1160] = 20
        frame[285:315, 1110:1160] = 20
        # Tall union with only two thin hit stubs — product-class over-merge.
        blob = MergedTrack(
            start_frame=701,
            end_frame=745,
            box_coords=[1100.0, 229.0, 1168.0, 316.0],
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(1134.0, 272.5),
            hit_count=24,
            hit_boxes=[
                (1100.0, 229.0, 1168.0, 316.0),  # tall unions dominate
                (1100.0, 229.0, 1168.0, 265.0),
                (1102.0, 280.0, 1166.0, 316.0),
            ]
            * 8,
            hit_frames=list(range(701, 725)),
            hit_sharpness=[10.0] * 24,
        )
        rows = split_mid_label_blob_rows(blob, frame_bgr=frame, frame_h=1080)
        self.assertGreaterEqual(len(rows), 2)
        for r in rows:
            self.assertGreaterEqual(int(r.hit_count), 5, msg=f"row n={r.hit_count} box={r.box_coords}")
            self.assertGreaterEqual(
                len(r.hit_frames),
                5,
                msg=f"row frames starved n_frames={len(r.hit_frames)} box={r.box_coords}",
            )

        rec = MagicMock()
        rec.recognize.side_effect = lambda crop: LocalRecognition(
            "21%" if crop.shape[0] < 40 else "40%", 0.95, 1.0
        )
        kept, audit = filter_tracks_by_local_text(
            [blob],
            frame_cache={fi: frame for fi in range(701, 746)},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertGreaterEqual(len(kept), 2, msg=f"audit={audit}")


class OverlayVsSceneGateTests(unittest.TestCase):
    """Editor burn-in stays; packaging / in-scene text that moves is dropped."""

    def test_locked_hardsub_is_editor_overlay(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            is_editor_overlay_track,
        )

        boxes = [(40.0, 960.0, 1500.0, 1010.0)] * 8
        track = MergedTrack(
            start_frame=0,
            end_frame=20,
            box_coords=list(boxes[0]),
            best_frame_index=4,
            best_sharpness=20.0,
            centroid=(770.0, 985.0),
            hit_count=8,
            hit_boxes=list(boxes),
            hit_frames=list(range(8)),
            hit_sharpness=[20.0] * 8,
        )
        self.assertTrue(
            is_editor_overlay_track(
                track,
                role="hardsub",
                frame_w=1920,
                frame_h=1080,
                has_stable_column_peer=False,
            )
        )

    def test_wide_mid_label_x_jitter_still_editor(self) -> None:
        """Fixed UI labels (碳水化合物) may jitter in X from partial DBNet widths."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            is_editor_overlay_track,
            is_horizontally_locked_track,
        )

        # Fossil-class: left-edge flicker ~±30px on a ~290px-wide nutrient label.
        boxes = [
            (165.0, 281.0, 455.0, 316.0),
            (210.0, 280.0, 500.0, 315.0),
            (140.0, 282.0, 430.0, 317.0),
            (190.0, 280.5, 480.0, 316.0),
            (155.0, 281.0, 445.0, 315.5),
            (200.0, 280.0, 490.0, 316.0),
            (145.0, 281.5, 435.0, 316.5),
            (185.0, 280.0, 475.0, 315.0),
        ]
        track = MergedTrack(
            start_frame=701,
            end_frame=745,
            box_coords=list(boxes[0]),
            best_frame_index=730,
            best_sharpness=12.0,
            centroid=(310.0, 298.0),
            hit_count=48,
            hit_boxes=list(boxes) * 6,
            hit_frames=list(range(701, 749)),
            hit_sharpness=[12.0] * 48,
        )
        self.assertTrue(
            is_horizontally_locked_track(track, frame_w=1920, frame_h=1080)
        )
        self.assertTrue(
            is_editor_overlay_track(
                track,
                role="mid_label",
                frame_w=1920,
                frame_h=1080,
                has_stable_column_peer=False,
            )
        )


    def test_moving_short_mid_is_scene_even_with_peer(self) -> None:
        """Piping-bag / packaging text follows the hand — drop despite peer column."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            is_editor_overlay_track,
        )

        # Horizontal centroid drift across 3 hits (scene / hand-held class).
        boxes = [
            (840.0, 260.0, 1010.0, 330.0),
            (890.0, 300.0, 1060.0, 370.0),
            (940.0, 340.0, 1110.0, 410.0),
        ]
        track = MergedTrack(
            start_frame=210,
            end_frame=214,
            box_coords=list(boxes[1]),
            best_frame_index=211,
            best_sharpness=12.0,
            centroid=(975.0, 335.0),
            hit_count=3,
            hit_boxes=list(boxes),
            hit_frames=[210, 211, 212],
            hit_sharpness=[12.0] * 3,
        )
        self.assertFalse(
            is_editor_overlay_track(
                track,
                role="mid_label",
                frame_w=1920,
                frame_h=1080,
                has_stable_column_peer=True,
            )
        )

    def test_locked_short_mid_with_peer_is_editor(self) -> None:
        """Ingredient flash in a stable list column must not be culled as scene."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            is_editor_overlay_track,
        )

        boxes = [
            (320.0, 220.0, 450.0, 280.0),
            (322.0, 221.0, 448.0, 279.0),
            (321.0, 220.5, 449.0, 281.0),
        ]
        track = MergedTrack(
            start_frame=100,
            end_frame=104,
            box_coords=list(boxes[0]),
            best_frame_index=101,
            best_sharpness=18.0,
            centroid=(385.0, 250.0),
            hit_count=3,
            hit_boxes=list(boxes),
            hit_frames=[100, 101, 102],
            hit_sharpness=[18.0] * 3,
        )
        self.assertTrue(
            is_editor_overlay_track(
                track,
                role="mid_label",
                frame_w=1920,
                frame_h=1080,
                has_stable_column_peer=True,
            )
        )

    def test_vertical_overmerge_high_sy_still_editor(self) -> None:
        """Stacked list rows may inflate Yσ; column-locked X must still keep."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            is_editor_overlay_track,
        )

        boxes = [
            (320.0, 220.0, 450.0, 280.0),
            (322.0, 300.0, 448.0, 360.0),
            (321.0, 380.0, 449.0, 440.0),
        ]
        track = MergedTrack(
            start_frame=0,
            end_frame=10,
            box_coords=list(boxes[1]),
            best_frame_index=5,
            best_sharpness=18.0,
            centroid=(385.0, 330.0),
            hit_count=12,
            hit_boxes=list(boxes) * 4,
            hit_frames=list(range(12)),
            hit_sharpness=[18.0] * 12,
        )
        self.assertTrue(
            is_editor_overlay_track(
                track,
                role="mid_label",
                frame_w=1920,
                frame_h=1080,
                has_stable_column_peer=False,
            )
        )

    def test_moving_long_mid_is_scene(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            is_editor_overlay_track,
        )

        boxes = [
            (800.0 + i * 12.0, 280.0 + i * 10.0, 980.0 + i * 12.0, 340.0 + i * 10.0)
            for i in range(12)
        ]
        track = MergedTrack(
            start_frame=0,
            end_frame=30,
            box_coords=list(boxes[6]),
            best_frame_index=12,
            best_sharpness=10.0,
            centroid=(890.0, 310.0),
            hit_count=12,
            hit_boxes=list(boxes),
            hit_frames=list(range(12)),
            hit_sharpness=[10.0] * 12,
        )
        self.assertFalse(
            is_editor_overlay_track(
                track,
                role="mid_label",
                frame_w=1920,
                frame_h=1080,
                has_stable_column_peer=False,
            )
        )

    def test_filter_drops_moving_packaging_keeps_locked_peer_chip(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            filter_tracks_by_local_text,
        )

        peer = MergedTrack(
            start_frame=0,
            end_frame=40,
            box_coords=[274.0, 391.0, 503.0, 468.0],
            best_frame_index=10,
            best_sharpness=18.0,
            centroid=(388.0, 430.0),
            hit_count=40,
            hit_boxes=[(274.0, 391.0, 503.0, 468.0)] * 8,
            hit_frames=list(range(8)),
            hit_sharpness=[18.0] * 8,
        )
        locked_chip = MergedTrack(
            start_frame=100,
            end_frame=104,
            box_coords=[320.0, 220.0, 450.0, 280.0],
            best_frame_index=101,
            best_sharpness=18.0,
            centroid=(385.0, 250.0),
            hit_count=3,
            hit_boxes=[
                (320.0, 220.0, 450.0, 280.0),
                (322.0, 221.0, 448.0, 279.0),
                (321.0, 220.5, 449.0, 281.0),
            ],
            hit_frames=[100, 101, 102],
            hit_sharpness=[18.0] * 3,
        )
        packaging = MergedTrack(
            start_frame=210,
            end_frame=214,
            box_coords=[890.0, 300.0, 1060.0, 370.0],
            best_frame_index=211,
            best_sharpness=12.0,
            centroid=(975.0, 335.0),
            hit_count=3,
            hit_boxes=[
                (870.0, 260.0, 1040.0, 330.0),
                (890.0, 300.0, 1060.0, 370.0),
                (910.0, 340.0, 1080.0, 410.0),
            ],
            hit_frames=[210, 211, 212],
            hit_sharpness=[12.0] * 3,
        )
        # Same column bucket as peer so peer min_hits=3 would otherwise rescue packaging.
        packaging.box_coords = [310.0, 300.0, 480.0, 370.0]
        packaging.hit_boxes = [
            (260.0, 260.0, 430.0, 330.0),
            (310.0, 300.0, 480.0, 370.0),
            (360.0, 340.0, 530.0, 410.0),
        ]
        packaging.centroid = (395.0, 335.0)

        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        frame[391:468, 274:503] = 240
        frame[220:280, 320:450] = 240
        frame[300:370, 280:450] = 200
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("净含量150克", 0.95, 1.0)

        kept, audit = filter_tracks_by_local_text(
            [peer, locked_chip, packaging],
            frame_cache={10: frame, 101: frame, 211: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertTrue(
            any(r.get("reason") == "scene_text" for r in audit["rows"]),
            msg=f"expected scene_text drop, audit={audit}",
        )
        self.assertTrue(
            any(abs(t.box_coords[1] - 220) < 2 for t in kept),
            msg=f"locked peer chip missing kept={[t.box_coords for t in kept]}",
        )
        self.assertFalse(
            any(abs(t.centroid[1] - 335) < 1 for t in kept),
            msg="moving packaging must not stay in SSOT",
        )


class Phase1PolishGateTests(unittest.TestCase):
    def test_coalesce_near_duplicate_column_tracks(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            coalesce_near_duplicate_tracks,
        )

        a = MergedTrack(
            start_frame=10,
            end_frame=40,
            box_coords=[325.0, 144.0, 448.0, 222.0],
            best_frame_index=20,
            best_sharpness=10.0,
            centroid=(386.5, 183.0),
            hit_count=6,
            hit_boxes=[(325.0, 144.0, 448.0, 222.0)] * 6,
            hit_frames=list(range(10, 22, 2)),
            hit_sharpness=[10.0] * 6,
        )
        b = MergedTrack(
            start_frame=30,
            end_frame=80,
            box_coords=[326.0, 145.0, 449.0, 221.0],
            best_frame_index=50,
            best_sharpness=18.0,
            centroid=(387.5, 183.0),
            hit_count=20,
            hit_boxes=[(326.0, 145.0, 449.0, 221.0)] * 8,
            hit_frames=list(range(30, 46, 2)),
            hit_sharpness=[18.0] * 8,
        )
        other = MergedTrack(
            start_frame=10,
            end_frame=80,
            box_coords=[325.0, 720.0, 455.0, 786.0],
            best_frame_index=40,
            best_sharpness=15.0,
            centroid=(390.0, 753.0),
            hit_count=40,
            hit_boxes=[(325.0, 720.0, 455.0, 786.0)],
            hit_frames=[40],
            hit_sharpness=[15.0],
        )
        out = coalesce_near_duplicate_tracks(
            [a, b, other], frame_w=1920, frame_h=1080
        )
        self.assertEqual(len(out), 2)
        top = [t for t in out if t.box_coords[1] < 400][0]
        self.assertGreaterEqual(top.hit_count, 14)  # union of hit_boxes
        self.assertEqual(top.start_frame, 10)
        self.assertEqual(top.end_frame, 80)

    def test_trimmed_stable_box_rejects_outlier_hit(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            stable_box_xyxy,
        )

        thin = [(100.0, 200.0, 300.0, 260.0)] * 6
        fat = (40.0, 120.0, 700.0, 520.0)  # low-IoU food slab
        got = stable_box_xyxy([*thin, fat], expansive=False)
        self.assertLess(got[2] - got[0], 250.0)
        self.assertLess(got[3] - got[1], 100.0)
        self.assertGreater(got[0], 80.0)

    def test_ink_aware_keyframe_prefers_stroke_over_blurry(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            pick_ink_aware_keyframe,
            MergedTrack,
        )

        box = [100.0, 900.0, 800.0, 960.0]
        sharp_frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        sharp_frame[910:950, 120:780] = 255
        # Add edge contrast so stroke score beats flat blur.
        sharp_frame[910:950, 120:125] = 0
        blur_frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
        track = MergedTrack(
            start_frame=0,
            end_frame=10,
            box_coords=box,
            best_frame_index=1,  # blurry currently "best" by laplacian mock
            best_sharpness=99.0,
            centroid=(450.0, 930.0),
            hit_count=2,
            hit_boxes=[tuple(box), tuple(box)],
            hit_frames=[1, 5],
            hit_sharpness=[99.0, 1.0],
        )
        fi, score = pick_ink_aware_keyframe(
            track,
            frame_cache={1: blur_frame, 5: sharp_frame},
            frame_w=1920,
            frame_h=1080,
        )
        self.assertEqual(fi, 5)
        self.assertGreater(score, 0.0)

    def test_multi_crop_keeps_when_first_frame_rejects(self) -> None:
        """One bad crop must not kill a track if another hit frame accepts."""
        calls: list[str] = []

        rec = MagicMock()

        def _recognize(crop: np.ndarray) -> LocalRecognition:
            calls.append("x")
            if len(calls) == 1:
                return LocalRecognition("的", 0.2, 0.3)
            return LocalRecognition("加盐", 0.95, 1.0)

        rec.recognize.side_effect = _recognize
        track = MergedTrack(
            start_frame=0,
            end_frame=10,
            box_coords=[200.0, 480.0, 340.0, 560.0],
            best_frame_index=1,
            best_sharpness=10.0,
            centroid=(270.0, 520.0),
            hit_count=8,
            hit_boxes=[(200.0, 480.0, 340.0, 560.0)] * 4,
            hit_frames=[1, 3, 5, 7],
            hit_sharpness=[10.0] * 4,
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        frame[480:560, 200:340] = 240
        kept, audit = filter_tracks_by_local_text(
            [track],
            frame_cache={1: frame, 3: frame, 5: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(len(kept), 1)
        self.assertGreaterEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
