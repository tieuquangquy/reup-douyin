"""Phase 1 frame sampling: STRICT 1|2 fps only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode
from src.media_pipeline.frame_sampling.ffmpeg_engine import extract_video_frames, normalize_sample_fps
from src.media_pipeline.frame_sampling.job import FrameSamplingJobRequest, run_frame_sampling_job
from src.media_pipeline.frame_sampling.types import SampleFps


class NormalizeSampleFpsTests(unittest.TestCase):
    def test_accepts_exactly_1_and_2(self) -> None:
        self.assertEqual(normalize_sample_fps(1), 1)
        self.assertEqual(normalize_sample_fps(1.0), 1)
        self.assertEqual(normalize_sample_fps(2), 2)
        self.assertEqual(normalize_sample_fps(2.0), 2)

    def test_rejects_other_rates(self) -> None:
        for bad in (0.5, 1.5, 3.0, 5.0, 24.0, 30.0, 0, -1):
            with self.subTest(bad=bad):
                with self.assertRaises(FrameSamplingError) as ctx:
                    normalize_sample_fps(bad)
                self.assertEqual(ctx.exception.code, FrameSamplingErrorCode.INVALID_SAMPLE_FPS)


class ExtractVideoFramesTests(unittest.TestCase):
    def test_extract_returns_frame_paths_via_ffmpeg_fps_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clip.mp4"
            video.write_bytes(b"fake-mp4")
            out = root / "frames"

            def fake_run(cmd, **_kwargs):
                out.mkdir(parents=True, exist_ok=True)
                if "thumbnail.jpg" in str(cmd[-1]):
                    Path(cmd[-1]).write_bytes(b"jpg")
                    return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()
                # Ensure STRICT fps filter is present and not a full dump.
                self.assertIn("-vf", cmd)
                vf = cmd[cmd.index("-vf") + 1]
                self.assertIn(vf, ("fps=1", "fps=2"))
                self.assertNotIn("select=", vf)
                for i in range(1, 4):
                    (out / f"frame_{i:06d}.jpg").write_bytes(b"jpg")
                return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()

            with patch("src.media_pipeline.frame_sampling.ffmpeg_engine.shutil.which", return_value="ffmpeg"):
                with patch("src.media_pipeline.frame_sampling.ffmpeg_engine.subprocess.run", side_effect=fake_run):
                    frames = extract_video_frames(video, out, sample_fps=1)

            self.assertEqual(len(frames), 4)  # thumbnail + 3 samples
            self.assertTrue(all(p.is_file() for p in frames))
            self.assertEqual(frames[0].name, "thumbnail.jpg")
            self.assertEqual(
                [p.name for p in frames[1:]],
                ["frame_000001.jpg", "frame_000002.jpg", "frame_000003.jpg"],
            )

    def test_job_returns_paths_for_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "in.mp4"
            video.write_bytes(b"x")
            out = root / "out"

            def fake_run(cmd, **_kwargs):
                out.mkdir(parents=True, exist_ok=True)
                if "thumbnail.jpg" in str(cmd[-1]):
                    Path(cmd[-1]).write_bytes(b"jpg")
                    return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()
                (out / "frame_000001.jpg").write_bytes(b"jpg")
                return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()

            with patch("src.media_pipeline.frame_sampling.ffmpeg_engine.shutil.which", return_value="ffmpeg"):
                with patch("src.media_pipeline.frame_sampling.ffmpeg_engine.subprocess.run", side_effect=fake_run):
                    result = run_frame_sampling_job(
                        FrameSamplingJobRequest(
                            video_source=str(video),
                            output_dir=str(out),
                            sample_fps=2,
                        )
                    )

            self.assertEqual(result.sample_fps, 2)
            self.assertEqual(result.frame_count, 2)  # thumbnail + 1 sample
            self.assertEqual(len(result.frame_paths), 2)
            self.assertEqual(Path(result.frame_paths[0]).name, "thumbnail.jpg")
            self.assertTrue(Path(result.frame_paths[0]).is_file())
            self.assertTrue(Path(result.frame_paths[1]).is_file())


class SampleFpsTypeTests(unittest.TestCase):
    def test_sample_fps_literal_values(self) -> None:
        allowed: list[SampleFps] = [1, 2]
        self.assertEqual(allowed, [1, 2])


if __name__ == "__main__":
    unittest.main()
