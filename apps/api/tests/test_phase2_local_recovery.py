from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    _recover_failed_ocr_tracks,
    ocr_timeline_keyframes,
)
from src.media_pipeline.frame_sampling.phase2_local_recovery import (
    RecoveryObservation,
    choose_recovery_consensus,
    expanded_recovery_box,
    reconcile_temporal_shadow_tracks,
    recovery_frame_indices,
    recovery_variants,
    repeated_recovered_source_ui_indices,
)


class Phase2LocalRecoveryUnitTests(unittest.TestCase):
    def test_frame_selection_is_bounded_and_uses_temporal_hits(self) -> None:
        selected = recovery_frame_indices(
            {
                "start_frame": 10,
                "end_frame": 30,
                "best_frame_index": 22,
                "hit_frames": [12, 18, 24, 29],
            }
        )
        self.assertEqual(selected, [22, 12])

    def test_recognition_box_expands_but_clamps_to_source(self) -> None:
        self.assertEqual(
            expanded_recovery_box(
                [2.0, 3.0, 98.0, 47.0],
                frame_width=100,
                frame_height=50,
            ),
            [0, 0, 100, 50],
        )

    def test_recovery_variants_keep_large_recognition_height(self) -> None:
        crop = np.full((42, 320, 3), 30, dtype=np.uint8)
        crop[8:34, 20:300] = 220
        variants = recovery_variants(crop)
        self.assertEqual(len(variants), 3)
        self.assertTrue(all(image.shape[0] > 112 for _name, image in variants))

    def test_temporal_consensus_beats_single_sharp_outlier(self) -> None:
        result = choose_recovery_consensus(
            [
                RecoveryObservation(0, 10, "raw", "加盐", 20.0),
                RecoveryObservation(0, 12, "clahe", "加盐", 25.0),
                RecoveryObservation(0, 14, "raw", "加糖", 500.0),
            ]
        )
        assert result is not None
        self.assertEqual(result["text"], "加盐")
        self.assertEqual(result["method"], "temporal_consensus")
        self.assertEqual(result["frame_support"], 2)

    def test_repeated_short_ui_label_is_preserved_fail_closed(self) -> None:
        tracks = [
            {
                "start_frame": 100,
                "end_frame": 105,
                "box_coords": [700, 820, 1050, 875],
                "ocr_text": "素材",
                "ocr_recovery": {"status": "RECOVERED_FOR_OPERATOR_REVIEW"},
            },
            {
                "start_frame": 180,
                "end_frame": 185,
                "box_coords": [702, 821, 1052, 876],
                "ocr_text": "素材",
                "ocr_recovery": {"status": "RECOVERED_FOR_OPERATOR_REVIEW"},
            },
        ]
        self.assertEqual(
            repeated_recovered_source_ui_indices(
                tracks,
                frame_width=1920,
                frame_height=1080,
            ),
            {0, 1},
        )

    def test_empty_short_track_inside_caption_authority_is_purged(self) -> None:
        timeline = [
            {
                "text_id": "sub_19",
                "start_frame": 1426,
                "end_frame": 1605,
                "hit_count": 11,
                "box_coords": [343.5, 1936.12, 1081.15, 2010.10],
                "ocr_text": "需要把眼尾撑开抬高",
            },
            {
                "text_id": "sub_21",
                "start_frame": 1573,
                "end_frame": 1586,
                "hit_count": 2,
                "box_coords": [30.0, 2280.0, 1154.0, 2430.0],
                "ocr_source": "failed",
            },
        ]

        kept, audit = reconcile_temporal_shadow_tracks(
            timeline,
            frame_width=1440,
            frame_height=2560,
            fps=43.97,
        )

        self.assertEqual([row["text_id"] for row in kept], ["sub_19"])
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["shadow_text_id"], "sub_21")
        self.assertEqual(audit[0]["host_text_id"], "sub_19")


class Phase2LocalRecoveryIntegrationTests(unittest.TestCase):
    def test_failed_crop_retries_with_dominant_neighbor_geometry(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "clip.mp4"
            source.write_bytes(b"fixture")
            frame = np.full((2560, 1440, 3), 35, dtype=np.uint8)
            timeline = [
                {
                    "text_id": "sub_19",
                    "start_frame": 1426,
                    "end_frame": 1605,
                    "hit_count": 11,
                    "box_coords": [343.5, 1936.12, 1081.15, 2010.10],
                    "ocr_text": "需要把眼尾撑开抬高",
                    "ocr_source": "crop",
                },
                {
                    "text_id": "sub_21",
                    "start_frame": 1573,
                    "end_frame": 1586,
                    "best_frame_index": 1584,
                    "hit_frames": [1575, 1584],
                    "hit_count": 2,
                    "box_coords": [30.0, 2280.0, 1154.0, 2430.0],
                    "ocr_source": "failed",
                },
            ]

            with patch(
                "src.media_pipeline.frame_sampling.phase2_local_recovery."
                "decode_selected_frames",
                return_value={1575: frame, 1584: frame},
            ), patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor."
                "_recognize_batch_sync",
                return_value=["需要把眼尾撑开抬高", "需要把眼尾撑开抬高"],
            ):
                _recover_failed_ocr_tracks(
                    timeline,
                    source=source,
                    boxes=[row["box_coords"] for row in timeline],
                    roles=["generic", "hardsub"],
                    dump_dir=root / "qa" / "ocr_inputs",
                    endpoint_url=None,
                    cache=None,
                )

        recovered = timeline[1]
        self.assertEqual(recovered["ocr_text"], "需要把眼尾撑开抬高")
        self.assertEqual(
            recovered["geometry_recovery"]["status"],
            "LOCAL_DERIVED_TEMPORAL_CONSENSUS",
        )
        self.assertEqual(
            recovered["geometry_recovery"]["derived_box_coords"],
            [343.5, 1936.12, 1081.15, 2010.1],
        )

    def test_primary_failures_are_recovered_without_geometry_mutation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            crop = np.full((50, 300, 3), 40, dtype=np.uint8)
            cv2.imwrite(str(root / "crops" / "sub_01.jpg"), crop)
            video = root / "clip.mp4"
            video.write_bytes(b"fixture")
            frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
            frame[460:550, 760:1100] = 220
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 10,
                    "end_frame": 20,
                    "best_frame_index": 12,
                    "hit_frames": [12, 18],
                    "box_coords": [800.0, 480.0, 1000.0, 530.0],
                    "crop_path": "crops/sub_01.jpg",
                }
            ]
            original_geometry = list(timeline[0]["box_coords"])
            calls = {"count": 0}

            def recognize(items):  # noqa: ANN001
                calls["count"] += 1
                if calls["count"] <= 3:
                    return [None] * len(items)
                return ["加盐"] * len(items)

            with patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor."
                "_recognize_batch_sync",
                side_effect=recognize,
            ), patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor._read_frame",
                return_value=frame,
            ), patch(
                "src.media_pipeline.frame_sampling.phase2_local_recovery."
                "decode_selected_frames",
                return_value={12: frame, 18: frame},
            ):
                result = ocr_timeline_keyframes(
                    timeline,
                    root_dir=root,
                    video_path=video,
                )

        self.assertEqual(result[0]["ocr_text"], "加盐")
        self.assertEqual(result[0]["ocr_source"], "local_temporal_recovery")
        self.assertEqual(result[0]["box_coords"], original_geometry)
        self.assertEqual(
            result[0]["ocr_recovery"]["status"],
            "RECOVERED_FOR_OPERATOR_REVIEW",
        )
        self.assertEqual(result[0]["ocr_recovery"]["frame_support"], 2)

    def test_hardsub_geometry_is_derived_only_after_temporal_consensus(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            cv2.imwrite(
                str(root / "crops" / "sub_01.jpg"),
                np.full((60, 400, 3), 40, dtype=np.uint8),
            )
            video = root / "clip.mp4"
            video.write_bytes(b"fixture")
            frame = np.full((1920, 1080, 3), 35, dtype=np.uint8)
            frame[1460:1530, 220:880] = 220
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 10,
                    "end_frame": 20,
                    "best_frame_index": 12,
                    "hit_frames": [12, 18],
                    # Deliberately offset hardsub geometry.
                    "box_coords": [80.0, 1700.0, 700.0, 1760.0],
                    "crop_path": "crops/sub_01.jpg",
                }
            ]
            original_geometry = list(timeline[0]["box_coords"])
            calls = {"count": 0}

            def recognize(items):  # noqa: ANN001
                calls["count"] += 1
                # Primary crop + fallback fail; the bounded recovery batch wins.
                if calls["count"] < 4:
                    return [None] * len(items)
                return ["字幕内容"] * len(items)

            with patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor."
                "_recognize_batch_sync",
                side_effect=recognize,
            ), patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor._read_frame",
                return_value=frame,
            ), patch(
                "src.media_pipeline.frame_sampling.phase2_local_recovery."
                "decode_selected_frames",
                return_value={12: frame, 18: frame},
            ), patch(
                "src.media_pipeline.frame_sampling.phase2_local_recovery."
                "hardsub_geometry_candidates",
                return_value=[
                    {"box_xyxy": [200.0, 1450.0, 900.0, 1540.0], "score": 0.9}
                ],
            ):
                result = ocr_timeline_keyframes(
                    timeline,
                    root_dir=root,
                    video_path=video,
                    frame_width=1080,
                    frame_height=1920,
                )

        self.assertEqual(result[0]["ocr_text"], "字幕内容")
        self.assertNotEqual(result[0]["box_coords"], original_geometry)
        self.assertEqual(
            result[0]["geometry_recovery"]["status"],
            "LOCAL_DERIVED_TEMPORAL_CONSENSUS",
        )
        self.assertEqual(result[0]["geometry_recovery"]["original_box_coords"], original_geometry)
        self.assertTrue(str(result[0]["crop_path"]).endswith("qa/geometry_recovery/sub_01.jpg"))


if __name__ == "__main__":
    unittest.main()
