"""Phase 1 PASS contract (editor text SSOT) — behavioral gates for all videos.

PASS criteria (operator + downstream Phase 2–4):
1. Editor-only: keep burn-in / editor UI; drop in-scene source text (packaging…).
2. Geometry: one box per editor line — no excess (FP/fragment/dupe), no missing (FN).
3. One SSOT per line: near-duplicate column/hardsub tracks coalesce.
4. Box hugs glyphs: no empty left pad to x=0; no food-slab inflation.
5. Lifespan matches appearance (evidence-based; no ghost pad bleed).
6. Temporal lock: editor X-stable; moving scene text out.
7. No Douyin chrome stubs in timeline.
8. Keyframe crop ink-readable (ink-aware pick when cache allows).
9. General across layouts (list / hardsub / endcard) — no clip hardcodes.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.local_text_recognizer import LocalRecognition
from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    MergedTrack,
    coalesce_near_duplicate_tracks,
    complete_locked_overlay_boxes_from_hit_evidence,
    filter_tracks_by_local_text,
    purge_redundant_hardsub_fragments,
    trim_hardsub_box_to_ink,
)


class Phase1PassEditorOnlyTests(unittest.TestCase):
    def test_isolated_locked_micro_source_text_does_not_enter_ssot(self) -> None:
        """A camera-locked appliance label is not an editor overlay."""
        source_label = MergedTrack(
            start_frame=170,
            end_frame=212,
            box_coords=[1636.0, 934.0, 1673.0, 948.0],
            best_frame_index=208,
            best_sharpness=12.0,
            centroid=(1654.5, 941.0),
            hit_count=33,
            hit_boxes=[(1636.0, 934.0, 1673.0, 948.0)] * 33,
            hit_frames=list(range(170, 203)),
            hit_sharpness=[12.0] * 33,
        )
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        frame[934:948, 1636:1673] = 230
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("明书", 0.95, 1.0)

        kept, audit = filter_tracks_by_local_text(
            [source_label],
            frame_cache={208: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )

        self.assertEqual(kept, [])
        self.assertTrue(
            any(
                row.get("reason") == "isolated_micro_source_text"
                for row in audit["rows"]
            ),
            msg=f"source label must be provenance-rejected audit={audit}",
        )

    def test_paired_micro_editor_chips_keep_layout_evidence(self) -> None:
        """Do not replace source filtering with a blanket tiny-box rejection."""

        def _chip(box: list[float]) -> MergedTrack:
            x0, y0, x1, y1 = box
            return MergedTrack(
                start_frame=100,
                end_frame=130,
                box_coords=box,
                best_frame_index=110,
                best_sharpness=12.0,
                centroid=((x0 + x1) * 0.5, (y0 + y1) * 0.5),
                hit_count=20,
                hit_boxes=[tuple(box)] * 20,
                hit_frames=list(range(100, 120)),
                hit_sharpness=[12.0] * 20,
            )

        left = _chip([120.0, 300.0, 180.0, 330.0])
        right = _chip([220.0, 300.0, 280.0, 330.0])
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        frame[300:330, 120:180] = 230
        frame[300:330, 220:280] = 230
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("配料", 0.95, 1.0)

        kept, audit = filter_tracks_by_local_text(
            [left, right],
            frame_cache={110: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )

        self.assertEqual(len(kept), 2, msg=f"paired editor layout must keep {audit}")
        self.assertFalse(
            any(
                row.get("reason") == "isolated_micro_source_text"
                for row in audit["rows"]
            ),
            msg=f"paired chips carry editor layout evidence audit={audit}",
        )

    def test_short_packaging_not_rescued_by_later_dropped_anchor(self) -> None:
        """
        Peer column must come from tracks that themselves survive the gate.

        A scene-drifting mid in the same bucket must not lower min_hits for a
        short packaging chip (净含量 class).
        """
        # Long drifting packaging-like mid (same column as short chip) — will be scene_text.
        drifting = MergedTrack(
            start_frame=0,
            end_frame=40,
            box_coords=[870.0, 280.0, 1040.0, 350.0],
            best_frame_index=10,
            best_sharpness=12.0,
            centroid=(955.0, 315.0),
            hit_count=20,
            hit_boxes=[
                (
                    850.0 + i * 8.0,
                    260.0 + i * 4.0,
                    1020.0 + i * 8.0,
                    330.0 + i * 4.0,
                )
                for i in range(12)
            ],
            hit_frames=list(range(12)),
            hit_sharpness=[12.0] * 12,
        )
        # Short packaging flash — X-stable enough to pass hit count after loosen,
        # but still in-scene if centroids drift with the bag (not editor lock).
        short = MergedTrack(
            start_frame=210,
            end_frame=214,
            box_coords=[873.8, 285.2, 1044.2, 354.5],
            best_frame_index=211,
            best_sharpness=10.0,
            centroid=(959.0, 319.85),
            hit_count=3,
            hit_boxes=[
                (873.8, 285.2, 1044.2, 354.5),
                (900.0, 286.0, 1070.0, 355.0),
                (930.0, 285.0, 1100.0, 354.0),
            ],
            hit_frames=[210, 211, 212],
            hit_sharpness=[10.0] * 3,
        )
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        frame[285:355, 873:1045] = 200
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("净含量150克", 0.95, 1.0)
        kept, audit = filter_tracks_by_local_text(
            [drifting, short],
            frame_cache={10: frame, 211: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(kept, [])
        reasons = {r.get("reason") for r in audit["rows"]}
        self.assertTrue(
            "scene_text" in reasons or "low_hits" in reasons,
            msg=f"packaging must drop audit={audit}",
        )

    def test_compact_device_ui_cluster_dropped_keeps_hardsub_and_sparse_mid(
        self,
    ) -> None:
        """
        Camera-locked appliance/panel glyphs look X-stable like burn-in.

        A concurrent cluster of tiny mid/ui chips is in-scene device UI → drop.
        True hardsub + a single sparse editor mid must still keep.
        """
        def _locked_chip(
            *,
            box: list[float],
            start: int,
            end: int,
            hits: int,
            text: str,
        ) -> MergedTrack:
            x0, y0, x1, y1 = box
            cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
            n = max(hits, 5)
            hit_boxes = [
                (x0 + (i % 2), y0 + (i % 2) * 0.5, x1 + (i % 2), y1 + (i % 2) * 0.5)
                for i in range(n)
            ]
            return MergedTrack(
                start_frame=start,
                end_frame=end,
                box_coords=list(box),
                best_frame_index=start + 1,
                best_sharpness=12.0,
                centroid=(cx, cy),
                hit_count=n,
                hit_boxes=hit_boxes,
                hit_frames=list(range(start, start + n)),
                hit_sharpness=[12.0] * n,
            )

        # Six compact panel-like chips overlapping in time (device UI grid).
        panel_boxes = [
            [762.0, 645.0, 810.0, 673.0],
            [976.0, 706.0, 1026.0, 739.0],
            [993.0, 533.0, 1051.0, 570.0],
            [1226.0, 601.0, 1270.0, 662.0],
            [560.0, 415.0, 606.0, 445.0],
            [776.0, 474.0, 828.0, 507.0],
        ]
        panel = [
            _locked_chip(
                box=b,
                start=539,
                end=567,
                hits=8 + i,
                text="面板",
            )
            for i, b in enumerate(panel_boxes)
        ]
        hardsub = MergedTrack(
            start_frame=10,
            end_frame=1000,
            box_coords=[622.0, 1011.0, 1296.0, 1056.0],
            best_frame_index=100,
            best_sharpness=20.0,
            centroid=(959.0, 1033.5),
            hit_count=40,
            hit_boxes=[(622.0, 1011.0, 1296.0, 1056.0)] * 8,
            hit_frames=list(range(100, 108)),
            hit_sharpness=[20.0] * 8,
        )
        # Sparse editor mid (alone, larger caption chip) — must keep.
        sparse_mid = _locked_chip(
            box=[700.0, 220.0, 980.0, 290.0],
            start=100,
            end=160,
            hits=20,
            text="加盐",
        )

        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        for b in panel_boxes:
            x0, y0, x1, y1 = (int(v) for v in b)
            frame[y0:y1, x0:x1] = 220
        # Stroke hardsub (flat white scores ink≈0 and trips low_ink gate).
        for x in range(640, 1280, 10):
            frame[1016:1050, x : x + 6] = 235
            frame[1016:1050, x + 6 : x + 10] = 20
        frame[220:290, 700:980] = 240
        rec = MagicMock()

        def _recognize(crop: np.ndarray) -> LocalRecognition:
            h, w = crop.shape[:2]
            if w > 400:
                return LocalRecognition("上汽蒸个15分钟就可以了", 0.95, 1.0)
            if w > 200:
                return LocalRecognition("加盐", 0.95, 1.0)
            return LocalRecognition("时间", 0.90, 1.0)

        rec.recognize.side_effect = _recognize
        kept, audit = filter_tracks_by_local_text(
            [hardsub, sparse_mid, *panel],
            frame_cache={100: frame, 540: frame, 120: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        kept_boxes = [list(t.box_coords) for t in kept]
        self.assertTrue(
            any(abs(b[1] - 1011.0) < 2 for b in kept_boxes),
            msg=f"hardsub must keep kept={kept_boxes} audit={audit}",
        )
        self.assertTrue(
            any(abs(b[1] - 220.0) < 2 for b in kept_boxes),
            msg=f"sparse editor mid must keep kept={kept_boxes}",
        )
        for b in panel_boxes:
            self.assertFalse(
                any(abs(kb[0] - b[0]) < 2 and abs(kb[1] - b[1]) < 2 for kb in kept_boxes),
                msg=f"panel chip {b} must drop kept={kept_boxes} audit={audit}",
            )
        cluster_drops = [
            r
            for r in audit["rows"]
            if r.get("reason")
            in {"scene_text", "scene_ui_cluster", "not_overlay_geometry"}
        ]
        self.assertGreaterEqual(
            len(cluster_drops),
            6,
            msg=f"expected cluster scene drops audit={audit}",
        )

    def test_compact_chips_on_editor_card_kept_with_wide_mid_anchor(self) -> None:
        """
        Nutrition/endcard UI: tiny chips sit next to wide locked mid labels.

        Cluster gate must not drop those chips when a wide editor mid overlaps
        the same window (unlike a device panel that is only compact chips).
        """

        def _locked(
            *,
            box: list[float],
            start: int,
            end: int,
            hits: int,
        ) -> MergedTrack:
            x0, y0, x1, y1 = box
            n = max(hits, 5)
            return MergedTrack(
                start_frame=start,
                end_frame=end,
                box_coords=list(box),
                best_frame_index=start + 1,
                best_sharpness=12.0,
                centroid=((x0 + x1) * 0.5, (y0 + y1) * 0.5),
                hit_count=n,
                hit_boxes=[
                    (x0, y0, x1, y1) for _ in range(n)
                ],
                hit_frames=list(range(start, start + n)),
                hit_sharpness=[12.0] * n,
            )

        # Wide nutrition labels (editor card).
        protein = _locked(
            box=[80.0, 279.0, 359.0, 325.0], start=1003, end=1044, hits=20
        )
        carbs = _locked(
            box=[112.0, 340.0, 453.0, 378.0], start=1003, end=1044, hits=20
        )
        # Compact amount chips on the same card — must KEEP.
        chip_boxes = [
            [154.0, 681.0, 246.0, 711.0],
            [156.0, 769.0, 232.0, 806.0],
            [159.0, 629.0, 267.0, 666.0],
        ]
        chips = [
            _locked(box=b, start=1003, end=1044, hits=20) for b in chip_boxes
        ]
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        for b in [protein.box_coords, carbs.box_coords, *chip_boxes]:
            x0, y0, x1, y1 = (int(v) for v in b)
            frame[y0:y1, x0:x1] = 230
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("蛋白质", 0.95, 1.0)
        kept, audit = filter_tracks_by_local_text(
            [protein, carbs, *chips],
            frame_cache={1010: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        kept_boxes = [list(t.box_coords) for t in kept]
        self.assertTrue(
            any(abs(b[1] - 279.0) < 2 for b in kept_boxes),
            msg=f"wide mid must keep kept={kept_boxes} audit={audit}",
        )
        for b in chip_boxes:
            self.assertTrue(
                any(abs(kb[0] - b[0]) < 2 and abs(kb[1] - b[1]) < 2 for kb in kept_boxes),
                msg=f"editor-card chip {b} must keep kept={kept_boxes} audit={audit}",
            )
        self.assertFalse(
            any(r.get("reason") == "scene_ui_cluster" for r in audit["rows"]),
            msg=f"must not cluster-drop editor card chips audit={audit}",
        )


class Phase1PassGeometryTests(unittest.TestCase):
    def test_repeated_wider_mid_label_hits_restore_missing_leading_glyph(self) -> None:
        """Repeated full-line evidence must beat a partial-edge median."""
        partial = (556.0, 179.0, 734.0, 221.0)
        complete = (509.0, 179.0, 734.0, 221.0)
        boxes = [partial] * 40 + [complete] * 15
        track = MergedTrack(
            start_frame=138,
            end_frame=189,
            box_coords=list(partial),
            best_frame_index=180,
            best_sharpness=20.0,
            centroid=(645.0, 200.0),
            hit_count=len(boxes),
            hit_boxes=boxes,
            hit_frames=list(range(138, 138 + len(boxes))),
            hit_sharpness=[20.0] * len(boxes),
        )

        completed = complete_locked_overlay_boxes_from_hit_evidence(
            [track], frame_w=1920, frame_h=1080
        )[0]

        self.assertLessEqual(completed.box_coords[0], 505.0)
        self.assertAlmostEqual(completed.box_coords[2], 734.0, delta=2.0)

    def test_one_wide_mid_label_outlier_does_not_expand_stable_box(self) -> None:
        partial = (556.0, 179.0, 734.0, 221.0)
        outlier = (390.0, 170.0, 900.0, 250.0)
        boxes = [partial] * 39 + [outlier]
        track = MergedTrack(
            start_frame=100,
            end_frame=139,
            box_coords=list(partial),
            best_frame_index=110,
            best_sharpness=20.0,
            centroid=(645.0, 200.0),
            hit_count=len(boxes),
            hit_boxes=boxes,
            hit_frames=list(range(100, 140)),
            hit_sharpness=[20.0] * len(boxes),
        )

        completed = complete_locked_overlay_boxes_from_hit_evidence(
            [track], frame_w=1920, frame_h=1080
        )[0]

        self.assertAlmostEqual(completed.box_coords[0], partial[0], delta=2.0)
        self.assertAlmostEqual(completed.box_coords[2], partial[2], delta=2.0)

    def test_two_hit_wide_hardsub_shadow_drops_against_dense_host(self) -> None:
        host_box = (621.0, 1001.0, 1349.0, 1054.0)
        shadow_box = (758.0, 969.0, 1647.0, 1018.0)
        host = MergedTrack(
            start_frame=6,
            end_frame=358,
            box_coords=list(host_box),
            best_frame_index=139,
            best_sharpness=20.0,
            centroid=(985.0, 1027.5),
            hit_count=493,
            hit_boxes=[host_box] * 20,
            hit_frames=list(range(120, 140)),
            hit_sharpness=[20.0] * 20,
        )
        shadow = MergedTrack(
            start_frame=139,
            end_frame=140,
            box_coords=list(shadow_box),
            best_frame_index=139,
            best_sharpness=10.0,
            centroid=(1202.5, 993.5),
            hit_count=2,
            hit_boxes=[shadow_box] * 2,
            hit_frames=[139, 140],
            hit_sharpness=[10.0] * 2,
        )

        kept = purge_redundant_hardsub_fragments(
            [host, shadow], frame_w=1920, frame_h=1080
        )

        self.assertEqual(kept, [host])

    def test_coalesce_keeps_dense_hardsub_core_when_wide_variant_extends_timing(self) -> None:
        core_box = (500.0, 1008.0, 1400.0, 1052.0)
        balloon_box = (330.0, 1002.0, 1620.0, 1054.0)
        core = MergedTrack(
            start_frame=1,
            end_frame=50,
            box_coords=list(core_box),
            best_frame_index=25,
            best_sharpness=20.0,
            centroid=(950.0, 1030.0),
            hit_count=50,
            hit_boxes=[core_box] * 50,
            hit_frames=list(range(1, 51)),
            hit_sharpness=[20.0] * 50,
        )
        balloon = MergedTrack(
            start_frame=40,
            end_frame=60,
            box_coords=list(balloon_box),
            best_frame_index=55,
            best_sharpness=30.0,
            centroid=(975.0, 1028.0),
            hit_count=21,
            hit_boxes=[balloon_box] * 21,
            hit_frames=list(range(40, 61)),
            hit_sharpness=[30.0] * 21,
        )

        merged = coalesce_near_duplicate_tracks(
            [core, balloon], frame_w=1920, frame_h=1080
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual((merged[0].start_frame, merged[0].end_frame), (1, 60))
        self.assertLessEqual(merged[0].box_coords[0], core_box[0] + 1.0)
        self.assertGreaterEqual(merged[0].box_coords[0], core_box[0] - 1.0)
        self.assertLessEqual(merged[0].box_coords[2], core_box[2] + 1.0)
        self.assertGreaterEqual(merged[0].box_coords[2], core_box[2] - 1.0)
        self.assertIn(60, merged[0].hit_frames)
        self.assertEqual(merged[0].best_frame_index, 55)
        self.assertTrue(
            any(
                box[0] == core_box[0]
                and box[2] == core_box[2]
                and box[1] == balloon_box[1]
                and box[3] == balloon_box[3]
                for box in merged[0].hit_boxes
            )
        )

    def test_filter_does_not_relocate_dense_valid_short_hardsub(self) -> None:
        """A dense detector line is geometry authority, not a recover stub."""
        seed = [800.0, 1010.0, 1126.0, 1052.0]
        wrong_upper_texture = [311.0, 973.0, 1455.0, 1014.0]
        track = MergedTrack(
            start_frame=397,
            end_frame=431,
            box_coords=list(seed),
            best_frame_index=410,
            best_sharpness=20.0,
            centroid=(963.0, 1031.0),
            hit_count=35,
            hit_boxes=[tuple(seed)] * 35,
            hit_frames=list(range(397, 432)),
            hit_sharpness=[20.0] * 35,
        )
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[1010:1052, 800:1126] = 240
        recognizer = MagicMock()
        recognizer.recognize.return_value = LocalRecognition("起锅喷三克油", 0.98, 1.0)

        with patch(
            "src.media_pipeline.frame_sampling.master_phase1_extractor."
            "recover_hardsub_box_from_band_ink",
            return_value=list(wrong_upper_texture),
        ) as recover:
            kept, audit = filter_tracks_by_local_text(
                [track],
                frame_cache={410: frame},
                frame_w=1920,
                frame_h=1080,
                recognizer=recognizer,
            )

        self.assertEqual(len(kept), 1, msg=str(audit))
        self.assertEqual(kept[0].box_coords, seed)
        recover.assert_not_called()

    def test_purge_thin_hardsub_stub_under_wide_line(self) -> None:
        wide = MergedTrack(
            start_frame=0,
            end_frame=100,
            box_coords=[0.0, 976.0, 1498.0, 1018.0],
            best_frame_index=50,
            best_sharpness=20.0,
            centroid=(749.0, 997.0),
            hit_count=100,
            hit_boxes=[(0.0, 976.0, 1498.0, 1018.0)],
            hit_frames=[50],
            hit_sharpness=[20.0],
        )
        stub = MergedTrack(
            start_frame=60,
            end_frame=80,
            box_coords=[0.0, 986.0, 220.0, 1009.0],
            best_frame_index=70,
            best_sharpness=8.0,
            centroid=(110.0, 997.5),
            hit_count=10,
            hit_boxes=[(0.0, 986.0, 220.0, 1009.0)],
            hit_frames=[70],
            hit_sharpness=[8.0],
        )
        mid = MergedTrack(
            start_frame=0,
            end_frame=40,
            box_coords=[274.0, 391.0, 503.0, 468.0],
            best_frame_index=20,
            best_sharpness=15.0,
            centroid=(388.0, 430.0),
            hit_count=40,
            hit_boxes=[(274.0, 391.0, 503.0, 468.0)],
            hit_frames=[20],
            hit_sharpness=[15.0],
        )
        kept = purge_redundant_hardsub_fragments(
            [wide, stub, mid], frame_w=1920, frame_h=1080
        )
        self.assertEqual(len(kept), 2)
        self.assertTrue(any(abs(t.box_coords[2] - 1498) < 1 for t in kept))
        self.assertFalse(any(abs(t.box_coords[2] - 220) < 1 for t in kept))

    def test_purge_nested_sparse_hardsub_under_dense_line(self) -> None:
        """Short overwide hardsub nested under a dense burn-in must drop (FP pad)."""
        dense = MergedTrack(
            start_frame=422,
            end_frame=683,
            box_coords=[432.0, 1017.0, 1204.0, 1054.0],
            best_frame_index=583,
            best_sharpness=20.0,
            centroid=(818.0, 1035.5),
            hit_count=255,
            hit_boxes=[(432.0, 1017.0, 1204.0, 1054.0)] * 8,
            hit_frames=list(range(580, 588)),
            hit_sharpness=[20.0] * 8,
        )
        nested = MergedTrack(
            start_frame=571,
            end_frame=578,
            box_coords=[0.0, 975.0, 1205.0, 1077.0],
            best_frame_index=575,
            best_sharpness=5.0,
            centroid=(602.5, 1026.0),
            hit_count=4,
            hit_boxes=[(0.0, 975.0, 1205.0, 1077.0)] * 4,
            hit_frames=[572, 573, 574, 575],
            hit_sharpness=[5.0] * 4,
        )
        kept = purge_redundant_hardsub_fragments(
            [dense, nested], frame_w=1920, frame_h=1080
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].hit_count, 255)

    def test_rejected_wide_balloon_cannot_purge_adjacent_dense_captions(self) -> None:
        """A stale sparse host must not erase captions on either boundary."""
        prior = MergedTrack(
            start_frame=744,
            end_frame=818,
            box_coords=[727.6, 1002.8, 1187.8, 1054.1],
            best_frame_index=780,
            best_sharpness=20.0,
            centroid=(957.7, 1028.45),
            hit_count=71,
            hit_boxes=[(727.6, 1002.8, 1187.8, 1054.1)] * 71,
            hit_frames=list(range(748, 819)),
            hit_sharpness=[20.0] * 71,
        )
        sparse_balloon = MergedTrack(
            start_frame=816,
            end_frame=821,
            box_coords=[524.0, 987.2, 1549.0, 1032.4],
            best_frame_index=818,
            best_sharpness=5.0,
            centroid=(1036.5, 1009.8),
            hit_count=2,
            hit_boxes=[(524.0, 987.2, 1549.0, 1032.4)] * 2,
            hit_frames=[818, 819],
            hit_sharpness=[5.0] * 2,
        )
        following = MergedTrack(
            start_frame=818,
            end_frame=917,
            box_coords=[755.6, 1000.6, 1156.4, 1049.2],
            best_frame_index=870,
            best_sharpness=20.0,
            centroid=(956.0, 1024.9),
            hit_count=93,
            hit_boxes=[(755.6, 1000.6, 1156.4, 1049.2)] * 93,
            hit_frames=list(range(818, 911)),
            hit_sharpness=[20.0] * 93,
        )

        kept = purge_redundant_hardsub_fragments(
            [prior, sparse_balloon, following], frame_w=1920, frame_h=1080
        )

        self.assertEqual(len(kept), 2)
        self.assertIn(prior, kept)
        self.assertIn(following, kept)
        self.assertNotIn(sparse_balloon, kept)

    def test_purge_keeps_later_shorter_hardsub_without_time_overlap(self) -> None:
        """Consecutive burn-in lines: shorter next line must not die under prior wide host."""
        prior = MergedTrack(
            start_frame=272,
            end_frame=324,
            box_coords=[78.0, 1009.0, 1301.0, 1060.0],
            best_frame_index=300,
            best_sharpness=20.0,
            centroid=(689.5, 1034.5),
            hit_count=48,
            hit_boxes=[(78.0, 1009.0, 1301.0, 1060.0)] * 6,
            hit_frames=list(range(290, 296)),
            hit_sharpness=[20.0] * 6,
        )
        # Spatially nested under prior X-span, but a different later line.
        nxt = MergedTrack(
            start_frame=326,
            end_frame=368,
            box_coords=[832.0, 1018.0, 1147.0, 1051.0],
            best_frame_index=348,
            best_sharpness=18.0,
            centroid=(989.5, 1034.5),
            hit_count=39,
            hit_boxes=[(832.0, 1018.0, 1147.0, 1051.0)] * 6,
            hit_frames=list(range(330, 336)),
            hit_sharpness=[18.0] * 6,
        )
        kept = purge_redundant_hardsub_fragments(
            [prior, nxt], frame_w=1920, frame_h=1080
        )
        self.assertEqual(len(kept), 2)
        self.assertTrue(
            any(abs(t.box_coords[0] - 832.0) < 1 for t in kept),
            msg=f"later shorter hardsub must keep kept={[t.box_coords for t in kept]}",
        )

    def test_purge_keeps_consecutive_hardsubs_with_one_boundary_frame_overlap(self) -> None:
        """Inclusive spans may share one frame; that is not fragment overlap."""
        prior = MergedTrack(
            start_frame=753,
            end_frame=874,
            box_coords=[689.0, 1016.0, 1226.0, 1053.0],
            best_frame_index=818,
            best_sharpness=20.0,
            centroid=(957.5, 1034.5),
            hit_count=126,
            hit_boxes=[(689.0, 1016.0, 1226.0, 1053.0)] * 4,
            hit_frames=[816, 817, 818, 819],
            hit_sharpness=[20.0] * 4,
        )
        following = MergedTrack(
            start_frame=874,
            end_frame=1001,
            box_coords=[619.0, 1014.0, 1310.0, 1054.0],
            best_frame_index=900,
            best_sharpness=20.0,
            centroid=(964.5, 1034.0),
            hit_count=130,
            hit_boxes=[(619.0, 1014.0, 1310.0, 1054.0)] * 4,
            hit_frames=[900, 901, 902, 903],
            hit_sharpness=[20.0] * 4,
        )
        kept = purge_redundant_hardsub_fragments(
            [prior, following], frame_w=1920, frame_h=1080
        )
        self.assertEqual(len(kept), 2)

    def test_filter_drops_food_texture_hardsub_band(self) -> None:
        """Wide bottom food/lettuce strip without glyph ink must not SSOT as hardsub."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            filter_tracks_by_local_text,
            MergedTrack,
        )

        track = MergedTrack(
            start_frame=70,
            end_frame=80,
            box_coords=[239.0, 946.0, 1515.0, 998.0],
            best_frame_index=75,
            best_sharpness=4.0,
            centroid=(877.0, 972.0),
            hit_count=6,
            hit_boxes=[(239.0, 946.0, 1515.0, 998.0)] * 4,
            hit_frames=[72, 73, 74, 75],
            hit_sharpness=[4.0] * 4,
        )
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # Soft food colors — no stroke glyphs (noise would inflate ink score).
        frame[946:998, 239:700] = (40, 180, 60)
        frame[946:998, 700:1100] = (30, 140, 220)
        frame[946:998, 1100:1515] = (50, 160, 80)
        frame[946:998, 239:1515] = cv2.GaussianBlur(
            frame[946:998, 239:1515], (21, 21), 0
        )
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("", 0.0, 0.0)
        kept, audit = filter_tracks_by_local_text(
            [track],
            frame_cache={75: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(kept, [])
        reasons = {r.get("reason") for r in audit["rows"]}
        self.assertTrue(
            reasons & {"low_ink", "local_text_reject"},
            msg=f"food hardsub band must drop audit={audit}",
        )

    def test_filter_drops_tall_micro_food_fleck(self) -> None:
        """Tiny tall mid box on food flecks must not enter SSOT."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            filter_tracks_by_local_text,
            MergedTrack,
        )

        track = MergedTrack(
            start_frame=640,
            end_frame=647,
            box_coords=[432.0, 340.0, 466.0, 389.0],
            best_frame_index=645,
            best_sharpness=6.0,
            centroid=(449.0, 364.5),
            hit_count=3,
            hit_boxes=[(432.0, 340.0, 466.0, 389.0)] * 3,
            hit_frames=[643, 644, 645],
            hit_sharpness=[6.0] * 3,
        )
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        frame[340:389, 432:466] = (40, 90, 200)  # orange food fleck
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("福", 0.90, 1.0)
        kept, audit = filter_tracks_by_local_text(
            [track],
            frame_cache={645: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(kept, [])
        reasons = {r.get("reason") for r in audit["rows"]}
        self.assertTrue(
            reasons & {"not_overlay_geometry", "local_text_reject", "low_ink"},
            msg=f"food fleck must drop audit={audit}",
        )

    def test_coalesce_merges_same_ingredient_band(self) -> None:
        a = MergedTrack(
            start_frame=10,
            end_frame=40,
            box_coords=[325.0, 144.0, 448.0, 222.0],
            best_frame_index=20,
            best_sharpness=10.0,
            centroid=(386.5, 183.0),
            hit_count=6,
            hit_boxes=[(325.0, 144.0, 448.0, 222.0)] * 4,
            hit_frames=[10, 12, 14, 16],
            hit_sharpness=[10.0] * 4,
        )
        b = MergedTrack(
            start_frame=30,
            end_frame=80,
            box_coords=[326.0, 145.0, 449.0, 221.0],
            best_frame_index=50,
            best_sharpness=18.0,
            centroid=(387.5, 183.0),
            hit_count=20,
            hit_boxes=[(326.0, 145.0, 449.0, 221.0)] * 6,
            hit_frames=list(range(30, 42, 2)),
            hit_sharpness=[18.0] * 6,
        )
        out = coalesce_near_duplicate_tracks([a, b], frame_w=1920, frame_h=1080)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].start_frame, 10)
        self.assertEqual(out[0].end_frame, 80)

    def test_coalesce_merges_detection_hole_same_band(self) -> None:
        """List bands flicker in DBNet; SSOT must bridge gaps >> MERGE_GAP_FRAMES."""
        early = MergedTrack(
            start_frame=603,
            end_frame=709,
            box_coords=[325.0, 144.0, 448.0, 222.0],
            best_frame_index=650,
            best_sharpness=12.0,
            centroid=(386.5, 183.0),
            hit_count=90,
            hit_boxes=[(325.0, 144.0, 448.0, 222.0)] * 8,
            hit_frames=list(range(603, 711, 14)),
            hit_sharpness=[12.0] * 8,
        )
        hole = MergedTrack(
            start_frame=719,
            end_frame=742,
            box_coords=[324.0, 141.0, 450.0, 227.0],
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(387.0, 184.0),
            hit_count=10,
            hit_boxes=[(324.0, 141.0, 450.0, 227.0)] * 4,
            hit_frames=[719, 725, 732, 740],
            hit_sharpness=[10.0] * 4,
        )
        late = MergedTrack(
            start_frame=761,
            end_frame=829,
            box_coords=[326.0, 144.0, 449.0, 220.0],
            best_frame_index=790,
            best_sharpness=14.0,
            centroid=(387.5, 182.0),
            hit_count=61,
            hit_boxes=[(326.0, 144.0, 449.0, 220.0)] * 6,
            hit_frames=list(range(761, 830, 12)),
            hit_sharpness=[14.0] * 6,
        )
        # Different row — must not merge.
        other = MergedTrack(
            start_frame=603,
            end_frame=829,
            box_coords=[325.0, 391.0, 503.0, 468.0],
            best_frame_index=700,
            best_sharpness=20.0,
            centroid=(414.0, 429.5),
            hit_count=200,
            hit_boxes=[(325.0, 391.0, 503.0, 468.0)],
            hit_frames=[700],
            hit_sharpness=[20.0],
        )
        out = coalesce_near_duplicate_tracks(
            [early, hole, late, other], frame_w=1920, frame_h=1080
        )
        self.assertEqual(len(out), 2)
        top = [t for t in out if t.box_coords[1] < 300][0]
        self.assertEqual(top.start_frame, 603)
        self.assertEqual(top.end_frame, 829)
        self.assertGreaterEqual(top.hit_count, 18)

    def test_trim_hardsub_drops_empty_left_pad(self) -> None:
        """Overwide hardsub with x=0 empty margin must hug glyph ink."""
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        # Stroke-like glyphs: alternating bright/dark columns (flat white ≠ ink).
        for x in range(420, 980, 8):
            frame[980:1010, x : x + 5] = 235
            frame[980:1010, x + 5 : x + 8] = 25
        overwide = [0.0, 976.0, 1498.0, 1018.0]
        trimmed = trim_hardsub_box_to_ink(
            frame, overwide, frame_w=1920, frame_h=1080
        )
        self.assertGreater(trimmed[0], 200.0)
        self.assertLess(trimmed[2], 1200.0)
        self.assertLess(trimmed[2] - trimmed[0], 900.0)
        # Must not eat into the glyph run (pad past first stroke).
        self.assertLessEqual(trimmed[0], 420.0)
        self.assertGreaterEqual(trimmed[2], 980.0)
        # Empty left pad must be gone (glyphs start at 420).
        self.assertGreaterEqual(trimmed[0], 380.0)
        # Soft edge pad must stay tight to glyph mets (≤8px outside ink).
        self.assertGreaterEqual(trimmed[0], 412.0)
        self.assertLessEqual(trimmed[2], 988.0)

    def test_trim_hardsub_y_hugs_glyph_band(self) -> None:
        """Tall hardsub seed with empty Y pad must snap to stroke band."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            trim_hardsub_box_y_to_ink,
        )

        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        for x in range(500, 1100, 8):
            frame[990:1012, x : x + 5] = 240
            frame[990:1012, x + 5 : x + 8] = 20
        tall = [480.0, 940.0, 1200.0, 1040.0]
        trimmed = trim_hardsub_box_y_to_ink(
            frame, tall, frame_w=1920, frame_h=1080
        )
        self.assertGreaterEqual(trimmed[1], 980.0)
        self.assertLessEqual(trimmed[3], 1020.0)
        self.assertLessEqual(trimmed[1], 990.0)
        self.assertGreaterEqual(trimmed[3], 1012.0)

    def test_trim_hardsub_y_completes_glyph_beyond_detector_seed(self) -> None:
        """A clipped detector y1 must not permanently cut the glyph outline."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            trim_hardsub_box_y_to_ink,
        )

        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        for x in range(500, 1100, 8):
            frame[990:1013, x : x + 5] = 240
            frame[990:1013, x + 5 : x + 8] = 20
        clipped = [480.0, 988.0, 1200.0, 1008.0]

        completed = trim_hardsub_box_y_to_ink(
            frame, clipped, frame_w=1920, frame_h=1080
        )

        self.assertGreaterEqual(completed[3], 1013.0)
        self.assertLessEqual(completed[3], 1020.0)

    def test_pick_hardsub_box_prefers_full_ink_span(self) -> None:
        """Among candidate trims, prefer full-line coverage — not the tightest mid slice."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            pick_best_hardsub_ink_box,
        )

        seed = [700.0, 976.0, 1100.0, 1018.0]
        # Mid slice (too tight) vs full line.
        mid = [610.0, 976.0, 1264.0, 1018.0]
        full = [340.0, 976.0, 1480.0, 1018.0]
        got = pick_best_hardsub_ink_box(
            [mid, full], seed=seed, frame_w=1920, max_width_frac=0.78
        )
        self.assertEqual(got, full)

    def test_pick_hardsub_rejects_empty_left_to_frame_edge(self) -> None:
        """x=0 pad must lose to a seed-centered full line (food-edge false ink)."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            pick_best_hardsub_ink_box,
        )

        seed = [700.0, 976.0, 1100.0, 1018.0]
        balloon = [0.0, 976.0, 1382.0, 1018.0]
        full = [340.0, 976.0, 1480.0, 1018.0]
        got = pick_best_hardsub_ink_box(
            [balloon, full], seed=seed, frame_w=1920, max_width_frac=0.78
        )
        self.assertEqual(got, full)
        self.assertGreater(got[0], 16.0)

    def test_recover_hardsub_from_band_when_seed_is_right_stub(self) -> None:
        """Right-edge stub must expand to the real centered hardsub ink run."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            recover_hardsub_box_from_band_ink,
        )

        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        # Centered stroke hardsub (not at right edge).
        for x in range(420, 1280, 8):
            frame[980:1010, x : x + 5] = 235
            frame[980:1010, x + 5 : x + 8] = 20
        stub = [1606.0, 950.0, 1703.0, 974.0]
        got = recover_hardsub_box_from_band_ink(
            frame, stub, frame_w=1920, frame_h=1080
        )
        self.assertIsNotNone(got)
        assert got is not None
        self.assertLess(got[0], 500.0)
        self.assertGreater(got[2], 1200.0)
        self.assertGreater((got[2] - got[0]) / 1920.0, 0.35)

    def test_extend_tracks_completes_left_truncated_hardsub_line(self) -> None:
        """Mid-width seed covering only the left half must grow to full ink span."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        for x in range(200, 1500, 8):
            frame[1000:1035, x : x + 5] = 240
            frame[1000:1035, x + 5 : x + 8] = 20
        # Truncated seed: left ~half of the real line (w≈0.40).
        seed = [200.0, 998.0, 970.0, 1038.0]
        track = MergedTrack(
            start_frame=270,
            end_frame=320,
            box_coords=list(seed),
            best_frame_index=290,
            best_sharpness=20.0,
            centroid=(585.0, 1018.0),
            hit_count=40,
            hit_boxes=[tuple(seed)] * 6,
            hit_frames=[288, 289, 290, 291],
            hit_sharpness=[20.0] * 4,
        )
        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={290: frame},
            frame_w=1920,
            frame_h=1080,
        )
        self.assertEqual(len(out), 1)
        box = out[0].box_coords
        self.assertGreater((box[2] - box[0]) / 1920.0, 0.55)
        self.assertGreaterEqual(box[2], 1450.0)

    def test_trim_completes_right_biased_left_truncated_seed(self) -> None:
        """Seed missing left glyphs must grow left into strong ink (not floor at seed x0)."""
        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        # Two CJK clusters with a weak ~60px gap (real burn-in spacing).
        for x in range(600, 710, 8):
            frame[1016:1050, x : x + 5] = 240
            frame[1016:1050, x + 5 : x + 8] = 20
        for x in range(780, 1340, 8):
            frame[1016:1050, x : x + 5] = 240
            frame[1016:1050, x + 5 : x + 8] = 20
        # Detector seed covers only the right cluster (w≈0.29).
        seed = [772.0, 1016.0, 1334.0, 1054.0]
        # Extend already found the left cluster; trim must absorb across the gap.
        extended = [606.0, 1016.0, 1340.0, 1054.0]
        trimmed = trim_hardsub_box_to_ink(
            frame,
            extended,
            frame_w=1920,
            frame_h=1080,
            seed_xyxy=seed,
        )
        self.assertLessEqual(trimmed[0], 620.0)
        self.assertGreaterEqual(trimmed[2], 1320.0)
        self.assertGreater((trimmed[2] - trimmed[0]) / 1920.0, 0.35)

    def test_extend_tracks_completes_right_biased_hardsub_seed(self) -> None:
        """Track seed covering only the right half must grow left to full ink span."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        for x in range(600, 1340, 8):
            frame[1016:1050, x : x + 5] = 240
            frame[1016:1050, x + 5 : x + 8] = 20
        seed = [772.0, 1016.0, 1334.0, 1054.0]
        track = MergedTrack(
            start_frame=9,
            end_frame=207,
            box_coords=list(seed),
            best_frame_index=100,
            best_sharpness=20.0,
            centroid=(1053.0, 1035.0),
            hit_count=40,
            hit_boxes=[tuple(seed)] * 6,
            hit_frames=[98, 99, 100, 101],
            hit_sharpness=[20.0] * 4,
        )
        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={100: frame},
            frame_w=1920,
            frame_h=1080,
        )
        self.assertEqual(len(out), 1)
        box = out[0].box_coords
        self.assertLessEqual(box[0], 620.0)
        self.assertGreaterEqual(box[2], 1320.0)

    def test_filter_drops_low_ink_texture_band(self) -> None:
        """Flat food/reflection bands without stroke ink must not enter SSOT."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            filter_tracks_by_local_text,
            MergedTrack,
        )

        track = MergedTrack(
            start_frame=0,
            end_frame=20,
            box_coords=[693.0, 742.0, 814.0, 768.0],
            best_frame_index=10,
            best_sharpness=5.0,
            centroid=(753.5, 755.0),
            hit_count=12,
            hit_boxes=[(693.0, 742.0, 814.0, 768.0)] * 6,
            hit_frames=list(range(10, 16)),
            hit_sharpness=[5.0] * 6,
        )
        # Smooth gradient — no glyph strokes.
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for x in range(693, 814):
            v = int(40 + (x - 693) * 1.5)
            v = min(240, max(0, v))
            frame[742:768, x] = (v, v // 2, 20)
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition("的", 0.4, 0.5)
        kept, audit = filter_tracks_by_local_text(
            [track],
            frame_cache={10: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(kept, [])
        reasons = {r.get("reason") for r in audit["rows"]}
        self.assertTrue(
            "low_ink" in reasons or "local_text_reject" in reasons,
            msg=f"texture must drop audit={audit}",
        )


    def test_square_food_blob_not_thin_hardsub(self) -> None:
        """Compact food blobs in the bottom band must not count as hardsub lines."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            _box_looks_like_thin_hardsub,
            classify_ocr_box_role,
        )

        # sub_08 fossil class: ~square shrimp tip in lower band.
        food = [1273.0, 848.0, 1355.0, 935.0]
        self.assertFalse(
            _box_looks_like_thin_hardsub(food, frame_w=1920, frame_h=1080)
        )
        self.assertNotEqual(
            classify_ocr_box_role(food, frame_w=1920, frame_h=1080),
            "hardsub",
        )

    def test_endcard_lower_row_is_ui_chip_not_hardsub(self) -> None:
        """Endcard list rows sit in cy~0.80 — must not be burn-in hardsub role."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            classify_ocr_box_role,
        )

        # 花生油-class chip: wide-ish label in lower UI, not frame-bottom burn-in.
        peanut = [60.0, 840.0, 280.0, 880.0]
        self.assertEqual(
            classify_ocr_box_role(peanut, frame_w=1920, frame_h=1080),
            "ui_chip",
        )
        # True bottom burn-in stays hardsub.
        burnin = [500.0, 990.0, 1400.0, 1040.0]
        self.assertEqual(
            classify_ocr_box_role(burnin, frame_w=1920, frame_h=1080),
            "hardsub",
        )

    def test_filter_keeps_endcard_peanut_oil_row(self) -> None:
        """Lower endcard chips must survive local-text (not hardsub recover/drop)."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            classify_ocr_box_role,
            filter_tracks_by_local_text,
            MergedTrack,
        )

        peanut = MergedTrack(
            start_frame=721,
            end_frame=745,
            box_coords=[60.0, 840.0, 280.0, 880.0],
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(170.0, 860.0),
            hit_count=24,
            hit_boxes=[(60.0, 840.0, 280.0, 880.0)] * 6,
            hit_frames=[725, 726, 727, 728, 729, 730],
            hit_sharpness=[10.0] * 6,
        )
        qty = MergedTrack(
            start_frame=721,
            end_frame=745,
            box_coords=[60.0, 890.0, 220.0, 925.0],
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(140.0, 907.5),
            hit_count=24,
            hit_boxes=[(60.0, 890.0, 220.0, 925.0)] * 6,
            hit_frames=[725, 726, 727, 728, 729, 730],
            hit_sharpness=[10.0] * 6,
        )
        kcal = MergedTrack(
            start_frame=721,
            end_frame=745,
            box_coords=[1680.0, 860.0, 1890.0, 900.0],
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(1785.0, 880.0),
            hit_count=24,
            hit_boxes=[(1680.0, 860.0, 1890.0, 900.0)] * 6,
            hit_frames=[725, 726, 727, 728, 729, 730],
            hit_sharpness=[10.0] * 6,
        )
        frame = np.full((1080, 1920, 3), 245, dtype=np.uint8)
        frame[840:880, 60:280] = 20
        frame[890:925, 60:220] = 20
        frame[860:900, 1680:1890] = 20
        rec = MagicMock()

        def _recognize(crop: np.ndarray) -> LocalRecognition:
            h, w = crop.shape[:2]
            if w > 180:
                return LocalRecognition("72千卡", 0.90, 1.0)
            if w > 140:
                return LocalRecognition("花生油", 0.99, 1.0)
            return LocalRecognition("8毫升", 0.98, 1.0)

        rec.recognize.side_effect = _recognize
        kept, audit = filter_tracks_by_local_text(
            [peanut, qty, kcal],
            frame_cache={730: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(len(kept), 3, msg=f"endcard row must keep audit={audit}")
        roles = {
            classify_ocr_box_role(t.box_coords, frame_w=1920, frame_h=1080)
            for t in kept
        }
        self.assertNotIn("hardsub", roles)

    def test_filter_drops_compact_food_ui_chip(self) -> None:
        """Chili/food chips without real overlay text must not enter SSOT."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            filter_tracks_by_local_text,
            MergedTrack,
        )

        track = MergedTrack(
            start_frame=540,
            end_frame=553,
            box_coords=[1378.0, 688.0, 1429.0, 742.0],
            best_frame_index=546,
            best_sharpness=8.0,
            centroid=(1403.5, 715.0),
            hit_count=7,
            hit_boxes=[(1378.0, 688.0, 1429.0, 742.0)] * 4,
            hit_frames=[546, 547, 548, 549],
            hit_sharpness=[8.0] * 4,
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        # Red food blob, no glyphs.
        frame[688:742, 1378:1429] = (40, 40, 200)
        rec = MagicMock()
        # Real chili fossil: single-CJK hallucination at mid-high conf.
        rec.recognize.return_value = LocalRecognition("福", 0.74, 1.0)
        kept, audit = filter_tracks_by_local_text(
            [track],
            frame_cache={546: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(kept, [])
        reasons = {r.get("reason") for r in audit["rows"]}
        self.assertTrue(
            reasons & {"local_text_reject", "low_ink", "not_overlay_geometry"},
            msg=f"food chip must drop audit={audit}",
        )

    def test_discover_hardsub_from_cache_when_detector_missed_line(self) -> None:
        """Bottom burn-in present in cache must enter SSOT even without a DBNet seed."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            discover_hardsub_tracks_from_cache,
        )

        frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
        # White hardsub ink strip near bottom (synthetic burn-in).
        frame[1000:1040, 500:1400] = 240
        for x in range(520, 1380, 28):
            frame[1008:1032, x : x + 16] = 20
        rec = MagicMock()
        rec.recognize.return_value = LocalRecognition(
            "不开玩笑这个酱汁拌米饭真的非常香", 0.93, 1.0
        )
        found = discover_hardsub_tracks_from_cache(
            {546: frame, 547: frame, 548: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
            existing=[],
        )
        self.assertGreaterEqual(len(found), 1)
        box = found[0].box_coords
        self.assertGreater((box[2] - box[0]) / 1920.0, 0.28)
        self.assertGreaterEqual(found[0].hit_count, 2)


    def test_extend_hardsub_does_not_rewrite_endcard_chip(self) -> None:
        """Ink-extend must not replace lower endcard ui_chips with burn-in lines."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            extend_hardsub_tracks_to_ink,
        )

        peanut = MergedTrack(
            start_frame=721,
            end_frame=745,
            box_coords=[148.0, 849.0, 268.0, 886.0],
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(208.0, 867.5),
            hit_count=24,
            hit_boxes=[(148.0, 849.0, 268.0, 886.0)] * 4,
            hit_frames=[728, 729, 730, 731],
            hit_sharpness=[10.0] * 4,
        )
        frame = np.full((1080, 1920, 3), 245, dtype=np.uint8)
        # Endcard chip glyphs.
        frame[849:886, 148:268] = 20
        # Stronger bottom burn-in that recover would prefer if allowed.
        frame[1000:1040, 400:1500] = 240
        for x in range(420, 1480, 30):
            frame[1008:1032, x : x + 14] = 10
        out = extend_hardsub_tracks_to_ink(
            [peanut],
            frame_cache={730: frame},
            frame_w=1920,
            frame_h=1080,
        )
        self.assertEqual(len(out), 1)
        box = out[0].box_coords
        self.assertLess(abs(box[1] - 849.0), 5.0)
        self.assertLess(box[2] - box[0], 200.0)


    def test_wide_food_slab_in_band_not_kept_as_generic(self) -> None:
        """Wide thin food slabs at cy~0.80 must not SSOT; recover may promote burn-in."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            classify_ocr_box_role,
            filter_tracks_by_local_text,
        )

        # sub_08 regression class: wide rice-edge slab, not a burn-in line.
        food_slab = [1264.0, 847.0, 1828.0, 910.0]
        self.assertEqual(
            classify_ocr_box_role(food_slab, frame_w=1920, frame_h=1080),
            "generic",
        )
        slab = MergedTrack(
            start_frame=469,
            end_frame=489,
            box_coords=food_slab,
            best_frame_index=480,
            best_sharpness=8.0,
            centroid=(1546.0, 878.5),
            hit_count=4,
            hit_boxes=[(1264.0, 847.0, 1828.0, 910.0)] * 3,
            hit_frames=[478, 479, 480],
            hit_sharpness=[8.0] * 3,
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        frame[847:910, 1264:1828] = (180, 200, 220)  # food texture, no glyphs
        # Real burn-in below the slab.
        frame[1000:1040, 550:1350] = 240
        for x in range(570, 1330, 26):
            frame[1008:1032, x : x + 14] = 15
        rec = MagicMock()

        def _recognize(crop: np.ndarray) -> LocalRecognition:
            h, w = crop.shape[:2]
            if w > 400 and h < 80:
                return LocalRecognition("碳水就搭配150g米饭", 0.96, 1.0)
            return LocalRecognition("一，", 0.55, 1.0)

        rec.recognize.side_effect = _recognize
        kept, audit = filter_tracks_by_local_text(
            [slab],
            frame_cache={480: frame},
            frame_w=1920,
            frame_h=1080,
            recognizer=rec,
        )
        self.assertEqual(len(kept), 1, msg=f"must promote/keep burn-in audit={audit}")
        box = kept[0].box_coords
        cy = (box[1] + box[3]) * 0.5 / 1080.0
        self.assertGreaterEqual(cy, 0.88)
        self.assertGreater((box[2] - box[0]) / 1920.0, 0.28)
        self.assertEqual(
            classify_ocr_box_role(box, frame_w=1920, frame_h=1080),
            "hardsub",
        )


    def test_coalesce_does_not_rebuild_hardsub_from_food_hit_boxes(self) -> None:
        """Recover may fix box_coords while hit_boxes still hold food slabs."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            classify_ocr_box_role,
            coalesce_near_duplicate_tracks,
        )

        burn_in = [669.0, 979.0, 1250.0, 1041.0]
        food = (1264.0, 847.4, 1828.48, 909.5)
        self.assertEqual(
            classify_ocr_box_role(burn_in, frame_w=1920, frame_h=1080),
            "hardsub",
        )
        a = MergedTrack(
            start_frame=469,
            end_frame=485,
            box_coords=burn_in,
            best_frame_index=480,
            best_sharpness=8.0,
            centroid=(960.0, 1010.0),
            hit_count=3,
            hit_boxes=[food] * 3,
            hit_frames=[478, 479, 480],
            hit_sharpness=[8.0, 8.0, 8.0],
        )
        b = MergedTrack(
            start_frame=472,
            end_frame=489,
            box_coords=[680.0, 980.0, 1240.0, 1040.0],
            best_frame_index=482,
            best_sharpness=8.5,
            centroid=(960.0, 1010.0),
            hit_count=3,
            hit_boxes=[food] * 3,
            hit_frames=[480, 482, 484],
            hit_sharpness=[8.0, 8.5, 8.0],
        )
        out = coalesce_near_duplicate_tracks([a, b], frame_w=1920, frame_h=1080)
        self.assertEqual(len(out), 1)
        cy = (out[0].box_coords[1] + out[0].box_coords[3]) * 0.5 / 1080.0
        self.assertGreaterEqual(cy, 0.88, msg=f"food rebuild? {out[0].box_coords}")
        self.assertEqual(
            classify_ocr_box_role(out[0].box_coords, frame_w=1920, frame_h=1080),
            "hardsub",
        )

    def test_extend_hardsub_does_not_overwrite_with_food_seed(self) -> None:
        """Wider food hit_boxes must not rewrite an already-good burn-in line."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            classify_ocr_box_role,
            extend_hardsub_tracks_to_ink,
        )

        food_slab = (1264.0, 847.0, 1828.0, 910.0)
        stub = [900.0, 1008.0, 1320.0, 1048.0]
        self.assertEqual(
            classify_ocr_box_role(stub, frame_w=1920, frame_h=1080),
            "hardsub",
        )
        self.assertEqual(
            classify_ocr_box_role(food_slab, frame_w=1920, frame_h=1080),
            "generic",
        )
        track = MergedTrack(
            start_frame=469,
            end_frame=489,
            box_coords=stub,
            best_frame_index=480,
            best_sharpness=8.0,
            centroid=(1110.0, 1028.0),
            hit_count=4,
            hit_boxes=[food_slab, food_slab, tuple(stub)],
            hit_frames=[478, 479, 480],
            hit_sharpness=[8.0, 8.0, 8.0],
        )
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        frame[1005:1055, 280:1640] = 245
        for x in range(300, 1620, 28):
            frame[1012:1048, x : x + 12] = 10
        out = extend_hardsub_tracks_to_ink(
            [track],
            frame_cache={480: frame},
            frame_w=1920,
            frame_h=1080,
        )
        self.assertEqual(len(out), 1)
        cy = (out[0].box_coords[1] + out[0].box_coords[3]) * 0.5 / 1080.0
        self.assertGreaterEqual(cy, 0.88, msg=f"overwrote with food? {out[0].box_coords}")
        self.assertEqual(
            classify_ocr_box_role(out[0].box_coords, frame_w=1920, frame_h=1080),
            "hardsub",
        )

    def test_extend_uses_shrink_only_y_when_candidate_leaves_dense_core(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            extend_hardsub_tracks_to_ink,
        )

        core = (600.0, 1010.0, 1300.0, 1050.0)
        wrong_upper_band = [500.0, 991.0, 1400.0, 1017.0]
        track = MergedTrack(
            start_frame=1,
            end_frame=10,
            box_coords=list(core),
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(950.0, 1030.0),
            hit_count=10,
            hit_boxes=[core] * 10,
            hit_frames=list(range(1, 11)),
            hit_sharpness=[20.0] * 10,
        )
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        def _trim_y(
            _frame: np.ndarray,
            box: list[float],
            **kwargs: object,
        ) -> list[float]:
            if int(kwargs.get("search_pad_px", 6)) == 0:
                return [box[0], 1009.0, box[2], 1053.0]
            return list(wrong_upper_band)

        module = "src.media_pipeline.frame_sampling.master_phase1_extractor."
        with (
            patch(module + "extend_hardsub_box_to_ink", return_value=wrong_upper_band),
            patch(module + "trim_hardsub_box_to_ink", return_value=wrong_upper_band),
            patch(module + "trim_hardsub_box_y_to_ink", side_effect=_trim_y) as trim_y,
            patch(module + "tighten_hardsub_box_to_neutral_glyphs", return_value=None),
        ):
            out = extend_hardsub_tracks_to_ink(
                [track],
                frame_cache={5: frame},
                frame_w=1920,
                frame_h=1080,
            )

        self.assertEqual(out[0].box_coords[1:4:2], [1009.0, 1053.0])
        self.assertTrue(
            any(call.kwargs.get("search_pad_px") == 0 for call in trim_y.call_args_list)
        )

    def test_recover_uses_shrink_only_y_when_candidate_leaves_dense_core(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            extend_hardsub_tracks_to_ink,
        )

        narrow_core = (820.0, 1010.0, 1080.0, 1050.0)
        wrong_upper_band = [500.0, 991.0, 1400.0, 1017.0]
        track = MergedTrack(
            start_frame=1,
            end_frame=10,
            box_coords=list(narrow_core),
            best_frame_index=5,
            best_sharpness=20.0,
            centroid=(950.0, 1030.0),
            hit_count=10,
            hit_boxes=[narrow_core] * 10,
            hit_frames=list(range(1, 11)),
            hit_sharpness=[20.0] * 10,
        )
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        def _trim_y(
            _frame: np.ndarray,
            box: list[float],
            **kwargs: object,
        ) -> list[float]:
            if int(kwargs.get("search_pad_px", 6)) == 0:
                return [box[0], 1009.0, box[2], 1053.0]
            return list(wrong_upper_band)

        module = "src.media_pipeline.frame_sampling.master_phase1_extractor."
        with (
            patch(module + "recover_hardsub_box_from_band_ink", return_value=wrong_upper_band),
            patch(module + "trim_hardsub_box_y_to_ink", side_effect=_trim_y) as trim_y,
        ):
            extend_hardsub_tracks_to_ink(
                [track],
                frame_cache={5: frame},
                frame_w=1920,
                frame_h=1080,
            )

        self.assertTrue(
            any(call.kwargs.get("search_pad_px") == 0 for call in trim_y.call_args_list)
        )

    def test_coalesce_does_not_merge_stacked_endcard_rows(self) -> None:
        """花生油 + 8毫升 are separate rows — hardsub-band coalesce must not union them."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            coalesce_near_duplicate_tracks,
        )

        peanut = MergedTrack(
            start_frame=721,
            end_frame=745,
            box_coords=[148.0, 849.0, 268.0, 886.0],
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(208.0, 867.5),
            hit_count=12,
            hit_boxes=[(148.0, 849.0, 268.0, 886.0)] * 4,
            hit_frames=[728, 729, 730, 731],
            hit_sharpness=[10.0] * 4,
        )
        ml = MergedTrack(
            start_frame=721,
            end_frame=745,
            box_coords=[151.0, 901.0, 231.0, 930.0],
            best_frame_index=730,
            best_sharpness=10.0,
            centroid=(191.0, 915.5),
            hit_count=12,
            hit_boxes=[(151.0, 901.0, 231.0, 930.0)] * 4,
            hit_frames=[728, 729, 730, 731],
            hit_sharpness=[10.0] * 4,
        )
        out = coalesce_near_duplicate_tracks(
            [peanut, ml], frame_w=1920, frame_h=1080
        )
        self.assertEqual(len(out), 2)

    def test_coalesce_does_not_glue_sequential_hardsub_lines(self) -> None:
        """Different bottom lines (width jump, no time overlap) must stay separate."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            coalesce_near_duplicate_tracks,
        )

        short = MergedTrack(
            start_frame=100,
            end_frame=108,
            box_coords=[500.0, 1000.0, 900.0, 1048.0],
            best_frame_index=104,
            best_sharpness=10.0,
            centroid=(700.0, 1024.0),
            hit_count=4,
            hit_boxes=[(500.0, 1000.0, 900.0, 1048.0)] * 4,
            hit_frames=[100, 102, 104, 106],
            hit_sharpness=[10.0] * 4,
        )
        long = MergedTrack(
            start_frame=112,
            end_frame=120,
            box_coords=[350.0, 1000.0, 1550.0, 1048.0],
            best_frame_index=116,
            best_sharpness=12.0,
            centroid=(950.0, 1024.0),
            hit_count=4,
            hit_boxes=[(350.0, 1000.0, 1550.0, 1048.0)] * 4,
            hit_frames=[112, 114, 116, 118],
            hit_sharpness=[12.0] * 4,
        )
        out = coalesce_near_duplicate_tracks(
            [short, long], frame_w=1920, frame_h=1080
        )
        self.assertEqual(
            len(out),
            2,
            msg=f"sequential hardsubs glued: {[t.box_coords for t in out]}",
        )

    def test_coalesce_does_not_glue_sequential_similar_width_hardsubs(self) -> None:
        """
        Different subtitle lines often share similar centered width.

        Coalesce must not re-glue them across a time gap even when geometry
        looks compatible (Video2 mega-hardsub fossil class).
        """
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            coalesce_near_duplicate_tracks,
        )

        a = MergedTrack(
            start_frame=100,
            end_frame=150,
            box_coords=[560.0, 1005.0, 1360.0, 1050.0],
            best_frame_index=120,
            best_sharpness=10.0,
            centroid=(960.0, 1027.5),
            hit_count=20,
            hit_boxes=[(560.0, 1005.0, 1360.0, 1050.0)] * 4,
            hit_frames=[100, 110, 120, 140],
            hit_sharpness=[10.0] * 4,
        )
        b = MergedTrack(
            start_frame=160,
            end_frame=210,
            box_coords=[580.0, 1004.0, 1340.0, 1052.0],
            best_frame_index=180,
            best_sharpness=11.0,
            centroid=(960.0, 1028.0),
            hit_count=20,
            hit_boxes=[(580.0, 1004.0, 1340.0, 1052.0)] * 4,
            hit_frames=[160, 170, 180, 200],
            hit_sharpness=[11.0] * 4,
        )
        out = coalesce_near_duplicate_tracks(
            [a, b], frame_w=1920, frame_h=1080
        )
        self.assertEqual(
            len(out),
            2,
            msg=f"similar-width sequential hardsubs glued: {[t.box_coords for t in out]}",
        )

    def test_coalesce_does_not_glue_pad_touching_hardsub_lines(self) -> None:
        """Lifespans that only touch at a pad boundary must stay separate rows."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            MergedTrack,
            coalesce_near_duplicate_tracks,
        )

        a = MergedTrack(
            start_frame=100,
            end_frame=194,
            box_coords=[571.0, 1000.0, 1353.0, 1048.0],
            best_frame_index=150,
            best_sharpness=10.0,
            centroid=(962.0, 1024.0),
            hit_count=40,
            hit_boxes=[(571.0, 1000.0, 1353.0, 1048.0)] * 4,
            hit_frames=[100, 120, 150, 190],
            hit_sharpness=[10.0] * 4,
        )
        b = MergedTrack(
            start_frame=194,
            end_frame=250,
            box_coords=[765.0, 998.0, 1165.0, 1054.0],
            best_frame_index=220,
            best_sharpness=11.0,
            centroid=(965.0, 1026.0),
            hit_count=20,
            hit_boxes=[(765.0, 998.0, 1165.0, 1054.0)] * 4,
            hit_frames=[194, 200, 220, 248],
            hit_sharpness=[11.0] * 4,
        )
        out = coalesce_near_duplicate_tracks(
            [a, b], frame_w=1920, frame_h=1080
        )
        self.assertEqual(
            len(out),
            2,
            msg=f"pad-touch hardsubs glued: {[t.box_coords for t in out]}",
        )


if __name__ == "__main__":
    unittest.main()
