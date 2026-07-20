"""OCR sampling must include a near-EOF still — endcard UI often lasts <1s after the last 1fps tick."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.media_pipeline.frame_sampling.ffmpeg_engine import extract_video_frames_detailed
from src.media_pipeline.video_renderer.overlays import overlays_from_ocr_payload
from src.media_pipeline.video_renderer.inpaint_render import _active_segments


class SampleIncludesEofFrameTests(unittest.TestCase):
    def test_1fps_grid_plus_eof_when_duration_past_last_tick(self) -> None:
        """29.3s clip @ 1fps yields ticks 0..28s; must also sample ~EOF for nutrition UI."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clip.mp4"
            video.write_bytes(b"fake-mp4")
            out = root / "frames"
            calls: list[list[str]] = []

            def fake_run(cmd, **_kwargs):
                calls.append([str(c) for c in cmd])
                out.mkdir(parents=True, exist_ok=True)
                dest = Path(cmd[-1])
                if dest.name == "thumbnail.jpg":
                    dest.write_bytes(b"jpg")
                    return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()
                if "fps=" in " ".join(str(c) for c in cmd):
                    # 29 ticks → indices 0..28 → 29 files from fps filter
                    for i in range(1, 30):
                        (out / f"frame_{i:06d}.jpg").write_bytes(b"jpg")
                    return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()
                # EOF still extract
                dest.write_bytes(b"jpg-eof")
                return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()

            with patch(
                "src.media_pipeline.frame_sampling.ffmpeg_engine.shutil.which",
                return_value="ffmpeg",
            ):
                with patch(
                    "src.media_pipeline.frame_sampling.ffmpeg_engine.subprocess.run",
                    side_effect=fake_run,
                ):
                    with patch(
                        "src.media_pipeline.frame_sampling.ffmpeg_engine.probe_duration_ms",
                        return_value=29300,
                    ):
                        frames = extract_video_frames_detailed(video, out, sample_fps=1)

            times = [f.time_ms for f in frames if f.path.name != "thumbnail.jpg"]
            self.assertEqual(times[0], 0)
            self.assertEqual(times[-2], 28000)  # last 1fps tick
            self.assertGreaterEqual(times[-1], 29000)  # near-EOF still
            self.assertLessEqual(times[-1], 29300)
            self.assertTrue(any("sseof" in " ".join(c) or "-ss" in c for c in calls))


class EofNutritionOverlayHoldTests(unittest.TestCase):
    def test_nutrition_eof_sample_replaces_prior_cta_hold(self) -> None:
        """CTA at 28s must not stay active alone once nutrition UI is OCR'd at ~29.3s."""
        cta = {
            "frame_id": "t28000",
            "time_ms": 28000,
            "boxes": [
                {
                    "x": 0.34,
                    "y": 0.0,
                    "width": 0.42,
                    "height": 0.43,
                    "text": "减脂期的朋友给个关注吧",
                }
            ],
        }
        nutrition = {
            "frame_id": "t29250",
            "time_ms": 29250,
            "boxes": [
                {"x": 0.08, "y": 0.06, "width": 0.22, "height": 0.06, "text": "午餐"},
                {"x": 0.15, "y": 0.28, "width": 0.22, "height": 0.04, "text": "蛋白质"},
                {"x": 0.70, "y": 0.26, "width": 0.18, "height": 0.08, "text": "525千卡"},
                {"x": 0.12, "y": 0.50, "width": 0.25, "height": 0.05, "text": "米饭"},
                {"x": 0.12, "y": 0.60, "width": 0.28, "height": 0.05, "text": "花生油"},
                {"x": 0.12, "y": 0.70, "width": 0.18, "height": 0.05, "text": "虾"},
                {"x": 0.12, "y": 0.78, "width": 0.18, "height": 0.05, "text": "鸡蛋"},
            ],
        }
        vi = {
            "28000#0": "Thich thi theo doi nhe",
            **{f"29250#{i}": f"VI{i}" for i in range(7)},
        }
        overlays = overlays_from_ocr_payload(
            {"frames": [cta, nutrition]},
            vi,
            hold_ms=500,
            video_duration_ms=29300,
        )
        active = _active_segments(overlays, 29250)
        kinds = {seg.kind for seg in active}
        self.assertIn("dense_ui", kinds)
        self.assertTrue(any(seg.text_vi.startswith("VI") for seg in active))
        # Prior CTA must have ended before nutrition start (no top-only CTA wipe).
        cta_segs = [seg for seg in overlays if seg.text_vi == "Thich thi theo doi nhe"]
        self.assertEqual(len(cta_segs), 1)
        self.assertLessEqual(cta_segs[0].end_ms, 29250)


if __name__ == "__main__":
    unittest.main()
