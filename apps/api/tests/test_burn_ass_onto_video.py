"""Unit tests for ASS burn-in helper (final complete video)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src.media_pipeline.video_renderer.video_cleaner_and_sub import burn_ass_onto_video


class BurnAssOntoVideoTests(unittest.TestCase):
    def test_burn_invokes_ffmpeg_with_ass_basename_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video = root / "cleaned_video.mp4"
            ass = root / "vietnamese_sub.ass"
            out = root / "final_complete.mp4"
            writer = cv2.VideoWriter(
                str(video),
                cv2.VideoWriter_fourcc(*"mp4v"),
                5.0,
                (64, 48),
            )
            for _ in range(5):
                writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
            writer.release()
            ass.write_text(
                "[Script Info]\nScriptType: v4.00+\n\n"
                "[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding\n"
                "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
                "0,0,0,0,100,100,0,0,1,2,1,2,10,10,10,1\n\n"
                "[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hello\n",
                encoding="utf-8",
            )

            with patch(
                "src.media_pipeline.video_renderer.video_cleaner_and_sub.subprocess.run"
            ) as run:

                def _side_effect(cmd, **kwargs):
                    out.write_bytes(b"mp4")
                    return type(
                        "Completed",
                        (),
                        {"returncode": 0, "stdout": "", "stderr": ""},
                    )()

                run.side_effect = _side_effect
                result = burn_ass_onto_video(video, ass, out)

            self.assertEqual(result, out.resolve())
            run.assert_called_once()
            cmd = run.call_args.args[0]
            kwargs = run.call_args.kwargs
            self.assertIn("ffmpeg", cmd[0])
            vf = next(c for c in cmd if isinstance(c, str) and c.startswith("ass="))
            self.assertEqual(vf, f"ass={ass.name}")
            self.assertEqual(Path(kwargs["cwd"]), ass.resolve().parent)


if __name__ == "__main__":
    unittest.main()
