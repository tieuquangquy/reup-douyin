"""Master Phase 1: pad, IoU/gap merge, confirm-hit, crop sharpness, geometry.

Also covers pre-gate text-frame coverage SSOT (frames that actually had text hits).
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    STEP,
    PADDING,
    ROI_Y0,
    _DiskBackedFrameCache,
    DetectionHit,
    MergedTrack,
    apply_temporal_pad,
    box_iou,
    build_text_frame_coverage,
    coalesce_tracks_by_local_text_content,
    confirm_tracks,
    crop_box_sharpness,
    dense_rescan_frame_indices,
    expand_tracks_by_local_text_continuity,
    format_timeline_time,
    is_plausible_text_box,
    merge_tracks_by_centroid,
    merge_primary_and_residual_frame_hits,
    phase_offset_frame_indices,
    phase1_residual_risk_frame_indices,
    purge_temporally_nested_ui_fragments,
    purge_unverified_sparse_compact_tracks_after_refinement,
    recover_residual_hardsub_tracks,
    reconcile_final_tracks_with_coverage,
    stable_box_xyxy,
    split_tracks_by_local_text_change,
    split_wide_ui_tracks_by_ink_columns,
    timeline_entry_dict,
    timeline_to_ocr_payload,
)

from src.media_pipeline.frame_sampling.local_text_recognizer import LocalRecognition


class DiskBackedFrameCacheTests(unittest.TestCase):
    def test_cache_is_lossless_and_bounds_hot_ram_by_bytes(self) -> None:
        frame_bytes = 4 * 5 * 3
        cache = _DiskBackedFrameCache(max_hot_bytes=frame_bytes * 2)
        try:
            expected: dict[int, np.ndarray] = {}
            for frame_index in range(10):
                frame = np.full((4, 5, 3), frame_index, dtype=np.uint8)
                expected[frame_index] = frame
                cache[frame_index] = frame

            self.assertEqual(len(cache), 10)
            self.assertEqual(cache.backing_bytes, frame_bytes * 10)
            for frame_index in range(10):
                np.testing.assert_array_equal(cache[frame_index], expected[frame_index])
                self.assertLessEqual(cache.hot_bytes, frame_bytes * 2)
                self.assertLessEqual(cache.hot_frame_count, 2)
        finally:
            cache.close()


class TemporalPadTests(unittest.TestCase):
    def test_padding_equals_step(self) -> None:
        self.assertEqual(PADDING, STEP)
        self.assertGreaterEqual(STEP, 1)
        self.assertLessEqual(ROI_Y0, 0.35)

    def test_residual_risk_windows_cover_intro_and_outro_only(self) -> None:
        frames = phase1_residual_risk_frame_indices(
            frame_count=300, fps=30.0, risk_seconds=2.0
        )

        self.assertEqual(min(frames), 0)
        self.assertEqual(max(frames), 299)
        self.assertIn(59, frames)
        self.assertIn(240, frames)
        self.assertNotIn(60, frames)
        self.assertNotIn(239, frames)
        self.assertEqual(len(frames), 120)

    def test_residual_profile_replaces_overlapping_primary_slab(self) -> None:
        primary = DetectionHit(
            frame_index=3,
            box_xyxy=(492.0, 460.0, 1308.0, 592.0),
            sharpness=10.0,
        )
        residual = DetectionHit(
            frame_index=3,
            box_xyxy=(599.0, 488.0, 1331.0, 580.0),
            sharpness=20.0,
        )

        merged = merge_primary_and_residual_frame_hits(
            [primary], [residual]
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].box_xyxy, residual.box_xyxy)

    def test_hit_at_50_spans_n_minus_padding_to_n_plus_padding(self) -> None:
        """Fade-safe stretch: Frame_N=50 → [49, 51] when PADDING=STEP=1."""
        start, end = apply_temporal_pad(50, frame_count=844, pad=PADDING)
        self.assertEqual((start, end), (50 - PADDING, 50 + PADDING))

    def test_pad_clamps_at_edges(self) -> None:
        self.assertEqual(
            apply_temporal_pad(0, frame_count=100, pad=PADDING),
            (0, PADDING),
        )
        self.assertEqual(
            apply_temporal_pad(99, frame_count=100, pad=PADDING),
            (99 - PADDING, 99),
        )


class DenseRescanTests(unittest.TestCase):
    def test_dense_window_around_each_coarse_hit(self) -> None:
        hits = [
            DetectionHit(10, (100.0, 500.0, 200.0, 540.0), 1.0),
            DetectionHit(20, (100.0, 500.0, 200.0, 540.0), 1.0),
        ]
        idxs = dense_rescan_frame_indices(hits, step=2, frame_count=100)
        self.assertEqual(idxs, list(range(8, 13)) + list(range(18, 23)))


class PhaseOffsetTests(unittest.TestCase):
    def test_phase_offset_probes_between_coarse_samples(self) -> None:
        # STEP=2 → probe 1,5,9,... (offset 1 every 2*STEP) so gaps without coarse hits still get a look.
        idxs = phase_offset_frame_indices(frame_count=20, step=2)
        self.assertEqual(idxs, [1, 5, 9, 13, 17])


class CropSharpnessTests(unittest.TestCase):
    def test_sharpness_uses_box_crop_not_full_frame(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        # Sharp checkerboard only inside the box region.
        tile = np.array([[0, 255], [255, 0]], dtype=np.uint8)
        patch = np.tile(tile, (10, 20))
        frame[40:60, 50:90, :] = np.stack([patch, patch, patch], axis=-1)
        sharp_box = crop_box_sharpness(frame, (50.0, 40.0, 90.0, 60.0))
        sharp_empty = crop_box_sharpness(frame, (150.0, 10.0, 190.0, 30.0))
        self.assertGreater(sharp_box, sharp_empty * 5.0)


class GeometryFilterTests(unittest.TestCase):
    def test_rejects_huge_endcard_area(self) -> None:
        # Nearly full-frame card
        self.assertFalse(
            is_plausible_text_box((50.0, 100.0, 1870.0, 900.0), frame_w=1920, frame_h=1080)
        )

    def test_keeps_bottom_hardsub_and_mid_label(self) -> None:
        hardsub = (80.0, 900.0, 900.0, 960.0)
        mid = (800.0, 480.0, 1000.0, 530.0)
        self.assertTrue(is_plausible_text_box(hardsub, frame_w=1920, frame_h=1080))
        self.assertTrue(is_plausible_text_box(mid, frame_w=1920, frame_h=1080))


class StableBoxTests(unittest.TestCase):
    def test_median_box_not_largest(self) -> None:
        boxes = [
            (100.0, 900.0, 200.0, 940.0),
            (110.0, 905.0, 300.0, 950.0),  # larger outlier
            (105.0, 902.0, 210.0, 942.0),
        ]
        stable = stable_box_xyxy(boxes)
        # Median x1 should be 210, not the largest 300.
        self.assertEqual(stable[2], 210.0)


class IoUMergeTests(unittest.TestCase):
    def test_box_iou_overlap(self) -> None:
        a = (0.0, 0.0, 100.0, 100.0)
        b = (50.0, 50.0, 150.0, 150.0)
        self.assertAlmostEqual(box_iou(a, b), 2500.0 / 17500.0, places=5)

    def test_nearby_hits_merge_overlapping_padded_spans(self) -> None:
        # pad=2: [48,52] ∪ [50,54] → [48,54]; stable box = median
        hits = [
            DetectionHit(
                frame_index=50,
                box_xyxy=(190.0, 910.0, 210.0, 930.0),
                sharpness=10.0,
            ),
            DetectionHit(
                frame_index=52,
                box_xyxy=(100.0, 900.0, 310.0, 950.0),
                sharpness=20.0,
            ),
        ]
        tracks = merge_tracks_by_centroid(
            hits, frame_count=844, pad=2, max_centroid_px=20.0
        )
        self.assertEqual(len(tracks), 1)
        track = tracks[0]
        self.assertEqual(track.start_frame, 48)
        self.assertEqual(track.end_frame, 54)
        self.assertEqual(track.hit_count, 2)
        self.assertEqual(track.best_frame_index, 52)
        # Median of the two boxes (not largest-only).
        self.assertEqual(
            track.box_coords,
            stable_box_xyxy(
                [(190.0, 910.0, 210.0, 930.0), (100.0, 900.0, 310.0, 950.0)]
            ),
        )

    def test_iou_or_gap_bridges_fragmented_same_line(self) -> None:
        # Centroids farther than 20px but high IoU + short gap → still merge.
        hits = [
            DetectionHit(40, (100.0, 900.0, 400.0, 940.0), 10.0),
            DetectionHit(50, (120.0, 905.0, 420.0, 945.0), 12.0),
        ]
        tracks = merge_tracks_by_centroid(
            hits, frame_count=200, pad=2, max_centroid_px=20.0
        )
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].start_frame, 38)
        self.assertEqual(tracks[0].end_frame, 52)

    def test_distant_centroids_low_iou_stay_separate(self) -> None:
        hits = [
            DetectionHit(
                frame_index=50,
                box_xyxy=(100.0, 900.0, 200.0, 940.0),
                sharpness=10.0,
            ),
            DetectionHit(
                frame_index=52,
                box_xyxy=(400.0, 900.0, 500.0, 940.0),
                sharpness=10.0,
            ),
        ]
        tracks = merge_tracks_by_centroid(
            hits, frame_count=200, pad=PADDING, max_centroid_px=20.0
        )
        self.assertEqual(len(tracks), 2)

    def test_hardsub_width_jump_keeps_consecutive_lines_separate(self) -> None:
        """Bottom-band lines share cy/IoU but different lengths are different SSOT rows."""
        # Short then long centered burn-ins: IoU≈0.33 ≥ MIN_MERGE_IOU and gap short
        # → old centroid merge glued them into one mega track spanning both lines.
        hits = [
            DetectionHit(100, (500.0, 1000.0, 900.0, 1048.0), 10.0),
            DetectionHit(102, (505.0, 1000.0, 895.0, 1048.0), 11.0),
            DetectionHit(110, (350.0, 1000.0, 1550.0, 1048.0), 12.0),
            DetectionHit(112, (360.0, 1000.0, 1540.0, 1048.0), 13.0),
        ]
        tracks = merge_tracks_by_centroid(hits, frame_count=200, pad=PADDING)
        self.assertEqual(
            len(tracks),
            2,
            msg=f"expected 2 hardsub lines, got {[t.box_coords for t in tracks]}",
        )
        widths = sorted(float(t.box_coords[2]) - float(t.box_coords[0]) for t in tracks)
        self.assertLess(widths[0], 500.0)
        self.assertGreater(widths[1], 1000.0)

    def test_hardsub_similar_width_jitter_still_merges(self) -> None:
        """Same burn-in line with mild DBNet width jitter must stay one track."""
        hits = [
            DetectionHit(100, (400.0, 1000.0, 1200.0, 1048.0), 10.0),
            DetectionHit(102, (420.0, 1000.0, 1180.0, 1048.0), 11.0),
            DetectionHit(104, (410.0, 1000.0, 1190.0, 1048.0), 12.0),
        ]
        tracks = merge_tracks_by_centroid(hits, frame_count=200, pad=PADDING)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].hit_count, 3)

    def test_hardsub_edge_jump_splits_similar_width_lines(self) -> None:
        """Same-ish width but left/right reflow is a new burn-in line."""
        hits = [
            DetectionHit(100, (500.0, 1000.0, 1300.0, 1048.0), 10.0),
            DetectionHit(102, (510.0, 1000.0, 1290.0, 1048.0), 11.0),
            DetectionHit(110, (350.0, 1000.0, 1150.0, 1048.0), 12.0),
            DetectionHit(112, (360.0, 1000.0, 1140.0, 1048.0), 13.0),
        ]
        tracks = merge_tracks_by_centroid(hits, frame_count=200, pad=PADDING)
        self.assertEqual(
            len(tracks),
            2,
            msg=f"expected edge-split lines, got {[t.box_coords for t in tracks]}",
        )

    def test_hardsub_gradual_width_drift_splits_into_multiple_lines(self) -> None:
        """
        Consecutive hits can drift slowly so last-hit gates never fire.

        Seed-vs-current (and post split) must break into multiple SSOT lines.
        """
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            split_overmerged_tracks,
        )

        hits: list[DetectionHit] = []
        # Line A ~w=800, then slowly shrink toward ~w=500 (new subtitle length).
        for i, fi in enumerate(range(100, 160, 2)):
            # width: 800 → ~480 over the span
            w = 800.0 - i * 10.0
            x0 = 960.0 - w * 0.5
            x1 = 960.0 + w * 0.5
            hits.append(DetectionHit(fi, (x0, 1000.0, x1, 1048.0), 10.0 + i))
        merged = merge_tracks_by_centroid(
            hits, frame_count=300, pad=1, frame_w=1920, frame_h=1080
        )
        split = split_overmerged_tracks(
            merged, frame_count=300, pad=1, frame_w=1920, frame_h=1080
        )
        self.assertGreaterEqual(
            len(split),
            2,
            msg=(
                f"gradual width drift must split "
                f"merged={len(merged)} split={len(split)} "
                f"widths={[round(t.box_coords[2]-t.box_coords[0]) for t in split]}"
            ),
        )


class ConfirmHitTests(unittest.TestCase):
    def test_single_hit_tracks_are_dropped(self) -> None:
        # Lone hit far from the confirmed pair so gap-bridge cannot merge them.
        hits = [
            DetectionHit(10, (100.0, 900.0, 200.0, 940.0), 10.0),
            DetectionHit(60, (100.0, 900.0, 200.0, 940.0), 11.0),
            DetectionHit(61, (105.0, 902.0, 205.0, 942.0), 12.0),
        ]
        merged = merge_tracks_by_centroid(
            hits, frame_count=200, pad=PADDING, max_centroid_px=20.0
        )
        kept, dropped = confirm_tracks(merged, min_hits=2)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].hit_count, 2)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0].hit_count, 1)


class HardsubInkExtendTests(unittest.TestCase):
    def test_extend_covers_full_white_line_from_truncated_seed(self) -> None:
        """DBNet often truncates hardsubs; ink walk must recover the rest of the line."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            extend_hardsub_box_to_ink,
        )

        frame = np.full((1080, 1920, 3), 20, dtype=np.uint8)
        # Discrete white glyph blocks (burn-in) spanning ~40→1450.
        for gx in range(40, 1450, 55):
            frame[932:978, gx : gx + 40] = 255
            frame[930:980, gx : gx + 2] = 0
            frame[930:980, gx + 38 : gx + 40] = 0
        # Truncated seed covering only the left half (fossil sub_08 shape).
        seed = (40.0, 920.0, 700.0, 990.0)
        out = extend_hardsub_box_to_ink(frame, seed)
        self.assertLessEqual(out[0], seed[0] + 1.0)
        self.assertGreater(out[2], 1200.0)
        self.assertGreater(out[2], seed[2] + 400.0)
        self.assertGreater((out[2] - out[0]) / 1920.0, 0.60)
        # Must not run away to the full frame width on empty dark bg.
        self.assertLess(out[2], 1900.0)

    def test_extend_does_not_balloon_short_line_on_bright_bowl(self) -> None:
        """Flat bright paper must not be treated as hardsub ink."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            extend_hardsub_box_to_ink,
        )

        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        # Bright bowl / plate under the band (false ink if using raw brightness).
        frame[900:1000, 200:1700] = 220
        # Short white glyph block only on the left.
        frame[932:978, 80:360] = 255
        frame[930:980, 80:82] = 0
        frame[930:980, 358:360] = 0
        seed = (80.0, 920.0, 360.0, 990.0)
        out = extend_hardsub_box_to_ink(frame, seed)
        self.assertLess((out[2] - out[0]) / 1920.0, 0.35)
        self.assertLess(out[2], 700.0)

    def test_extend_complete_mid_line_does_not_left_walk_into_wood(self) -> None:
        """Complete mid-width hardsub must not grow left into wood/food texture."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            extend_hardsub_box_to_ink,
            trim_hardsub_box_to_ink,
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 25, dtype=np.uint8)
        # High-contrast wood/food grain left of the line (false stroke ink).
        rng = np.random.default_rng(0)
        for x in range(0, 640):
            v = int(30 + 40 * np.sin(x / 3.0) + int(rng.integers(-15, 16)))
            v = max(0, min(255, v))
            frame[1010:1060, x] = (v, v // 2, 20)
        for x in range(0, 640, 4):
            frame[1016:1050, x : x + 2] = 200
            frame[1016:1050, x + 2 : x + 4] = 10
        # Complete centered burn-in (w≈0.32) — detector already covers glyphs.
        for x in range(650, 1260, 8):
            frame[1016:1050, x : x + 5] = 240
            frame[1016:1050, x + 5 : x + 8] = 20
        seed = [651.0, 1016.0, 1260.0, 1053.0]
        extended = extend_hardsub_box_to_ink(
            frame, seed, frame_w=1920, frame_h=1080
        )
        self.assertGreaterEqual(extended[0], 600.0)
        self.assertLess((extended[2] - extended[0]) / 1920.0, 0.42)
        trimmed = trim_hardsub_box_to_ink(
            frame,
            extended,
            frame_w=1920,
            frame_h=1080,
            seed_xyxy=seed,
        )
        self.assertGreaterEqual(trimmed[0], 620.0)
        track = MergedTrack(
            start_frame=753,
            end_frame=874,
            box_coords=list(seed),
            best_frame_index=818,
            best_sharpness=20.0,
            centroid=(955.5, 1034.5),
            hit_count=40,
            hit_boxes=[tuple(seed)] * 6,
            hit_frames=[816, 817, 818, 819],
            hit_sharpness=[20.0] * 4,
        )
        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={818: frame},
            frame_w=1920,
            frame_h=1080,
        )
        box = out[0].box_coords
        self.assertGreaterEqual(box[0], 620.0)
        self.assertLess((box[2] - box[0]) / 1920.0, 0.42)

    def test_extend_complete_mid_line_does_not_right_walk_into_wood(self) -> None:
        """Final glyph-color pass must remove right wood without clipping text."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_box_to_ink,
            extend_hardsub_tracks_to_ink,
            tighten_hardsub_box_to_neutral_glyphs,
        )

        frame = np.full((1080, 1920, 3), 25, dtype=np.uint8)
        # Complete centered burn-in (w≈0.32).
        for x in range(650, 1260, 8):
            frame[1016:1050, x : x + 5] = 240
            frame[1016:1050, x + 5 : x + 8] = 20
        # High-contrast food/wood texture immediately to the right.
        rng = np.random.default_rng(1)
        for x in range(1270, 1920):
            v = int(30 + 40 * np.sin(x / 3.0) + int(rng.integers(-15, 16)))
            v = max(0, min(255, v))
            frame[1010:1060, x] = (v, v // 2, 20)
        for x in range(1270, 1920, 4):
            frame[1016:1050, x : x + 2] = (190, 75, 24)
            frame[1016:1050, x + 2 : x + 4] = (28, 12, 6)

        seed = [651.0, 1016.0, 1260.0, 1053.0]
        extended = extend_hardsub_box_to_ink(
            frame, seed, frame_w=1920, frame_h=1080
        )
        tightened = tighten_hardsub_box_to_neutral_glyphs(
            frame,
            extended,
            frame_w=1920,
            frame_h=1080,
        )
        self.assertIsNotNone(tightened)
        assert tightened is not None
        self.assertLessEqual(tightened[2], 1320.0)
        self.assertGreaterEqual(tightened[2], 1250.0)
        self.assertLess((tightened[2] - tightened[0]) / 1920.0, 0.38)
        track = MergedTrack(
            start_frame=3,
            end_frame=7,
            box_coords=list(seed),
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(955.5, 1034.5),
            hit_count=3,
            hit_boxes=[tuple(seed)] * 3,
            hit_frames=[4, 5, 6],
            hit_sharpness=[18.0, 20.0, 19.0],
        )
        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={4: frame, 5: frame, 6: frame},
            frame_w=1920,
            frame_h=1080,
        )
        self.assertLessEqual(out[0].box_coords[2], 1320.0)

    def test_neutral_glyph_tighten_keeps_full_long_line_beyond_seed(self) -> None:
        """A partial DBNet seed must not stop final glyph extent on a long line."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
            tighten_hardsub_box_to_neutral_glyphs,
        )

        frame = np.full((1080, 1920, 3), 28, dtype=np.uint8)
        # Full white/black-outline line 650..1450; the seed ends at 950.
        for x in range(650, 1450, 55):
            frame[1016:1050, x : x + 38] = 242
            frame[1014:1052, x : x + 2] = 8
            frame[1014:1052, x + 36 : x + 38] = 8
        tightened = tighten_hardsub_box_to_neutral_glyphs(
            frame,
            [90.0, 1008.0, 1600.0, 1060.0],
            frame_w=1920,
            frame_h=1080,
        )
        self.assertIsNotNone(tightened)
        assert tightened is not None
        self.assertLessEqual(tightened[0], 655.0)
        self.assertGreaterEqual(tightened[2], 1430.0)
        self.assertLessEqual(tightened[2], 1470.0)
        partial_seed = [90.0, 1008.0, 950.0, 1060.0]
        track = MergedTrack(
            start_frame=10,
            end_frame=20,
            box_coords=list(partial_seed),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(520.0, 1034.0),
            hit_count=3,
            hit_boxes=[tuple(partial_seed)] * 3,
            hit_frames=[14, 15, 16],
            hit_sharpness=[18.0, 20.0, 19.0],
        )
        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={14: frame, 15: frame, 16: frame},
            frame_w=1920,
            frame_h=1080,
        )
        self.assertGreaterEqual(out[0].box_coords[0], 620.0)
        self.assertGreaterEqual(out[0].box_coords[2], 1430.0)

    def test_short_neutral_subset_does_not_replace_most_detector_evidence(self) -> None:
        """A centered subset cannot prove it contains every glyph of a short line."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), (45, 70, 105), dtype=np.uint8)
        for x in range(870, 1240, 55):
            frame[1016:1050, x : x + 38] = 242
            frame[1014:1052, x : x + 2] = 8
            frame[1014:1052, x + 36 : x + 38] = 8
        seed = [100.0, 1000.0, 1600.0, 1060.0]
        track = MergedTrack(
            start_frame=10,
            end_frame=20,
            box_coords=list(seed),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(850.0, 1030.0),
            hit_count=3,
            hit_boxes=[tuple(seed)] * 3,
            hit_frames=[14, 15, 16],
            hit_sharpness=[18.0, 20.0, 19.0],
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={14: frame, 15: frame, 16: frame},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertLessEqual(out[0].box_coords[0], 150.0)
        self.assertGreaterEqual(out[0].box_coords[2], 1550.0)

    def test_neutral_body_does_not_clip_colored_prefix_from_detector_line(self) -> None:
        """A large neutral subset still cannot discard supported prefix glyphs."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        for x in range(680, 775, 46):
            frame[1018:1050, x : x + 32] = (0, 220, 220)
            frame[1016:1052, x : x + 2] = 5
            frame[1016:1052, x + 30 : x + 32] = 5
        for x in range(775, 1230, 46):
            frame[1018:1050, x : x + 32] = 242
            frame[1016:1052, x : x + 2] = 5
            frame[1016:1052, x + 30 : x + 32] = 5

        detector_line = (670.0, 1014.0, 1245.0, 1055.0)
        hit_frames = list(range(10, 22))
        track = MergedTrack(
            start_frame=10,
            end_frame=21,
            box_coords=list(detector_line),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(957.5, 1034.5),
            hit_count=len(hit_frames),
            hit_boxes=[detector_line] * len(hit_frames),
            hit_frames=hit_frames,
            hit_sharpness=[20.0] * len(hit_frames),
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in hit_frames},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertLessEqual(out[0].box_coords[0], 700.0)
        self.assertGreaterEqual(out[0].box_coords[2], 1225.0)

    def test_dense_detector_consensus_wins_over_one_sided_edge_ink_balloon(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        # Saturated caption glyphs: valid stroke ink, intentionally outside the
        # neutral-glyph shortcut used by other regression tests.
        for x in range(630, 1320, 52):
            frame[1016:1048, x : x + 34] = (0, 220, 220)
            frame[1014:1050, x : x + 2] = 5
            frame[1014:1050, x + 32 : x + 34] = 5
        # High-contrast scene texture at the right edge tempts ink extension.
        for x in range(1730, 1912, 18):
            frame[1015:1049, x : x + 5] = 245

        detector_box = (620.0, 1008.0, 1320.0, 1050.0)
        track = MergedTrack(
            start_frame=10,
            end_frame=21,
            box_coords=[490.0, 1006.0, 1911.0, 1050.0],
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(1200.5, 1028.0),
            hit_count=12,
            hit_boxes=[detector_box] * 12,
            hit_frames=list(range(10, 22)),
            hit_sharpness=[20.0] * 12,
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in range(10, 22)},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertLess(out[0].box_coords[2], 1500.0)
        self.assertGreater(out[0].box_coords[2], 1280.0)

    def test_dense_detector_consensus_blocks_new_one_sided_edge_ink_balloon(self) -> None:
        """Scene ink must not widen a detector-tight segment to the frame edge."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        for x in range(630, 1320, 52):
            frame[1016:1048, x : x + 34] = (0, 220, 220)
            frame[1014:1050, x : x + 2] = 5
            frame[1014:1050, x + 32 : x + 34] = 5
        # A near-continuous high-contrast surface begins at the last glyph and
        # reaches the right edge. This reproduces food/plate texture being
        # accepted as an extension even though every detector frame agrees on
        # the complete, centered caption line.
        for x in range(1300, 1912, 12):
            frame[1015:1049, x : x + 8] = 245

        detector_box = (620.0, 1008.0, 1320.0, 1050.0)
        track = MergedTrack(
            start_frame=10,
            end_frame=21,
            box_coords=list(detector_box),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(970.0, 1029.0),
            hit_count=12,
            hit_boxes=[detector_box] * 12,
            hit_frames=list(range(10, 22)),
            hit_sharpness=[20.0] * 12,
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in range(10, 22)},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertLess(out[0].box_coords[2], 1500.0)
        self.assertGreater(out[0].box_coords[2], 1280.0)

    def test_dense_detector_core_rejects_disjoint_ink_relocation(self) -> None:
        """A short dense caption must not teleport into stronger edge texture."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        # A complete short centered caption (about 17% of frame width).
        for x in range(800, 1125, 48):
            frame[1002:1048, x : x + 32] = (0, 220, 220)
            frame[1000:1050, x : x + 2] = 5
            frame[1000:1050, x + 30 : x + 32] = 5
        # Strong cutting-board/food texture is spatially disjoint but reaches
        # the frame edge in the same lower band.
        for x in range(1220, 1920, 12):
            frame[985:1035, x : x + 8] = 245

        detector_box = (796.0, 1000.0, 1128.0, 1052.0)
        hit_frames = list(range(10, 30))
        track = MergedTrack(
            start_frame=10,
            end_frame=29,
            box_coords=list(detector_box),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(962.0, 1026.0),
            hit_count=len(hit_frames),
            hit_boxes=[detector_box] * len(hit_frames),
            hit_frames=hit_frames,
            hit_sharpness=[20.0] * len(hit_frames),
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in hit_frames},
            frame_w=1920,
            frame_h=1080,
        )

        box = out[0].box_coords
        self.assertLess(box[0], 900.0)
        self.assertGreater(box[2], 1100.0)
        self.assertLess(box[2], 1300.0)
        self.assertGreater(box[1], 990.0)

    def test_dense_short_core_rejects_one_sided_texture_balloon(self) -> None:
        """Dense four-character captions must not absorb a wide food band."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        for x in range(836, 1098, 44):
            frame[1002:1049, x : x + 30] = (0, 220, 220)
            frame[1000:1051, x : x + 2] = 5
            frame[1000:1051, x + 28 : x + 30] = 5
        # Same-band sauce/food texture attaches only on the right. It does not
        # reach the frame edge, so the general edge guard cannot catch it.
        for x in range(1100, 1615, 12):
            frame[997:1057, x : x + 8] = 245

        detector_box = (835.0, 1001.0, 1098.0, 1051.0)
        hit_frames = list(range(10, 40))
        track = MergedTrack(
            start_frame=10,
            end_frame=61,
            box_coords=list(detector_box),
            best_frame_index=25,
            best_sharpness=20.0,
            centroid=(966.5, 1026.0),
            hit_count=len(hit_frames),
            hit_boxes=[detector_box] * len(hit_frames),
            hit_frames=hit_frames,
            hit_sharpness=[20.0] * len(hit_frames),
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in hit_frames},
            frame_w=1920,
            frame_h=1080,
        )

        box = out[0].box_coords
        self.assertLess(box[0], 900.0)
        self.assertGreater(box[2], 1050.0)
        self.assertLess(box[2], 1250.0)

    def test_dense_mid_width_core_rejects_two_sided_pan_texture_balloon(self) -> None:
        """Ink projection cannot double a dense caption using pan texture."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        core = (640.0, 991.0, 1142.0, 1049.0)
        balloon = [530.0, 987.0, 1535.0, 1055.0]
        hit_frames = list(range(818, 856))
        track = MergedTrack(
            start_frame=818,
            end_frame=855,
            box_coords=list(core),
            best_frame_index=850,
            best_sharpness=20.0,
            centroid=(891.0, 1020.0),
            hit_count=len(hit_frames),
            hit_boxes=[core] * len(hit_frames),
            hit_frames=hit_frames,
            hit_sharpness=[20.0] * len(hit_frames),
        )
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        module = "src.media_pipeline.frame_sampling.master_phase1_extractor."
        with (
            patch(module + "extend_hardsub_box_to_ink", return_value=balloon),
            patch(module + "trim_hardsub_box_to_ink", return_value=balloon),
            patch(module + "trim_hardsub_box_y_to_ink", return_value=balloon),
            patch(module + "tighten_hardsub_box_to_neutral_glyphs", return_value=None),
        ):
            out = extend_hardsub_tracks_to_ink(
                [track],
                frame_cache={850: frame},
                frame_w=1920,
                frame_h=1080,
            )

        self.assertEqual(
            out[0].box_coords,
            [core[0], balloon[1], core[2], balloon[3]],
        )

    def test_raw_dense_coverage_is_final_x_authority_after_track_pollution(self) -> None:
        """Pre-merge coverage corrects a synthetic box no detector repeated."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            DetectionHit,
            MergedTrack,
            constrain_hardsubs_to_dense_detector_coverage,
        )

        core = (812.0, 1003.0, 1113.0, 1052.0)
        balloon = [438.0, 1001.0, 1414.0, 1051.0]
        frames = list(range(196, 220))
        track = MergedTrack(
            start_frame=196,
            end_frame=219,
            box_coords=list(balloon),
            best_frame_index=214,
            best_sharpness=20.0,
            centroid=(926.0, 1026.0),
            hit_count=80,
            hit_boxes=[tuple(balloon)] * 80,
            hit_frames=frames,
            hit_sharpness=[20.0] * 80,
        )
        hits = [
            DetectionHit(frame_index, core, 20.0) for frame_index in frames
        ]

        out, audit = constrain_hardsubs_to_dense_detector_coverage(
            [track], hits, frame_w=1920, frame_h=1080
        )

        self.assertEqual(
            out[0].box_coords,
            [core[0], balloon[1], core[2], balloon[3]],
        )
        self.assertEqual(audit["adjusted_tracks"], 1)

    def test_raw_dense_coverage_keeps_repeated_outer_detector_geometry(self) -> None:
        """Per-frame outer evidence keeps a genuinely long caption complete."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            DetectionHit,
            MergedTrack,
            constrain_hardsubs_to_dense_detector_coverage,
        )

        core = (780.0, 1002.0, 1120.0, 1052.0)
        full_line = [450.0, 999.0, 1470.0, 1055.0]
        frames = list(range(10, 30))
        hits = [DetectionHit(frame_index, core, 20.0) for frame_index in frames]
        hits.extend(
            DetectionHit(frame_index, tuple(full_line), 20.0)
            for frame_index in frames[:14]
        )
        track = MergedTrack(
            start_frame=10,
            end_frame=29,
            box_coords=list(full_line),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(960.0, 1027.0),
            hit_count=len(hits),
            hit_boxes=[hit.box_xyxy for hit in hits],
            hit_frames=[hit.frame_index for hit in hits],
            hit_sharpness=[20.0] * len(hits),
        )

        out, audit = constrain_hardsubs_to_dense_detector_coverage(
            [track], hits, frame_w=1920, frame_h=1080
        )

        self.assertEqual(out[0].box_coords, full_line)
        self.assertEqual(audit["adjusted_tracks"], 0)

    def test_detector_core_recovers_prefix_around_partial_neutral_glyph_anchor(self) -> None:
        """A scene-attached DBNet slab must not beat nested caption detections."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        # Saturated prefix: detector sees it, while the neutral-glyph pass is
        # intentionally unable to use it as direct color evidence.
        for x in range(630, 830, 48):
            frame[1016:1048, x : x + 32] = (0, 220, 220)
            frame[1014:1050, x : x + 2] = 5
            frame[1014:1050, x + 30 : x + 32] = 5
        # Neutral body provides a stable anchor for the real editor caption.
        for x in range(830, 1275, 48):
            frame[1016:1048, x : x + 32] = 242
            frame[1014:1050, x : x + 2] = 5
            frame[1014:1050, x + 30 : x + 32] = 5
        # Independent scene label/texture on the right is sometimes merged by
        # DBNet into the same wide box as the caption.
        for x in range(1600, 1780, 16):
            frame[1015:1049, x : x + 7] = 245

        caption_box = (614.0, 1008.0, 1290.0, 1050.0)
        attached_slab = (614.0, 1008.0, 1782.0, 1050.0)
        hit_boxes = [attached_slab] * 12 + [caption_box] * 8
        hit_frames = list(range(10, 30))
        track = MergedTrack(
            start_frame=10,
            end_frame=29,
            box_coords=list(attached_slab),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(1198.0, 1020.0),
            hit_count=len(hit_boxes),
            hit_boxes=hit_boxes,
            hit_frames=hit_frames,
            hit_sharpness=[20.0] * len(hit_boxes),
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in hit_frames},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertLessEqual(out[0].box_coords[0], 650.0)
        self.assertGreaterEqual(out[0].box_coords[2], 1270.0)
        self.assertLess(out[0].box_coords[2], 1400.0)

    def test_partial_detector_core_does_not_clip_real_glyphs_on_both_sides(self) -> None:
        """A centered neutral subset cannot replace a complete two-sided line."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        # Saturated glyphs on both outer sides are valid caption ink but cannot
        # participate in the neutral-color shortcut.
        for x in list(range(510, 700, 48)) + list(range(1300, 1590, 48)):
            frame[1016:1048, x : x + 32] = (0, 220, 220)
            frame[1014:1050, x : x + 2] = 5
            frame[1014:1050, x + 30 : x + 32] = 5
        for x in range(700, 1300, 48):
            frame[1016:1048, x : x + 32] = 242
            frame[1014:1050, x : x + 2] = 5
            frame[1014:1050, x + 30 : x + 32] = 5

        full_line = (490.0, 1008.0, 1640.0, 1050.0)
        partial_core = (650.0, 1008.0, 1310.0, 1050.0)
        hit_boxes = [partial_core] * 12 + [full_line] * 8
        hit_frames = list(range(10, 30))
        track = MergedTrack(
            start_frame=10,
            end_frame=29,
            box_coords=list(full_line),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(1065.0, 1029.0),
            hit_count=len(hit_boxes),
            hit_boxes=hit_boxes,
            hit_frames=hit_frames,
            hit_sharpness=[20.0] * len(hit_boxes),
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in hit_frames},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertLess(out[0].box_coords[0], 550.0)
        self.assertGreater(out[0].box_coords[2], 1550.0)

    def test_dense_centered_core_replaces_extreme_two_sided_ink_balloon(self) -> None:
        """An extreme box unsupported outside a dense glyph core must shrink."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        for x in range(370, 1785, 16):
            frame[1000:1051, x : x + 7] = (0, 120, 240)
            frame[998:1053, x : x + 2] = 5
        for x in range(805, 1120, 48):
            frame[1001:1050, x : x + 32] = 242
            frame[998:1053, x : x + 3] = 5
            frame[998:1053, x + 29 : x + 32] = 5
        # Scene texture on both sides makes ink projection retain an enormous
        # crop, but no detector frame supports it as part of the caption.

        detector_core = (800.0, 998.0, 1115.0, 1053.0)
        balloon = (373.0, 998.0, 1787.0, 1053.0)
        core_frames = list(range(10, 27))
        auxiliary_frames = list(range(10, 30))
        hit_frames = core_frames + auxiliary_frames
        hit_boxes = [detector_core] * len(core_frames) + [balloon] * len(
            auxiliary_frames
        )
        track = MergedTrack(
            start_frame=10,
            end_frame=29,
            box_coords=list(balloon),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(1080.0, 1025.5),
            hit_count=len(hit_frames),
            hit_boxes=hit_boxes,
            hit_frames=hit_frames,
            hit_sharpness=[20.0] * len(hit_frames),
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in hit_frames},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertGreater(out[0].box_coords[0], 760.0)
        self.assertLess(out[0].box_coords[2], 1160.0)

    def test_dense_centered_core_blocks_new_extreme_two_sided_ink_balloon(self) -> None:
        """The current call must not create an extreme box around a tight seed."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
        for x in range(370, 1785, 16):
            frame[1000:1051, x : x + 7] = (0, 120, 240)
            frame[998:1053, x : x + 2] = 5
        for x in range(805, 1120, 48):
            frame[1001:1050, x : x + 32] = 242
            frame[998:1053, x : x + 3] = 5
            frame[998:1053, x + 29 : x + 32] = 5

        detector_core = (800.0, 998.0, 1115.0, 1053.0)
        hit_frames = list(range(10, 30))
        track = MergedTrack(
            start_frame=10,
            end_frame=29,
            box_coords=list(detector_core),
            best_frame_index=15,
            best_sharpness=20.0,
            centroid=(957.5, 1025.5),
            hit_count=len(hit_frames),
            hit_boxes=[detector_core] * len(hit_frames),
            hit_frames=hit_frames,
            hit_sharpness=[20.0] * len(hit_frames),
        )

        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={fi: frame for fi in hit_frames},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertGreater(out[0].box_coords[0], 760.0)
        self.assertLess(out[0].box_coords[2], 1160.0)

    def test_extend_skips_mid_label_role(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            extend_hardsub_box_to_ink,
        )

        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        seed = (300.0, 480.0, 450.0, 560.0)
        out = extend_hardsub_box_to_ink(frame, seed)
        self.assertEqual(out, [300.0, 480.0, 450.0, 560.0])

    def test_hardsub_stable_box_uses_expansive_x1(self) -> None:
        """Median locks truncated width; hardsub must prefer high-percentile x1."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            stable_box_xyxy,
        )

        boxes = [(10.0, 930.0, 600.0, 980.0)] * 8 + [(10.0, 930.0, 980.0, 980.0)] * 2
        med = stable_box_xyxy(boxes)
        exp = stable_box_xyxy(boxes, expansive=True)
        self.assertLess(med[2], 650.0)
        self.assertGreater(exp[2], 850.0)


class FinalizePreOcrTests(unittest.TestCase):
    def test_shrink_removes_pad_bleed(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            shrink_track_to_evidence,
        )

        track = MergedTrack(
            start_frame=48,
            end_frame=54,
            box_coords=[100.0, 900.0, 200.0, 940.0],
            best_frame_index=50,
            best_sharpness=10.0,
            centroid=(150.0, 920.0),
            hit_count=2,
            hit_boxes=[(100.0, 900.0, 200.0, 940.0), (100.0, 900.0, 200.0, 940.0)],
            hit_frames=[50, 52],
            hit_sharpness=[10.0, 12.0],
        )
        out = shrink_track_to_evidence(track, frame_count=844, pad=1)
        self.assertEqual((out.start_frame, out.end_frame), (49, 53))

    def test_split_breaks_centroid_jump(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            split_overmerged_tracks,
        )

        # Same "merged" track but boxes jump mid-way (over-merge artifact).
        boxes = [(100.0, 900.0, 300.0, 940.0)] * 5 + [(800.0, 900.0, 1000.0, 940.0)] * 5
        frames = list(range(10, 20))
        track = MergedTrack(
            start_frame=8,
            end_frame=21,
            box_coords=list(boxes[0]),
            best_frame_index=10,
            best_sharpness=10.0,
            centroid=(200.0, 920.0),
            hit_count=10,
            hit_boxes=[tuple(b) for b in boxes],
            hit_frames=frames,
            hit_sharpness=[10.0] * 10,
        )
        parts = split_overmerged_tracks([track])
        self.assertGreaterEqual(len(parts), 2)

    def test_split_breaks_hardsub_width_jump(self) -> None:
        """Over-merged bottom lines with a sharp width step must split at the jump."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            split_overmerged_tracks,
        )

        short = (500.0, 1000.0, 900.0, 1048.0)
        long = (350.0, 1000.0, 1550.0, 1048.0)
        boxes = [short] * 4 + [long] * 4
        frames = [100, 102, 104, 106, 110, 112, 114, 116]
        track = MergedTrack(
            start_frame=98,
            end_frame=118,
            box_coords=list(long),
            best_frame_index=112,
            best_sharpness=12.0,
            centroid=(950.0, 1024.0),
            hit_count=8,
            hit_boxes=[tuple(b) for b in boxes],
            hit_frames=frames,
            hit_sharpness=[10.0] * 8,
        )
        parts = split_overmerged_tracks([track], frame_count=200)
        self.assertGreaterEqual(len(parts), 2)
        widths = sorted(float(t.box_coords[2]) - float(t.box_coords[0]) for t in parts)
        self.assertLess(widths[0], 500.0)
        self.assertGreater(widths[-1], 1000.0)

    def test_chrome_edge_tiny_purged(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            is_chrome_noise_box,
            purge_chrome_tracks,
            MergedTrack,
        )

        # True right-edge strip stub (Douyin chrome), not an interior list chip.
        edge = (1880.0, 752.0, 1910.0, 788.0)
        self.assertTrue(is_chrome_noise_box(edge, frame_w=1920, frame_h=1080))
        self.assertFalse(
            is_chrome_noise_box((80.0, 900.0, 900.0, 960.0), frame_w=1920, frame_h=1080)
        )
        # Interior compact name chips (shrimp-class, w≈31) must survive chrome purge.
        shrimp = (153.6, 566.4, 182.4, 606.0)
        self.assertFalse(
            is_chrome_noise_box(shrimp, frame_w=1920, frame_h=1080)
        )
        tiny = MergedTrack(
            start_frame=0,
            end_frame=5,
            box_coords=list(edge),
            best_frame_index=2,
            best_sharpness=1.0,
            centroid=(1895.0, 770.0),
            hit_count=3,
            hit_boxes=[edge] * 3,
            hit_frames=[1, 2, 3],
            hit_sharpness=[1.0, 1.0, 1.0],
        )
        kept, purged = purge_chrome_tracks([tiny], frame_w=1920, frame_h=1080)
        self.assertEqual(kept, [])
        self.assertEqual(len(purged), 1)

    def test_chrome_edge_text_survives_dense_full_width_editor_grid(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            purge_chrome_tracks,
            MergedTrack,
        )

        def track(box: tuple[float, float, float, float]) -> MergedTrack:
            return MergedTrack(
                start_frame=720,
                end_frame=745,
                box_coords=list(box),
                best_frame_index=730,
                best_sharpness=10.0,
                centroid=((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
                hit_count=24,
                hit_boxes=[box] * 24,
                hit_frames=list(range(722, 746)),
                hit_sharpness=[10.0] * 24,
            )

        edge_value = track((1800.0, 230.0, 1889.0, 260.0))
        grid = [
            edge_value,
            track((1790.0, 174.0, 1890.0, 201.0)),
            track((1790.0, 288.0, 1890.0, 315.0)),
            track((1100.0, 174.0, 1168.0, 201.0)),
            track((1100.0, 288.0, 1168.0, 315.0)),
            track((150.0, 620.0, 235.0, 647.0)),
            track((150.0, 850.0, 265.0, 883.0)),
        ]

        kept, purged = purge_chrome_tracks(
            grid, frame_w=1920, frame_h=1080
        )

        self.assertIn(edge_value, kept)
        self.assertNotIn(edge_value, purged)

    def test_thin_percent_hits_not_absorbed_by_tall_column(self) -> None:
        """Tall %% union must not IoU-absorb thinner row hits into one locus."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            DetectionHit,
            merge_tracks_by_centroid,
        )

        tall = (1098.0, 170.0, 1170.0, 316.0)
        thin21 = (1100.0, 226.0, 1168.0, 258.0)
        # IoU(tall, thin) ≈ 0.21 ≥ MIN_MERGE_IOU — height gate must block merge.
        self.assertEqual(
            len(
                merge_tracks_by_centroid(
                    [
                        DetectionHit(700, tall, 10.0),
                        DetectionHit(702, thin21, 10.0),
                    ],
                    frame_count=800,
                )
            ),
            2,
        )
        hits = [
            DetectionHit(700, tall, 10.0),
            DetectionHit(702, thin21, 10.0),
            DetectionHit(704, (1098.0, 286.0, 1170.0, 316.0), 10.0),
            DetectionHit(706, thin21, 10.0),
            DetectionHit(708, (1098.0, 286.0, 1170.0, 316.0), 10.0),
            DetectionHit(710, (1098.0, 170.0, 1170.0, 200.0), 10.0),
            DetectionHit(712, thin21, 10.0),
            DetectionHit(714, (1098.0, 286.0, 1170.0, 316.0), 10.0),
        ]
        tracks = merge_tracks_by_centroid(hits, frame_count=800)
        thin = [
            t
            for t in tracks
            if (float(t.box_coords[3]) - float(t.box_coords[1])) < 50.0
        ]
        self.assertGreaterEqual(
            len(thin),
            2,
            msg=f"expected separate thin %% rows, got {[t.box_coords for t in tracks]}",
        )
        self.assertTrue(
            any(int(t.hit_count) >= 3 for t in thin),
            msg=f"thin rows starved: {[(t.hit_count, t.box_coords) for t in thin]}",
        )

    def test_finalize_pipeline_records_audit(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            finalize_confirmed_tracks,
        )

        hits = [
            DetectionHit(10, (100.0, 900.0, 300.0, 940.0), 10.0),
            DetectionHit(11, (100.0, 900.0, 300.0, 940.0), 11.0),
            DetectionHit(12, (100.0, 900.0, 300.0, 940.0), 12.0),
            # chrome (true right-edge strip)
            DetectionHit(20, (1880.0, 752.0, 1910.0, 788.0), 5.0),
            DetectionHit(21, (1880.0, 752.0, 1910.0, 788.0), 5.0),
        ]
        merged = merge_tracks_by_centroid(
            hits, frame_count=100, pad=PADDING, max_centroid_px=20.0
        )
        kept, _ = confirm_tracks(merged, min_hits=2)
        final, audit = finalize_confirmed_tracks(
            kept, frame_count=100, frame_w=1920, frame_h=1080
        )
        self.assertEqual(len(final), 1)
        self.assertGreaterEqual(audit["purged_chrome"], 1)
        self.assertIn("shrunk", audit)
        self.assertLessEqual(final[0].end_frame - final[0].start_frame, 6)


class BoundaryQualityTests(unittest.TestCase):
    def test_perspective_ui_cohort_rescues_phone_micro_text(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            isolated_micro_source_text_member_ids,
            perspective_ui_provenance_member_ids,
        )

        boxes = [
            (80.0, 180.0, 120.0, 205.0),
            (880.0, 230.0, 930.0, 260.0),
            (1080.0, 310.0, 1135.0, 340.0),
            (1280.0, 390.0, 1340.0, 420.0),
            (1480.0, 470.0, 1540.0, 500.0),
            (1650.0, 550.0, 1710.0, 580.0),
            (1780.0, 630.0, 1840.0, 660.0),
        ]
        tracks: list[MergedTrack] = []
        for index, box in enumerate(boxes):
            hit_boxes = [
                (box[0] + frame * 2.0, box[1], box[2] + frame * 2.0, box[3])
                for frame in range(6)
            ]
            tracks.append(
                MergedTrack(
                    10,
                    15,
                    list(box),
                    12,
                    15.0,
                    ((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
                    6,
                    hit_boxes,
                    list(range(10, 16)),
                    [15.0] * 6,
                )
            )

        perspective = perspective_ui_provenance_member_ids(
            tracks, frame_w=1920, frame_h=1080
        )
        isolated = isolated_micro_source_text_member_ids(
            tracks, frame_w=1920, frame_h=1080
        )

        self.assertIn(id(tracks[0]), perspective)
        self.assertNotIn(id(tracks[0]), isolated)

    def test_scene_adjacent_perspective_cohort_rescues_early_phone_ui(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            isolated_micro_source_text_member_ids,
            perspective_ui_provenance_member_ids,
        )

        def track(start: int, end: int, box: tuple[float, ...]) -> MergedTrack:
            frames = list(range(start, end + 1))
            return MergedTrack(
                start,
                end,
                list(box),
                start,
                10.0,
                ((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
                len(frames),
                [box] * len(frames),
                frames,
                [10.0] * len(frames),
            )

        candidate = track(4, 6, (870.0, 996.0, 913.0, 1029.0))
        phone_rows = [
            track(35, 50, (120.0, 420.0, 190.0, 470.0)),
            track(35, 50, (180.0, 740.0, 250.0, 770.0)),
            track(35, 50, (260.0, 500.0, 330.0, 550.0)),
            track(35, 50, (300.0, 600.0, 365.0, 650.0)),
        ]
        tracks = [candidate, *phone_rows]

        perspective = perspective_ui_provenance_member_ids(
            tracks, frame_w=1920, frame_h=1080
        )
        isolated = isolated_micro_source_text_member_ids(
            tracks, frame_w=1920, frame_h=1080
        )

        self.assertIn(id(candidate), perspective)
        self.assertNotIn(id(candidate), isolated)

    def test_three_adjacent_fragments_do_not_rescue_appliance_micro_text(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            isolated_micro_source_text_member_ids,
            perspective_ui_provenance_member_ids,
        )

        def track(box: tuple[float, ...]) -> MergedTrack:
            return MergedTrack(
                10,
                14,
                list(box),
                12,
                10.0,
                ((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
                5,
                [box] * 5,
                list(range(10, 15)),
                [10.0] * 5,
            )

        appliance = track((1636.0, 934.0, 1673.0, 948.0))
        fragments = [
            track((100.0, 200.0, 150.0, 230.0)),
            track((500.0, 400.0, 550.0, 430.0)),
            track((900.0, 600.0, 950.0, 630.0)),
        ]
        tracks = [appliance, *fragments]

        perspective = perspective_ui_provenance_member_ids(
            tracks, frame_w=1920, frame_h=1080
        )
        isolated = isolated_micro_source_text_member_ids(
            tracks, frame_w=1920, frame_h=1080
        )

        self.assertNotIn(id(appliance), perspective)
        self.assertIn(id(appliance), isolated)

    def test_final_reconciliation_trims_isolated_sparse_outlier_cluster(self) -> None:
        box = (804.0, 644.0, 1125.0, 697.0)
        track = MergedTrack(
            start_frame=0,
            end_frame=11,
            box_coords=list(box),
            best_frame_index=0,
            best_sharpness=20.0,
            centroid=(964.5, 670.5),
            hit_count=4,
            hit_boxes=[box] * 4,
            hit_frames=[0, 1, 2, 9],
            hit_sharpness=[20.0, 19.0, 18.0, 5.0],
        )

        reconciled, audit = reconcile_final_tracks_with_coverage(
            [track],
            [],
            frame_count=20,
            frame_w=1920,
            frame_h=1080,
        )

        self.assertEqual((reconciled[0].start_frame, reconciled[0].end_frame), (0, 2))
        self.assertEqual(reconciled[0].hit_frames, [0, 1, 2])
        evidence = __import__(
            "src.media_pipeline.frame_sampling.master_phase1_extractor",
            fromlist=["track_boundary_evidence"],
        ).track_boundary_evidence(reconciled[0], frame_w=1920, frame_h=1080)
        self.assertEqual(evidence["status"], "confirmed")
        self.assertEqual(audit["sparse_clusters_trimmed"], 1)

    def test_final_reconciliation_extends_short_contiguous_hardsub_fade_tail(self) -> None:
        final_box = (610.0, 1003.0, 1311.0, 1056.0)
        track = MergedTrack(
            start_frame=5,
            end_frame=10,
            box_coords=list(final_box),
            best_frame_index=8,
            best_sharpness=30.0,
            centroid=(960.5, 1029.5),
            hit_count=6,
            hit_boxes=[final_box] * 6,
            hit_frames=list(range(5, 11)),
            hit_sharpness=[30.0] * 6,
        )
        fade_box = (690.0, 956.0, 960.0, 1004.0)
        raw_hits = [
            DetectionHit(frame, fade_box, 12.0)
            for frame in (11, 12, 13, 14, 15)
        ]

        reconciled, audit = reconcile_final_tracks_with_coverage(
            [track],
            raw_hits,
            frame_count=20,
            frame_w=1920,
            frame_h=1080,
        )

        self.assertEqual((reconciled[0].start_frame, reconciled[0].end_frame), (5, 15))
        self.assertEqual(reconciled[0].hit_frames[-5:], [11, 12, 13, 14, 15])
        self.assertEqual(audit["coverage_edges_extended"], 1)
        self.assertEqual(audit["coverage_frames_added"], 5)

    def test_final_reconciliation_does_not_join_persistent_next_caption(self) -> None:
        final_box = (610.0, 1003.0, 1311.0, 1056.0)
        track = MergedTrack(
            start_frame=5,
            end_frame=10,
            box_coords=list(final_box),
            best_frame_index=8,
            best_sharpness=30.0,
            centroid=(960.5, 1029.5),
            hit_count=6,
            hit_boxes=[final_box] * 6,
            hit_frames=list(range(5, 11)),
            hit_sharpness=[30.0] * 6,
        )
        next_caption_box = (690.0, 956.0, 960.0, 1004.0)
        raw_hits = [
            DetectionHit(frame, next_caption_box, 12.0)
            for frame in range(11, 18)
        ]

        reconciled, audit = reconcile_final_tracks_with_coverage(
            [track],
            raw_hits,
            frame_count=20,
            frame_w=1920,
            frame_h=1080,
        )

        self.assertEqual((reconciled[0].start_frame, reconciled[0].end_frame), (5, 10))
        self.assertEqual(audit["coverage_edges_extended"], 0)

    def test_purges_short_unseparable_hardsub_shadow_beside_verified_host(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            purge_hardsub_shadows_by_boundary_audit,
        )

        host_box = (580.0, 1009.0, 1340.0, 1052.0)
        shadow_box = (585.0, 991.0, 1420.0, 1017.0)
        host = MergedTrack(
            1, 71, list(host_box), 30, 20.0, (960.0, 1030.5), 71,
            [host_box] * 71, list(range(1, 72)), [20.0] * 71,
        )
        shadow = MergedTrack(
            10, 18, list(shadow_box), 14, 10.0, (1002.5, 1004.0), 9,
            [shadow_box] * 9, list(range(10, 19)), [10.0] * 9,
        )
        audits = [
            {"applied": True, "reason": "verified"},
            {
                "applied": True,
                "reason": "dense_detector_evidence",
                "fallback_from": "template_not_separable",
                "positive_floor": 0.9764,
                "negative_ceiling": 0.9715,
            },
        ]

        kept, kept_audits = purge_hardsub_shadows_by_boundary_audit(
            [host, shadow], audits, frame_w=1920, frame_h=1080
        )

        self.assertEqual(kept, [host])
        self.assertEqual(kept_audits, [audits[0]])

    def test_keeps_verified_second_hardsub_line(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            purge_hardsub_shadows_by_boundary_audit,
        )

        host_box = (580.0, 1009.0, 1340.0, 1052.0)
        second_box = (620.0, 960.0, 1300.0, 1002.0)
        host = MergedTrack(
            1, 71, list(host_box), 30, 20.0, (960.0, 1030.5), 71,
            [host_box] * 71, list(range(1, 72)), [20.0] * 71,
        )
        second = MergedTrack(
            10, 18, list(second_box), 14, 10.0, (960.0, 981.0), 9,
            [second_box] * 9, list(range(10, 19)), [10.0] * 9,
        )
        audits = [
            {"applied": True, "reason": "verified"},
            {"applied": True, "reason": "verified"},
        ]

        kept, kept_audits = purge_hardsub_shadows_by_boundary_audit(
            [host, second], audits, frame_w=1920, frame_h=1080
        )

        self.assertEqual(kept, [host, second])
        self.assertEqual(kept_audits, audits)

    def test_template_boundary_refiner_recovers_fades_and_removes_blind_pad(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            refine_track_boundaries_by_template,
        )

        frames: dict[int, np.ndarray] = {}
        for frame_index in range(12):
            frame = np.full((120, 240, 3), 25, dtype=np.uint8)
            if 3 <= frame_index <= 7:
                value = 160 if frame_index in {3, 7} else 240
                # Static editor glyph pattern. Frames 3/7 simulate fade edges.
                for x in range(70, 170, 16):
                    frame[82:105, x : x + 9] = value
                    frame[82:105, x + 9 : x + 12] = 10
            frames[frame_index] = frame

        track = MergedTrack(
            start_frame=2,  # old blind temporal pad
            end_frame=8,
            box_coords=[66.0, 78.0, 174.0, 108.0],
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(120.0, 93.0),
            hit_count=3,
            hit_boxes=[(66.0, 78.0, 174.0, 108.0)] * 3,
            hit_frames=[4, 5, 6],
            hit_sharpness=[18.0, 20.0, 19.0],
        )
        refined, audit = refine_track_boundaries_by_template(
            track,
            frame_cache=frames,
            frame_count=12,
            frame_w=240,
            frame_h=120,
            search_radius=4,
        )
        self.assertEqual((refined.start_frame, refined.end_frame), (3, 7))
        self.assertTrue(audit["applied"])
        self.assertEqual(audit["observed_hit_span"], [4, 6])
        self.assertEqual(audit["refined_span"], [3, 7])

    def test_boundary_evidence_flags_sparse_track_for_review(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            track_boundary_evidence,
        )

        track = MergedTrack(
            start_frame=10,
            end_frame=30,
            box_coords=[20.0, 80.0, 180.0, 105.0],
            best_frame_index=20,
            best_sharpness=10.0,
            centroid=(100.0, 92.5),
            hit_count=3,
            hit_boxes=[(20.0, 80.0, 180.0, 105.0)] * 3,
            hit_frames=[10, 20, 30],
            hit_sharpness=[10.0] * 3,
        )
        evidence = track_boundary_evidence(track, frame_w=240, frame_h=120)
        self.assertEqual(evidence["status"], "uncertain")
        self.assertGreaterEqual(evidence["max_internal_gap"], 9)
        self.assertIn("sparse_temporal_evidence", evidence["reasons"])

    def test_boundary_evidence_distinguishes_safe_margin_from_clipped_edge(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            track_boundary_evidence,
        )

        def dense_track(x0: float) -> MergedTrack:
            return MergedTrack(
                start_frame=10,
                end_frame=19,
                box_coords=[x0, 80.0, 260.0, 125.0],
                best_frame_index=14,
                best_sharpness=10.0,
                centroid=((x0 + 260.0) * 0.5, 102.5),
                hit_count=10,
                hit_boxes=[(x0, 80.0, 260.0, 125.0)] * 10,
                hit_frames=list(range(10, 20)),
                hit_sharpness=[10.0] * 10,
            )

        safe = track_boundary_evidence(
            dense_track(11.0), frame_w=1920, frame_h=1080
        )
        clipped = track_boundary_evidence(
            dense_track(1.0), frame_w=1920, frame_h=1080
        )

        self.assertEqual(safe["status"], "confirmed")
        self.assertNotIn("frame_edge_box_review", safe["reasons"])
        self.assertEqual(clipped["status"], "confirmed")
        self.assertTrue(clipped["source_intrinsic_clip"])
        self.assertNotIn("frame_edge_box_review", clipped["reasons"])

        sparse_edge_track = dense_track(1.0)
        sparse_edge_track.hit_count = 2
        sparse_edge_track.hit_boxes = sparse_edge_track.hit_boxes[:2]
        sparse_edge_track.hit_frames = [10, 19]
        sparse_edge_track.hit_sharpness = sparse_edge_track.hit_sharpness[:2]
        sparse = track_boundary_evidence(
            sparse_edge_track, frame_w=1920, frame_h=1080
        )
        self.assertEqual(sparse["status"], "uncertain")
        self.assertFalse(sparse["source_intrinsic_clip"])
        self.assertIn("frame_edge_box_review", sparse["reasons"])

    def test_dense_thin_portrait_line_is_not_uncertain_only_for_width(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            track_boundary_evidence,
        )

        box = [100.0, 1000.0, 930.0, 1042.0]
        track = MergedTrack(
            start_frame=10,
            end_frame=49,
            box_coords=box,
            best_frame_index=30,
            best_sharpness=10.0,
            centroid=(515.0, 1021.0),
            hit_count=40,
            hit_boxes=[tuple(box)] * 40,
            hit_frames=list(range(10, 50)),
            hit_sharpness=[10.0] * 40,
        )

        evidence = track_boundary_evidence(track, frame_w=1080, frame_h=1920)

        self.assertEqual(evidence["status"], "confirmed")
        self.assertNotIn("wide_box_review", evidence["reasons"])

    def test_boundary_refiner_uses_dense_hit_span_when_template_is_ambiguous(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            refine_track_boundaries_by_template,
        )

        # Identical background/text-like texture makes template separation
        # ambiguous. Dense STEP=1 hits remain stronger than blind ±2 padding.
        frame = np.full((120, 240, 3), 80, dtype=np.uint8)
        for x in range(70, 170, 12):
            frame[82:105, x : x + 6] = 220
        frames = {index: frame.copy() for index in range(30)}
        track = MergedTrack(
            start_frame=8,
            end_frame=16,
            box_coords=[66.0, 78.0, 174.0, 108.0],
            best_frame_index=12,
            best_sharpness=20.0,
            centroid=(120.0, 93.0),
            hit_count=5,
            hit_boxes=[(66.0, 78.0, 174.0, 108.0)] * 5,
            hit_frames=[10, 11, 12, 13, 14],
            hit_sharpness=[20.0] * 5,
        )
        refined, audit = refine_track_boundaries_by_template(
            track,
            frame_cache=frames,
            frame_count=30,
            frame_w=240,
            frame_h=120,
        )
        self.assertEqual((refined.start_frame, refined.end_frame), (10, 14))
        self.assertTrue(audit["applied"])
        self.assertEqual(audit["reason"], "dense_detector_evidence")


class ResidualHardsubRecoveryTests(unittest.TestCase):
    @staticmethod
    def _frames(indices: range) -> dict[int, np.ndarray]:
        return {
            frame_index: np.full((120, 240, 3), 127, dtype=np.uint8)
            for frame_index in indices
        }

    def test_recovers_short_bottom_caption_with_local_text_consensus(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("\u65b0\u5b57\u5e55", 0.98, 1.0) for _ in crops]

        hits = [
            DetectionHit(frame, (40.0, 98.0, 200.0, 115.0), 20.0)
            for frame in range(9, 14)
        ]
        recovered, audit = recover_residual_hardsub_tracks(
            [],
            hits,
            frame_cache=self._frames(range(9, 14)),
            frame_count=30,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(recovered), 1)
        self.assertEqual((recovered[0].start_frame, recovered[0].end_frame), (9, 13))
        self.assertEqual(audit["recovered_track_count"], 1)
        self.assertEqual(audit["unresolved_spans"], [])

    def test_fade_ghost_without_text_is_not_recovered(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("", 0.0, 0.0) for _ in crops]

        hits = [
            DetectionHit(frame, (50.0, 100.0, 190.0, 118.0), 5.0)
            for frame in range(3, 6)
        ]
        recovered, audit = recover_residual_hardsub_tracks(
            [],
            hits,
            frame_cache=self._frames(range(3, 6)),
            frame_count=20,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(recovered, [])
        self.assertEqual(audit["recovered_track_count"], 0)
        self.assertEqual(audit["unresolved_spans"], [[3, 5, 3]])

    def test_adjacent_shadow_requires_an_active_caption_host(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("", 0.0, 0.0) for _ in crops]

        host_box = (35.0, 96.0, 205.0, 116.0)
        host = MergedTrack(
            10,
            14,
            list(host_box),
            12,
            20.0,
            (120.0, 106.0),
            5,
            [host_box] * 5,
            list(range(10, 15)),
            [20.0] * 5,
        )
        shadow_hits = [
            DetectionHit(frame, (65.0, 112.0, 150.0, 120.0), 4.0)
            for frame in range(10, 13)
        ]
        with_host, host_audit = recover_residual_hardsub_tracks(
            [host],
            shadow_hits,
            frame_cache=self._frames(range(10, 13)),
            frame_count=30,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )
        without_host, no_host_audit = recover_residual_hardsub_tracks(
            [],
            shadow_hits,
            frame_cache=self._frames(range(10, 13)),
            frame_count=30,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(with_host, [host])
        self.assertEqual(host_audit["explained_shadow_frames"], [10, 11, 12])
        self.assertEqual(host_audit["unresolved_spans"], [])
        self.assertEqual(without_host, [])
        self.assertEqual(no_host_audit["unresolved_spans"], [[10, 12, 3]])

    def test_real_second_line_is_recovered_even_beside_active_host(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("\u7b2c\u4e8c\u884c", 0.97, 1.0) for _ in crops]

        host_box = (40.0, 94.0, 200.0, 108.0)
        host = MergedTrack(
            20,
            24,
            list(host_box),
            22,
            20.0,
            (120.0, 101.0),
            5,
            [host_box] * 5,
            list(range(20, 25)),
            [20.0] * 5,
        )
        second_line = [
            DetectionHit(frame, (55.0, 106.0, 185.0, 119.0), 18.0)
            for frame in range(20, 25)
        ]
        tracks, audit = recover_residual_hardsub_tracks(
            [host],
            second_line,
            frame_cache=self._frames(range(20, 25)),
            frame_count=40,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(tracks), 2)
        self.assertEqual(audit["recovered_track_count"], 1)
        self.assertEqual(audit["explained_shadow_frames"], [])


class ContentAwareSegmentationTests(unittest.TestCase):
    @staticmethod
    def _track() -> MergedTrack:
        return MergedTrack(
            start_frame=1,
            end_frame=10,
            box_coords=[20.0, 70.0, 220.0, 105.0],
            best_frame_index=3,
            best_sharpness=20.0,
            centroid=(120.0, 87.5),
            hit_count=10,
            hit_boxes=[(20.0, 70.0, 220.0, 105.0)] * 10,
            hit_frames=list(range(1, 11)),
            hit_sharpness=[float(fi) for fi in range(1, 11)],
        )

    @staticmethod
    def _frames() -> dict[int, np.ndarray]:
        frames: dict[int, np.ndarray] = {}
        for fi in range(1, 11):
            frame = np.zeros((120, 240, 3), dtype=np.uint8)
            frame[70:105, 20:220] = fi
            frames[fi] = frame
        return frames

    def test_splits_same_geometry_when_local_text_changes(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "第一句字幕" if fi <= 4 else "" if fi == 5 else "第二句字幕"
                    out.append(LocalRecognition(text, 0.95 if text else 0.0, 1.0 if text else 0.0))
                return out

        split, audit = split_tracks_by_local_text_change(
            [self._track()],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual([(t.start_frame, t.end_frame) for t in split], [(1, 4), (6, 10)])
        self.assertEqual([t.hit_frames for t in split], [list(range(1, 5)), list(range(6, 11))])
        self.assertEqual(audit["split_tracks"], 1)
        self.assertEqual(audit["segments_created"], 2)

    def test_single_frame_ocr_glitch_does_not_create_false_segment(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "错误噪声" if fi == 5 else "同一句字幕"
                    out.append(LocalRecognition(text, 0.95, 1.0))
                return out

        split, audit = split_tracks_by_local_text_change(
            [self._track()],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(split), 1)
        self.assertEqual((split[0].start_frame, split[0].end_frame), (1, 10))
        self.assertEqual(audit["split_tracks"], 0)

    def test_measurement_label_ocr_variants_do_not_split_one_editor_chip(self) -> None:
        """250g仁/230g仁/250g虾仁 are one static ingredient label."""
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "250g仁" if fi <= 4 else "230g仁" if fi <= 6 else "250g虾仁"
                    out.append(LocalRecognition(text, 0.99, 1.0))
                return out

        frames = {
            fi: np.full((120, 240, 3), fi, dtype=np.uint8)
            for fi in range(1, 11)
        }
        box = (40.0, 60.0, 105.0, 80.0)
        track = MergedTrack(
            start_frame=1,
            end_frame=10,
            box_coords=list(box),
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(72.5, 70.0),
            hit_count=10,
            hit_boxes=[box] * 10,
            hit_frames=list(range(1, 11)),
            hit_sharpness=[20.0] * 10,
        )

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(split), 1)
        self.assertEqual((split[0].start_frame, split[0].end_frame), (1, 10))
        self.assertEqual(audit["split_tracks"], 0)

    def test_distinct_measured_ingredient_labels_still_split(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "250g虾仁" if fi <= 5 else "150g里脊肉"
                    out.append(LocalRecognition(text, 0.99, 1.0))
                return out

        frames = {
            fi: np.full((120, 240, 3), fi, dtype=np.uint8)
            for fi in range(1, 11)
        }
        box = (40.0, 60.0, 105.0, 80.0)
        track = MergedTrack(
            start_frame=1,
            end_frame=10,
            box_coords=list(box),
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(72.5, 70.0),
            hit_count=10,
            hit_boxes=[box] * 10,
            hit_frames=list(range(1, 11)),
            hit_sharpness=[20.0] * 10,
        )

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(
            [(row.start_frame, row.end_frame) for row in split],
            [(1, 5), (6, 10)],
        )
        self.assertEqual(audit["split_tracks"], 1)

    def test_overlapping_ocr_variants_do_not_block_caption_split(self) -> None:
        """Near-identical interleaved OCR variants must not keep a stale parent track."""
        class FakeRecognizer:
            def recognize_batch(self, crops: list[LocalRecognition]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    if fi <= 5:
                        text = "第一段字幕"
                    elif fi <= 15:
                        text = "萌们先用膨胀色" if fi % 2 == 0 else "咱们先用膨胀色"
                    else:
                        text = "第二段字幕"
                    out.append(LocalRecognition(text, 0.95, 1.0))
                return out

        frames = {
            fi: np.full((120, 240, 3), fi, dtype=np.uint8)
            for fi in range(1, 31)
        }
        track = self._track()
        track.end_frame = 30
        track.hit_boxes = [(20.0, 70.0, 220.0, 105.0)] * 30
        track.hit_frames = list(range(1, 31))
        track.hit_sharpness = [float(fi) for fi in range(1, 31)]
        track.hit_count = 30

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(
            [(row.start_frame, row.end_frame) for row in split],
            [(1, 5), (6, 15), (16, 30)],
        )
        self.assertEqual(audit["split_tracks"], 1)
        self.assertEqual(audit["coalesced_overlapping_content_variants"], 1)

    def test_small_nested_ocr_glitch_does_not_block_real_caption_splits(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    if fi <= 10:
                        text = "错误噪声内容" if 6 <= fi <= 7 else "第一段稳定字幕"
                    else:
                        text = "第二段稳定字幕"
                    out.append(LocalRecognition(text, 0.95, 1.0))
                return out

        frames: dict[int, np.ndarray] = {}
        for fi in range(1, 21):
            frames[fi] = np.full((120, 240, 3), fi, dtype=np.uint8)
        track = self._track()
        track.end_frame = 20
        track.hit_boxes = [(20.0, 70.0, 220.0, 105.0)] * 20
        track.hit_frames = list(range(1, 21))
        track.hit_sharpness = [float(fi) for fi in range(1, 21)]
        track.hit_count = 20

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(
            [(row.start_frame, row.end_frame) for row in split],
            [(1, 10), (11, 20)],
        )
        self.assertEqual(audit["suppressed_nested_ocr_glitches"], 1)

    def test_trims_detector_tail_when_ocr_proves_text_is_gone(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "片头标题" if fi <= 4 else ""
                    out.append(LocalRecognition(text, 0.95 if text else 0.0, 1.0 if text else 0.0))
                return out

        split, audit = split_tracks_by_local_text_change(
            [self._track()],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(split), 1)
        self.assertEqual((split[0].start_frame, split[0].end_frame), (1, 4))
        self.assertEqual(split[0].hit_frames, [1, 2, 3, 4])
        self.assertEqual(audit["trimmed_tracks"], 1)

    def test_short_track_uses_two_dense_ocr_frames_to_trim_blank_lead(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "首先准备牛肉" if fi >= 5 else ""
                    out.append(LocalRecognition(text, 0.95 if text else 0.0, 1.0 if text else 0.0))
                return out

        track = self._track()
        track.end_frame = 6
        track.hit_boxes = track.hit_boxes[:6]
        track.hit_frames = track.hit_frames[:6]
        track.hit_sharpness = track.hit_sharpness[:6]
        track.hit_count = 6

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual([(row.start_frame, row.end_frame) for row in split], [(5, 6)])
        self.assertEqual(audit["trimmed_tracks"], 1)

    def test_short_stable_track_adds_ocr_positive_frames_to_boundary_evidence(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("短字幕证据", 0.95, 1.0) for _ in crops]

        track = self._track()
        track.end_frame = 6
        track.hit_boxes = track.hit_boxes[1:3]
        track.hit_frames = [2, 3]
        track.hit_sharpness = [2.0, 3.0]
        track.hit_count = 2

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual([(row.start_frame, row.end_frame) for row in split], [(1, 6)])
        self.assertEqual(sorted(set(split[0].hit_frames)), list(range(1, 7)))
        self.assertEqual(audit["rows"][0]["action"], "timing_seed")

    def test_drops_sparse_blank_hardsub_shadow_beside_dense_caption(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [
                    LocalRecognition("真实字幕内容" if int(crop[0, 0, 0]) == 1 else "", 0.95, 1.0)
                    for crop in crops
                ]

        frames: dict[int, np.ndarray] = {}
        for fi in range(1, 11):
            frame = np.zeros((120, 240, 3), dtype=np.uint8)
            frame[112:120, 50:190] = 1
            frames[fi] = frame

        shadow_box = (30.0, 104.0, 210.0, 112.0)
        caption_box = (50.0, 112.0, 190.0, 120.0)
        shadow = MergedTrack(
            start_frame=1,
            end_frame=10,
            box_coords=list(shadow_box),
            best_frame_index=5,
            best_sharpness=10.0,
            centroid=(120.0, 108.0),
            hit_count=3,
            hit_boxes=[shadow_box] * 3,
            hit_frames=[2, 6, 9],
            hit_sharpness=[10.0] * 3,
        )
        caption = MergedTrack(
            start_frame=1,
            end_frame=10,
            box_coords=list(caption_box),
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(120.0, 116.0),
            hit_count=10,
            hit_boxes=[caption_box] * 10,
            hit_frames=list(range(1, 11)),
            hit_sharpness=[20.0] * 10,
        )

        split, audit = split_tracks_by_local_text_change(
            [shadow, caption],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(split, [caption])
        self.assertEqual(audit["dropped_sparse_hardsub_shadows"], 1)

    def test_drops_ocr_only_segment_without_detector_seed(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "八楼" if fi <= 2 else ""
                    out.append(LocalRecognition(text, 0.95 if text else 0.0, 1.0 if text else 0.0))
                return out

        frames = {
            fi: np.full((120, 240, 3), fi, dtype=np.uint8)
            for fi in range(1, 8)
        }
        box = (170.0, 30.0, 220.0, 60.0)
        track = MergedTrack(
            start_frame=1,
            end_frame=7,
            box_coords=list(box),
            best_frame_index=5,
            best_sharpness=10.0,
            centroid=(195.0, 45.0),
            hit_count=3,
            hit_boxes=[box] * 3,
            hit_frames=[4, 5, 6],
            hit_sharpness=[10.0] * 3,
        )

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(split, [])
        self.assertEqual(audit["dropped_ocr_only_segments"], 1)

    def test_drops_edge_padded_wide_hardsub_without_multiframe_text_consensus(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("", 0.0, 0.0) for _ in crops]

        track = self._track()
        track.box_coords = [0.0, 106.0, 180.0, 118.0]

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(split, [])
        self.assertEqual(audit["dropped_unverified_edge_hardsubs"], 1)
        self.assertEqual(audit["rows"][0]["action"], "drop_unverified_edge_hardsub")

    def test_keeps_edge_aligned_hardsub_with_multiframe_text_consensus(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("左对齐字幕", 0.95, 1.0) for _ in crops]

        track = self._track()
        track.box_coords = [0.0, 106.0, 180.0, 118.0]

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(split), 1)
        self.assertEqual((split[0].start_frame, split[0].end_frame), (1, 10))
        self.assertEqual(audit["dropped_unverified_edge_hardsubs"], 0)

    def test_hardsub_bare_digits_do_not_create_a_false_caption_segment(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "收汁到汤汁浓稠" if fi <= 8 else "88"
                    out.append(LocalRecognition(text, 0.95, 1.0))
                return out

        track = self._track()
        track.box_coords = [20.0, 106.0, 220.0, 118.0]
        frames = self._frames()
        for fi, frame in frames.items():
            frame[106:118, 20:220] = fi

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual([(row.start_frame, row.end_frame) for row in split], [(1, 8)])
        self.assertEqual(audit["split_tracks"], 0)

    def test_drops_sparse_compact_texture_with_intermittent_ocr_acceptance(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    confidence = 0.90 if fi in {1, 3, 5, 7} else 0.75
                    out.append(LocalRecognition("福", confidence, 1.0))
                return out

        track = self._track()
        track.box_coords = [145.0, 78.0, 160.0, 84.0]
        track.hit_boxes = [(145.0, 78.0, 160.0, 84.0)] * 3
        track.hit_frames = [1, 2, 10]
        track.hit_sharpness = [3.0, 2.0, 1.0]
        track.hit_count = 3

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(split, [])
        self.assertEqual(audit["dropped_unverified_sparse_compact_tracks"], 1)

    def test_keeps_sparse_compact_real_single_glyph_with_multiframe_consensus(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("盐", 0.92, 1.0) for _ in crops]

        track = self._track()
        track.box_coords = [145.0, 78.0, 160.0, 84.0]
        track.hit_boxes = [(145.0, 78.0, 160.0, 84.0)] * 3
        track.hit_frames = [1, 2, 10]
        track.hit_sharpness = [3.0, 2.0, 1.0]
        track.hit_count = 3

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(split), 1)
        self.assertEqual(audit["dropped_unverified_sparse_compact_tracks"], 0)

    def test_drops_sparse_tiny_track_split_into_near_duplicate_ocr_variants(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "刃移动" if fi <= 2 else "刀移动" if fi <= 5 else "勿移动"
                    out.append(LocalRecognition(text, 0.95, 1.0))
                return out

        track = self._track()
        track.box_coords = [145.0, 58.0, 155.0, 62.0]
        track.hit_boxes = [(145.0, 58.0, 155.0, 62.0)] * 4
        track.hit_frames = [1, 2, 9, 10]
        track.hit_sharpness = [4.0, 3.0, 2.0, 1.0]
        track.hit_count = 4
        frames = self._frames()
        for fi, frame in frames.items():
            frame[:] = fi

        split, audit = split_tracks_by_local_text_change(
            [track],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(split, [])
        self.assertEqual(audit["dropped_sparse_variant_scene_tracks"], 1)

    def test_drops_nearby_ambiguous_scene_tracks_seeded_by_sparse_motion(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    fi = int(crop[0, 0, 0])
                    text = "气瓶导向片对正" if fi % 2 else "汽瓶导网片寿正"
                    out.append(LocalRecognition(text, 0.95, 1.0))
                return out

        sparse = self._track()
        sparse.box_coords = [150.0, 65.0, 205.0, 75.0]
        sparse.hit_boxes = [(150.0, 65.0, 205.0, 75.0)] * 3
        sparse.hit_frames = [1, 2, 10]
        sparse.hit_sharpness = [3.0, 2.0, 1.0]
        sparse.hit_count = 3
        companion = self._track()
        companion.box_coords = [145.0, 78.0, 195.0, 86.0]
        frames = self._frames()
        for fi, frame in frames.items():
            frame[:] = fi

        split, audit = split_tracks_by_local_text_change(
            [sparse, companion],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(split, [])
        self.assertEqual(audit["dropped_ambiguous_scene_tracks"], 2)


class PostRefinementSparseCompactFilterTests(unittest.TestCase):
    @staticmethod
    def _track() -> MergedTrack:
        box = (145.0, 78.0, 160.0, 84.0)
        return MergedTrack(
            start_frame=1,
            end_frame=10,
            box_coords=list(box),
            best_frame_index=2,
            best_sharpness=10.0,
            centroid=(152.5, 81.0),
            hit_count=3,
            hit_boxes=[box] * 3,
            hit_frames=[1, 2, 10],
            hit_sharpness=[10.0, 9.0, 8.0],
        )

    @staticmethod
    def _frames() -> dict[int, np.ndarray]:
        frames: dict[int, np.ndarray] = {}
        for frame_index in range(1, 11):
            frame = np.zeros((120, 240, 3), dtype=np.uint8)
            frame[78:84, 145:160] = frame_index
            frames[frame_index] = frame
        return frames

    def test_drops_sparse_compact_texture_after_geometry_refinement(self) -> None:
        class FakeRecognizer:
            def recognize_batch(
                self, crops: list[np.ndarray]
            ) -> list[LocalRecognition]:
                out: list[LocalRecognition] = []
                for crop in crops:
                    frame_index = int(crop[0, 0, 0])
                    text = "\u798f" if frame_index in {1, 3, 5, 7} else ""
                    out.append(
                        LocalRecognition(
                            text,
                            0.90 if text else 0.0,
                            1.0 if text else 0.0,
                        )
                    )
                return out

        kept, audit = purge_unverified_sparse_compact_tracks_after_refinement(
            [self._track()],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(kept, [])
        self.assertEqual(audit["candidate_count"], 1)
        self.assertEqual(audit["dropped_tracks"], 1)
        self.assertEqual(
            audit["rows"][0]["action"],
            "drop_unverified_sparse_compact_after_refinement",
        )
        self.assertFalse(audit["rows"][0]["clusters"][0]["stable"])

    def test_keeps_real_single_glyph_with_lifespan_consensus(self) -> None:
        class FakeRecognizer:
            def recognize_batch(
                self, crops: list[np.ndarray]
            ) -> list[LocalRecognition]:
                return [
                    LocalRecognition("\u76d0", 0.92, 1.0) for _ in crops
                ]

        track = self._track()
        kept, audit = purge_unverified_sparse_compact_tracks_after_refinement(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(kept, [track])
        self.assertEqual(audit["dropped_tracks"], 0)
        self.assertEqual(
            audit["rows"][0]["action"], "keep_stable_text_consensus"
        )
        self.assertTrue(audit["rows"][0]["clusters"][0]["stable"])
        self.assertEqual(audit["rows"][0]["clusters"][0]["detector_overlap"], 3)

    def test_stable_ocr_hallucination_on_low_detail_food_texture_is_dropped(
        self,
    ) -> None:
        class HallucinatingRecognizer:
            def recognize_batch(
                self, crops: list[np.ndarray]
            ) -> list[LocalRecognition]:
                return [
                    LocalRecognition("\u798f", 0.95, 1.0) for _ in crops
                ]

        frames = {
            frame_index: np.full(
                (120, 240, 3), (20, 55, 210), dtype=np.uint8
            )
            for frame_index in range(1, 11)
        }
        kept, audit = purge_unverified_sparse_compact_tracks_after_refinement(
            [self._track()],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=HallucinatingRecognizer(),
        )

        self.assertEqual(kept, [])
        row = audit["rows"][0]
        self.assertTrue(row["clusters"][0]["stable"])
        self.assertTrue(
            row["visual_evidence"]["low_detail_saturated_texture"]
        )
        self.assertEqual(
            row["reason"], "independent_low_detail_saturated_texture_veto"
        )

    def test_sharp_overlay_on_saturated_background_is_not_texture_vetoed(
        self,
    ) -> None:
        class StableRecognizer:
            def recognize_batch(
                self, crops: list[np.ndarray]
            ) -> list[LocalRecognition]:
                return [
                    LocalRecognition("\u76d0", 0.95, 1.0) for _ in crops
                ]

        frames: dict[int, np.ndarray] = {}
        for frame_index in range(1, 11):
            frame = np.full((120, 240, 3), (20, 55, 210), dtype=np.uint8)
            frame[78:84, 146:148] = 255
            frame[78:84, 152:154] = 255
            frame[80:82, 145:160] = 255
            frames[frame_index] = frame

        track = self._track()
        kept, audit = purge_unverified_sparse_compact_tracks_after_refinement(
            [track],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=StableRecognizer(),
        )

        self.assertEqual(kept, [track])
        row = audit["rows"][0]
        self.assertFalse(
            row["visual_evidence"]["low_detail_saturated_texture"]
        )
        self.assertEqual(row["action"], "keep_stable_text_consensus")

    def test_noncompact_sparse_track_remains_operator_reviewable(self) -> None:
        class BlankRecognizer:
            def recognize_batch(
                self, crops: list[np.ndarray]
            ) -> list[LocalRecognition]:
                return [LocalRecognition("", 0.0, 0.0) for _ in crops]

        track = self._track()
        track.box_coords = [100.0, 78.0, 160.0, 84.0]
        kept, audit = purge_unverified_sparse_compact_tracks_after_refinement(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=BlankRecognizer(),
        )

        self.assertEqual(kept, [track])
        self.assertEqual(audit["candidate_count"], 0)
        self.assertEqual(audit["rows"], [])

    def test_recognizer_error_fails_soft_to_operator_review(self) -> None:
        class BrokenRecognizer:
            def recognize_batch(
                self, crops: list[np.ndarray]
            ) -> list[LocalRecognition]:
                raise RuntimeError("offline")

        track = self._track()
        kept, audit = purge_unverified_sparse_compact_tracks_after_refinement(
            [track],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=BrokenRecognizer(),
        )

        self.assertEqual(kept, [track])
        self.assertEqual(audit["dropped_tracks"], 0)
        self.assertEqual(
            audit["rows"][0]["reason"], "recognizer_error_fail_soft"
        )


class ContentAwareCoalesceTests(unittest.TestCase):
    @staticmethod
    def _track(start: int, end: int, box: list[float]) -> MergedTrack:
        frames = list(range(start, end + 1))
        return MergedTrack(
            start_frame=start,
            end_frame=end,
            box_coords=box,
            best_frame_index=frames[len(frames) // 2],
            best_sharpness=20.0,
            centroid=((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
            hit_count=len(frames),
            hit_boxes=[tuple(box)] * len(frames),
            hit_frames=frames,
            hit_sharpness=[20.0] * len(frames),
        )

    @staticmethod
    def _frames() -> dict[int, np.ndarray]:
        return {
            fi: np.zeros((120, 240, 3), dtype=np.uint8)
            for fi in range(1, 11)
        }

    def test_merges_overlapping_and_adjacent_geometry_fragments_with_same_text(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                results: list[LocalRecognition] = []
                for crop in crops:
                    # First geometry fragment has two stable OCR substitutions;
                    # the overlapping peer and adjacent continuation read cleanly.
                    if crop.shape[1] < 160:
                        text = "错误识别文字内容多"
                    else:
                        text = "淋上蒜末葱花小米辣"
                    results.append(LocalRecognition(text, 0.95, 1.0))
                return results

        tracks = [
            self._track(1, 5, [20.0, 106.0, 150.0, 118.0]),
            self._track(4, 6, [40.0, 106.0, 225.0, 118.0]),
            self._track(7, 10, [5.0, 106.0, 205.0, 118.0]),
        ]

        merged, audit = coalesce_tracks_by_local_text_content(
            tracks,
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
            geometry_normalized=True,
        )

        self.assertEqual(len(merged), 1, msg=str(audit))
        self.assertEqual((merged[0].start_frame, merged[0].end_frame), (1, 10))
        self.assertEqual(merged[0].box_coords[0], 20.0)
        self.assertEqual(merged[0].box_coords[2], 150.0)
        self.assertEqual(audit["merged_tracks"], 2)

    def test_pre_ink_same_text_keeps_nested_dense_hardsub_core(self) -> None:
        """A same-content recovery balloon may add timing, never X padding."""
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("中途翻面", 0.95, 1.0) for _ in crops]

        narrow = [82.0, 106.0, 142.0, 118.0]
        balloon = [75.0, 106.0, 220.0, 118.0]
        merged, audit = coalesce_tracks_by_local_text_content(
            [self._track(1, 10, narrow), self._track(2, 10, balloon)],
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(merged), 1, msg=str(audit))
        self.assertEqual((merged[0].start_frame, merged[0].end_frame), (1, 10))
        self.assertEqual(merged[0].box_coords, narrow)
        self.assertTrue(audit["rows"][0]["normalized_box_used"])

    def test_does_not_merge_adjacent_geometry_when_text_changes(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [
                    LocalRecognition(
                        "第一句字幕" if crop.shape[1] < 150 else "第二句字幕",
                        0.95,
                        1.0,
                    )
                    for crop in crops
                ]

        tracks = [
            self._track(1, 5, [20.0, 90.0, 140.0, 110.0]),
            self._track(6, 10, [20.0, 88.0, 200.0, 112.0]),
        ]

        merged, audit = coalesce_tracks_by_local_text_content(
            tracks,
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual(audit["merged_tracks"], 0)

    def test_does_not_merge_distinct_ui_columns_when_ocr_crop_reads_same_text(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("same ui row", 0.95, 1.0) for _ in crops]

        tracks = [
            self._track(1, 10, [20.0, 20.0, 100.0, 40.0]),
            self._track(1, 10, [60.0, 20.0, 140.0, 40.0]),
        ]

        merged, audit = coalesce_tracks_by_local_text_content(
            tracks,
            frame_cache=self._frames(),
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(merged), 2, msg=str(audit))
        self.assertEqual(audit["merged_tracks"], 0)

    def test_merges_temporally_contained_nested_ui_text_fragment(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [
                    LocalRecognition(
                        "0卡糖2g" if crop.shape[1] > 150 else "卡糖",
                        0.95,
                        1.0,
                    )
                    for crop in crops
                ]

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frames = {frame_index: frame for frame_index in range(1, 11)}
        full_label = self._track(1, 10, [118.5, 465.6, 348.6, 530.25])
        nested_fragment = self._track(5, 8, [177.75, 474.06, 293.25, 511.05])

        merged, audit = coalesce_tracks_by_local_text_content(
            [full_label, nested_fragment],
            frame_cache=frames,
            frame_w=1920,
            frame_h=1080,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual(len(merged), 1, msg=str(audit))
        self.assertEqual((merged[0].start_frame, merged[0].end_frame), (1, 10))
        self.assertTrue(audit["rows"][0]["nested_ui_fragment_match"])


class NestedTemporalUiFragmentGuardTests(unittest.TestCase):
    @staticmethod
    def _track(start: int, end: int, box: list[float]) -> MergedTrack:
        frames = list(range(start, end + 1))
        return MergedTrack(
            start_frame=start,
            end_frame=end,
            box_coords=list(box),
            best_frame_index=frames[len(frames) // 2],
            best_sharpness=20.0,
            centroid=((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
            hit_count=len(frames),
            hit_boxes=[tuple(box)] * len(frames),
            hit_frames=frames,
            hit_sharpness=[20.0] * len(frames),
        )

    def test_drops_short_ui_fragment_inside_long_authority_without_ocr(self) -> None:
        authority = self._track(
            650, 815, [118.5, 465.6, 348.6, 530.25]
        )
        fragment = self._track(
            753, 772, [177.75, 474.06, 293.25, 511.05]
        )

        kept, audit = purge_temporally_nested_ui_fragments(
            [authority, fragment], frame_w=1920, frame_h=1080
        )

        self.assertEqual(kept, [authority])
        self.assertEqual(audit["dropped_tracks"], 1)
        self.assertEqual(audit["rows"][0]["candidate_span"], [753, 772])
        self.assertEqual(audit["rows"][0]["authority_span"], [650, 815])
        self.assertEqual(audit["rows"][0]["spatial_containment"], 1.0)

    def test_keeps_sequential_same_locus_text_transition(self) -> None:
        first = self._track(650, 700, [118.5, 465.6, 348.6, 530.25])
        second = self._track(701, 750, [177.75, 474.06, 293.25, 511.05])

        kept, audit = purge_temporally_nested_ui_fragments(
            [first, second], frame_w=1920, frame_h=1080
        )

        self.assertEqual(kept, [first, second])
        self.assertEqual(audit["dropped_tracks"], 0)

    def test_keeps_long_lived_nested_ui_value(self) -> None:
        authority = self._track(
            650, 815, [118.5, 465.6, 348.6, 530.25]
        )
        independent_value = self._track(
            680, 779, [177.75, 474.06, 293.25, 511.05]
        )

        kept, audit = purge_temporally_nested_ui_fragments(
            [authority, independent_value], frame_w=1920, frame_h=1080
        )

        self.assertEqual(kept, [authority, independent_value])
        self.assertEqual(audit["dropped_tracks"], 0)


class WideUiColumnSplitTests(unittest.TestCase):
    @staticmethod
    def _track(start: int, end: int, box: list[float]) -> MergedTrack:
        frames = list(range(start, end + 1))
        return MergedTrack(
            start_frame=start,
            end_frame=end,
            box_coords=box,
            best_frame_index=frames[len(frames) // 2],
            best_sharpness=20.0,
            centroid=((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5),
            hit_count=len(frames),
            hit_boxes=[tuple(box)] * len(frames),
            hit_frames=frames,
            hit_sharpness=[20.0] * len(frames),
        )

    @staticmethod
    def _frames() -> dict[int, np.ndarray]:
        return {
            frame_index: np.zeros((120, 240, 3), dtype=np.uint8)
            for frame_index in range(1, 11)
        }

    def test_splits_shallow_ui_box_at_large_blank_gutter(self) -> None:
        frame = np.full((1080, 1920, 3), 255, dtype=np.uint8)
        frame[220:250, 100:155] = 0
        frame[220:250, 265:345] = 0
        box = [80.0, 200.0, 360.0, 270.0]
        track = MergedTrack(
            start_frame=100,
            end_frame=123,
            box_coords=list(box),
            best_frame_index=110,
            best_sharpness=20.0,
            centroid=(220.0, 235.0),
            hit_count=24,
            hit_boxes=[tuple(box)] * 24,
            hit_frames=list(range(100, 124)),
            hit_sharpness=[20.0] * 24,
        )

        peers = [
            self._track(100, 123, [80.0, 80.0, 150.0, 110.0]),
            self._track(100, 123, [900.0, 90.0, 970.0, 120.0]),
            self._track(100, 123, [1700.0, 100.0, 1770.0, 130.0]),
            self._track(100, 123, [100.0, 500.0, 170.0, 530.0]),
            self._track(100, 123, [920.0, 520.0, 990.0, 550.0]),
            self._track(100, 123, [1680.0, 700.0, 1750.0, 730.0]),
        ]
        rows, audit = split_wide_ui_tracks_by_ink_columns(
            [track, *peers],
            frame_cache={110: frame},
            frame_w=1920,
            frame_h=1080,
        )

        self.assertEqual(len(rows), 8, msg=str(audit))
        children = [
            row for row in rows if getattr(row, "_ui_grid_split_child", False)
        ]
        self.assertEqual(len(children), 2)
        self.assertLess(children[0].box_coords[2], children[1].box_coords[0])
        self.assertEqual(audit["split_tracks"], 1)

    def test_does_not_split_latin_caption_words_without_dense_grid_peers(self) -> None:
        frame = np.full((1920, 1080, 3), 255, dtype=np.uint8)
        frame[1062:1106, 31:226] = 0
        frame[1062:1106, 243:323] = 0
        frame[1062:1106, 341:568] = 0
        caption = self._track(7, 86, [31.0, 1062.0, 568.0, 1106.0])

        rows, audit = split_wide_ui_tracks_by_ink_columns(
            [caption],
            frame_cache={caption.best_frame_index: frame},
            frame_w=1080,
            frame_h=1920,
        )

        self.assertEqual(len(rows), 1, msg=str(audit))
        self.assertEqual(rows[0].box_coords, caption.box_coords)
        self.assertEqual(audit["split_tracks"], 0)

    def test_merges_adjacent_same_row_when_one_ocr_crop_reads_only_prefix(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [
                    LocalRecognition(
                        "首先准备50克牛肉" if int(crop[0, 0, 0]) == 1 else "首先准备",
                        0.95,
                        1.0,
                    )
                    for crop in crops
                ]

        frames: dict[int, np.ndarray] = {}
        for fi in range(1, 9):
            frame = np.full((120, 240, 3), 1 if fi <= 2 else 2, dtype=np.uint8)
            frames[fi] = frame
        same_box = [20.0, 106.0, 220.0, 118.0]
        tracks = [
            self._track(1, 2, list(same_box)),
            self._track(3, 8, list(same_box)),
        ]

        merged, audit = coalesce_tracks_by_local_text_content(
            tracks,
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual([(row.start_frame, row.end_frame) for row in merged], [(1, 8)])
        self.assertEqual(audit["merged_tracks"], 1)

    def test_merges_overlapping_hardsub_when_one_crop_reads_short_prefix(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [
                    LocalRecognition(
                        "准备" if crop.shape[1] <= 105 else "准备一个不粘锅喷3克油",
                        0.95,
                        1.0,
                    )
                    for crop in crops
                ]

        frames = {
            fi: np.zeros((120, 240, 3), dtype=np.uint8)
            for fi in range(1, 11)
        }
        tracks = [
            self._track(1, 10, [0.0, 106.0, 100.0, 118.0]),
            self._track(1, 10, [70.0, 106.0, 230.0, 118.0]),
        ]

        merged, audit = coalesce_tracks_by_local_text_content(
            tracks,
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
            geometry_normalized=True,
        )

        self.assertEqual(len(merged), 1, msg=str(audit))
        self.assertEqual((merged[0].start_frame, merged[0].end_frame), (1, 10))
        self.assertEqual(audit["merged_tracks"], 1)

    def test_post_ink_does_not_merge_vertically_offset_hardsub_shadow(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [LocalRecognition("同一句稳定字幕", 0.95, 1.0) for _ in crops]

        frames = {
            fi: np.zeros((120, 240, 3), dtype=np.uint8)
            for fi in range(1, 11)
        }
        host = self._track(1, 10, [30.0, 106.0, 210.0, 118.0])
        upper_shadow = self._track(2, 4, [25.0, 102.0, 215.0, 110.0])

        merged, audit = coalesce_tracks_by_local_text_content(
            [host, upper_shadow],
            frame_cache=frames,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
            geometry_normalized=True,
        )

        self.assertEqual(len(merged), 2, msg=str(audit))
        self.assertEqual(audit["merged_tracks"], 0)


class ContentBoundaryExpansionTests(unittest.TestCase):
    def test_expands_hardsub_through_detector_gap_until_ocr_content_ends(self) -> None:
        class FakeRecognizer:
            def recognize_batch(self, crops: list[np.ndarray]) -> list[LocalRecognition]:
                return [
                    LocalRecognition(
                        "持续字幕内容" if int(crop[0, 0, 0]) == 1 else "",
                        0.95 if int(crop[0, 0, 0]) == 1 else 0.0,
                        1.0 if int(crop[0, 0, 0]) == 1 else 0.0,
                    )
                    for crop in crops
                ]

        frames: dict[int, np.ndarray] = {}
        for fi in range(10):
            frames[fi] = np.full(
                (120, 240, 3),
                1 if 1 <= fi <= 6 else 0,
                dtype=np.uint8,
            )
        box = [20.0, 106.0, 220.0, 118.0]
        track = MergedTrack(
            start_frame=1,
            end_frame=3,
            box_coords=list(box),
            best_frame_index=2,
            best_sharpness=20.0,
            centroid=(120.0, 112.0),
            hit_count=3,
            hit_boxes=[tuple(box)] * 3,
            hit_frames=[1, 2, 3],
            hit_sharpness=[18.0, 20.0, 19.0],
        )

        expanded, audit = expand_tracks_by_local_text_continuity(
            [track],
            frame_cache=frames,
            frame_count=10,
            frame_w=240,
            frame_h=120,
            recognizer=FakeRecognizer(),
        )

        self.assertEqual([(row.start_frame, row.end_frame) for row in expanded], [(1, 6)])
        self.assertEqual(sorted(set(expanded[0].hit_frames)), list(range(1, 7)))
        self.assertEqual(audit["expanded_tracks"], 1)


class TextFrameCoverageTests(unittest.TestCase):
    def test_coverage_lists_every_frame_with_a_hit(self) -> None:
        """Pre-gate coverage SSOT must not drop any detection frame index."""
        hits = [
            DetectionHit(10, (100.0, 900.0, 400.0, 940.0), 10.0),
            DetectionHit(11, (105.0, 900.0, 405.0, 940.0), 11.0),
            DetectionHit(50, (500.0, 200.0, 700.0, 260.0), 9.0),
            DetectionHit(50, (800.0, 1000.0, 1400.0, 1048.0), 12.0),
        ]
        cov = build_text_frame_coverage(
            hits, frame_count=100, frame_w=1920, frame_h=1080
        )
        self.assertEqual(cov["authority"], "master_phase1_detect")
        self.assertEqual(cov["frames_with_text"], [10, 11, 50])
        self.assertEqual(cov["n_frames_with_text"], 3)
        self.assertEqual(len(cov["by_frame"]["50"]), 2)
        # Gates / track merge must not be able to erase coverage — this artifact
        # is built only from raw hits.
        self.assertIn("boxes", cov["by_frame"]["10"][0])

    def test_timeline_entry_persists_hit_frames(self) -> None:
        entry = timeline_entry_dict(
            text_id="sub_01",
            start_frame=10,
            end_frame=20,
            fps=25.0,
            box_coords=[1.0, 2.0, 3.0, 4.0],
            best_keyframe_path="frames/sub_01.jpg",
            hit_count=3,
            hit_frames=[12, 14, 16],
        )
        self.assertEqual(entry["hit_frames"], [12, 14, 16])

    def test_qa_overlays_are_track_keyframes_not_coverage_frames(self) -> None:
        """qa/overlays stays 1 JPG/track (legacy); coverage must not dump tXXXXX.jpg there."""
        import tempfile

        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            write_phase1_qa_artifacts,
        )

        frame = np.zeros((108, 192, 3), dtype=np.uint8)
        frame[:] = (30, 30, 30)
        timeline = [
            {
                "text_id": "sub_01",
                "start_frame": 3,
                "end_frame": 5,
                "best_frame_index": 3,
                "best_keyframe_path": "frames/sub_01.jpg",
                "box_coords": [10.0, 20.0, 80.0, 50.0],
                "hit_count": 2,
            },
            {
                "text_id": "sub_02",
                "start_frame": 7,
                "end_frame": 9,
                "best_frame_index": 7,
                "best_keyframe_path": "frames/sub_02.jpg",
                "box_coords": [100.0, 60.0, 160.0, 90.0],
                "hit_count": 1,
            },
        ]
        cov = {
            "n_frames_with_text": 3,
            "frames_with_text": [3, 7, 9],
            "by_frame": {
                "3": [{"boxes": [10.0, 20.0, 80.0, 50.0], "role": "hardsub"}],
                "7": [{"boxes": [100.0, 60.0, 160.0, 90.0], "role": "hardsub"}],
                "9": [{"boxes": [40.0, 40.0, 90.0, 70.0], "role": "ui_chip"}],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames_dir = root / "frames"
            frames_dir.mkdir()
            qa_dir = root / "qa"
            for name in ("sub_01.jpg", "sub_02.jpg"):
                # Minimal valid JPEG via OpenCV path used by QA writer.
                import cv2

                cv2.imwrite(str(frames_dir / name), frame)
            summary = write_phase1_qa_artifacts(
                qa_dir=qa_dir,
                timeline=timeline,
                dropped=[],
                frame_count=10,
                frame_width=192,
                frame_height=108,
                frames_dir=frames_dir,
                frame_cache={3: frame, 7: frame, 9: frame},
                source=root / "missing.mp4",
                geometry_rejected=0,
                coarse_hits=0,
                phase_hits=0,
                dense_extra_frames=0,
                total_hits=0,
                text_coverage=cov,
                effective_step=2,
                effective_pad=2,
            )
            overlay_names = sorted(p.name for p in (qa_dir / "overlays").glob("*.jpg"))
            self.assertEqual(overlay_names, ["sub_01.jpg", "sub_02.jpg"])
            self.assertFalse((qa_dir / "overlays" / "t00003.jpg").exists())
            self.assertEqual(summary.get("overlays"), 2)
            # Coverage count may still be reported; must not drive overlay JPG count.
            self.assertEqual(summary.get("n_frames_with_text"), 3)
            uncertain_path = qa_dir / "uncertain_candidates.json"
            self.assertTrue(uncertain_path.is_file())
            boundary_names = sorted(
                p.name for p in (qa_dir / "boundaries").glob("*.jpg")
            )
            self.assertEqual(boundary_names, ["sub_01.jpg", "sub_02.jpg"])
            self.assertEqual(summary.get("boundary_overlays"), 2)
            boundary_crop_names = sorted(
                p.name for p in (qa_dir / "boundary_crops").glob("*.jpg")
            )
            self.assertEqual(boundary_crop_names, ["sub_01.jpg", "sub_02.jpg"])
            self.assertEqual(summary.get("boundary_crop_overlays"), 2)
            self.assertEqual(summary.get("boundary_source_tracks_skipped"), 0)
            self.assertEqual(summary["config"]["STEP"], 2)
            self.assertEqual(summary["config"]["PADDING"], 2)

    def test_boundary_qa_skips_protected_source_tracks(self) -> None:
        import tempfile
        import cv2

        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            write_phase1_qa_artifacts,
        )

        frame = np.zeros((108, 192, 3), dtype=np.uint8)
        timeline = [
            {
                "text_id": "editor_01",
                "start_frame": 1,
                "end_frame": 2,
                "best_frame_index": 1,
                "best_keyframe_path": "frames/editor_01.jpg",
                "box_coords": [10.0, 70.0, 180.0, 95.0],
                "hit_count": 2,
                "visual_provenance": {"classification": "EDITOR_OVERLAY"},
            },
            {
                "text_id": "source_01",
                "start_frame": 1,
                "end_frame": 2,
                "best_frame_index": 1,
                "best_keyframe_path": "frames/source_01.jpg",
                "box_coords": [20.0, 20.0, 80.0, 35.0],
                "hit_count": 2,
                "visual_provenance": {"classification": "SOURCE_INTRINSIC"},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames_dir = root / "frames"
            frames_dir.mkdir()
            qa_dir = root / "qa"
            for name in ("editor_01.jpg", "source_01.jpg"):
                cv2.imwrite(str(frames_dir / name), frame)
            summary = write_phase1_qa_artifacts(
                qa_dir=qa_dir,
                timeline=timeline,
                dropped=[],
                frame_count=4,
                frame_width=192,
                frame_height=108,
                frames_dir=frames_dir,
                frame_cache={1: frame, 2: frame},
                source=root / "missing.mp4",
                geometry_rejected=0,
                coarse_hits=0,
                phase_hits=0,
                dense_extra_frames=0,
                total_hits=0,
            )

            assert summary["boundary_overlays"] == 1
            assert summary["boundary_source_tracks_skipped"] == 1
            assert (qa_dir / "boundaries" / "editor_01.jpg").is_file()
            assert not (qa_dir / "boundaries" / "source_01.jpg").exists()


class TimelineFormatTests(unittest.TestCase):
    def test_format_and_entry_shape(self) -> None:
        self.assertEqual(format_timeline_time(1.56, fps=30.0), "00:01.560")
        entry = timeline_entry_dict(
            text_id="sub_01",
            start_frame=47,
            end_frame=120,
            fps=30.0,
            box_coords=[10.0, 20.0, 30.0, 40.0],
            best_keyframe_path="frames/sub_01.jpg",
            text="加盐",
        )
        self.assertEqual(entry["text_id"], "sub_01")
        self.assertEqual(entry["start_frame"], 47)
        self.assertEqual(entry["end_frame"], 120)
        self.assertEqual(entry["start_time"], "00:01.567")
        self.assertEqual(entry["end_time"], "00:04.000")
        self.assertEqual(entry["box_coords"], [10.0, 20.0, 30.0, 40.0])
        self.assertEqual(entry["best_keyframe_path"], "frames/sub_01.jpg")


class TimelinePayloadTests(unittest.TestCase):
    def test_expands_continuous_frames_with_same_box(self) -> None:
        timeline = [
            {
                "text_id": "sub_01",
                "start_frame": 47,
                "end_frame": 50,
                "start_time": "00:01.560",
                "end_time": "00:01.666",
                "box_coords": [100.0, 900.0, 500.0, 960.0],
                "best_keyframe_path": "frames/sub_01.jpg",
                "text": "字幕",
            }
        ]
        payload = timeline_to_ocr_payload(
            timeline,
            fps=30.0,
            frame_count=100,
            frame_width=1920,
            frame_height=1080,
        )
        self.assertEqual(payload["authority"], "master_phase1")
        frames = payload["frames"]
        by_idx = {int(f["frame_index"]): f for f in frames}
        for idx in (47, 48, 49, 50):
            self.assertIn(idx, by_idx)
            boxes = by_idx[idx]["boxes"]
            self.assertEqual(len(boxes), 1)
            self.assertEqual(boxes[0]["text"], "字幕")
            self.assertAlmostEqual(boxes[0]["x"], 100.0 / 1920.0, places=4)
            self.assertAlmostEqual(boxes[0]["y"], 900.0 / 1080.0, places=4)

    def test_empty_text_is_cover_only(self) -> None:
        timeline = [
            {
                "text_id": "sub_01",
                "start_frame": 0,
                "end_frame": 0,
                "box_coords": [0.0, 500.0, 100.0, 550.0],
                "best_keyframe_path": "frames/sub_01.jpg",
                "text": "",
            }
        ]
        payload = timeline_to_ocr_payload(
            timeline,
            fps=30.0,
            frame_count=10,
            frame_width=1000,
            frame_height=1000,
        )
        box = payload["frames"][0]["boxes"][0]
        self.assertTrue(box.get("cover_only"))


if __name__ == "__main__":
    unittest.main()
