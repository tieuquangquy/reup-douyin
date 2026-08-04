"""Pre-render finalize: track overlay SSOT, VI burn gate, overlay fossils."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.media_pipeline.video_renderer.overlays import gate_vi_for_burn
from src.media_pipeline.video_renderer.render_finalize import (
    finalize_overlays_for_render,
)


class GateViTests(unittest.TestCase):
    def test_drops_ellipsis_and_residual_cjk(self) -> None:
        self.assertEqual(gate_vi_for_burn("..."), "")
        self.assertEqual(gate_vi_for_burn("加盐"), "")
        self.assertEqual(gate_vi_for_burn("Thêm muối"), "Thêm muối")


class TrackOverlaySsotTests(unittest.TestCase):
    def test_one_segment_per_track_not_per_stamp(self) -> None:
        payload = {
            "authority": "master_phase1",
            "fps": 30.0,
            "frame_count": 90,
            "frame_width": 1000,
            "frame_height": 1000,
            "master_timeline": [
                {
                    "text_id": "sub_01",
                    "start_frame": 30,
                    "end_frame": 60,
                    "box_coords": [100.0, 800.0, 400.0, 880.0],
                    "ocr_text": "加盐",
                    "translate_ready": True,
                }
            ],
            "frames": [
                {
                    "time_ms": 1000,
                    "boxes": [
                        {
                            "text": "加盐",
                            "text_id": "sub_01",
                            "translate_ready": True,
                            "x": 0.1,
                            "y": 0.8,
                            "w": 0.3,
                            "h": 0.08,
                        }
                    ],
                },
                {
                    "time_ms": 1033,
                    "boxes": [
                        {
                            "text": "加盐",
                            "text_id": "sub_01",
                            "translate_ready": True,
                            "x": 0.1,
                            "y": 0.8,
                            "w": 0.3,
                            "h": 0.08,
                        }
                    ],
                },
                {
                    "time_ms": 1066,
                    "boxes": [
                        {
                            "text": "加盐",
                            "text_id": "sub_01",
                            "translate_ready": True,
                            "x": 0.1,
                            "y": 0.8,
                            "w": 0.3,
                            "h": 0.08,
                        }
                    ],
                },
            ],
        }
        vi = {
            "1000#0": "Thêm muối",
            "1033#0": "Thêm muối",
            "1066#0": "Thêm muối",
        }
        overlays, stats = finalize_overlays_for_render(payload, vi)
        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0].text_vi, "Thêm muối")
        self.assertEqual(overlays[0].start_ms, 1000)  # frame 30 @ 30fps
        self.assertEqual(overlays[0].end_ms, 2033)  # frame 61 exclusive ≈ 2033
        self.assertTrue(stats.get("coalesced"))
        self.assertEqual(stats.get("source"), "master_timeline")

    def test_bad_vi_cover_without_burn(self) -> None:
        payload = {
            "fps": 30.0,
            "frame_count": 60,
            "frame_width": 1000,
            "frame_height": 1000,
            "master_timeline": [
                {
                    "text_id": "sub_01",
                    "start_frame": 0,
                    "end_frame": 10,
                    "box_coords": [0.0, 800.0, 300.0, 900.0],
                    "ocr_text": "加盐",
                    "translate_ready": True,
                }
            ],
            "frames": [
                {
                    "time_ms": 0,
                    "boxes": [
                        {
                            "text": "加盐",
                            "text_id": "sub_01",
                            "translate_ready": True,
                            "x": 0.0,
                            "y": 0.8,
                            "w": 0.3,
                            "h": 0.1,
                        }
                    ],
                }
            ],
        }
        overlays, stats = finalize_overlays_for_render(
            payload, {"0#0": "..."}
        )
        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0].text_vi, "")
        self.assertGreaterEqual(int(stats.get("vi_dropped") or 0), 1)
        # Geometry still present for cover.
        self.assertGreater(overlays[0].width, 0.0)

    def test_deterministic_render_text_is_burned_without_llm_translation(self) -> None:
        payload = {
            "fps": 30.0,
            "frame_count": 60,
            "frame_width": 1000,
            "frame_height": 1000,
            "master_timeline": [
                {
                    "text_id": "sub_02",
                    "start_frame": 0,
                    "end_frame": 10,
                    "box_coords": [100.0, 100.0, 300.0, 180.0],
                    "ocr_text": "510千卡",
                    "translate_ready": False,
                    "localization_mode": "deterministic",
                    "render_text_approved": "510 kcal",
                }
            ],
            "frames": [],
        }

        overlays, stats = finalize_overlays_for_render(payload, {})

        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0].text_vi, "510 kcal")
        self.assertEqual(stats["deterministic"], 1)
        self.assertEqual(stats["cover_only"], 0)


class FossilTests(unittest.TestCase):
    def test_writes_overlay_fossils(self) -> None:
        payload = {
            "fps": 30.0,
            "frame_count": 30,
            "frame_width": 1000,
            "frame_height": 1000,
            "master_timeline": [
                {
                    "text_id": "sub_01",
                    "start_frame": 0,
                    "end_frame": 5,
                    "box_coords": [10.0, 10.0, 100.0, 50.0],
                    "ocr_text": "加盐",
                    "translate_ready": True,
                }
            ],
            "frames": [
                {
                    "time_ms": 0,
                    "boxes": [
                        {
                            "text": "加盐",
                            "text_id": "sub_01",
                            "translate_ready": True,
                            "x": 0.01,
                            "y": 0.01,
                            "w": 0.09,
                            "h": 0.04,
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp)
            overlays, _stats = finalize_overlays_for_render(
                payload,
                {"0#0": "Thêm muối"},
                artifact_dir=art,
            )
            self.assertTrue((art / "overlays.json").is_file())
            self.assertTrue((art / "overlay_stats.json").is_file())
            rows = json.loads((art / "overlays.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text_vi"], "Thêm muối")
            self.assertEqual(len(overlays), 1)


if __name__ == "__main__":
    unittest.main()
