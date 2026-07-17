import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from src.render_pipeline.runners.ffmpeg_runner import build_subtitles_vf
from src.render_pipeline.runners.mock import CopyMockRenderRunner
from src.render_pipeline.services.output_validator import validate_render_output
from src.render_pipeline.services.render_manifest_builder import build_render_manifest
from src.render_pipeline.types import ExportInput, RenderProfile, ResolvedRenderInput, VideoProbe


class RenderPipelineTests(unittest.TestCase):
    def test_subtitles_vf_escapes_windows_drive_colon(self) -> None:
        vf = build_subtitles_vf(r"C:\Users\PC\Desktop\reup_douyin\data\storage\workspace\@Agu\metadata\subs.srt")
        self.assertTrue(vf.startswith("subtitles="))
        self.assertIn("C\\:/Users/PC/Desktop", vf)
        self.assertNotIn("subtitles=C:/", vf)
        self.assertIn("subs.srt", vf)

    def test_subtitles_vf_includes_readable_force_style(self) -> None:
        vf = build_subtitles_vf("subs.srt")
        self.assertIn("force_style=", vf)
        self.assertIn("Fontsize=", vf)
        self.assertIn("MarginV=", vf)

    def test_subtitles_vf_basename_has_no_drive_colon(self) -> None:
        vf = build_subtitles_vf("7449357262730136851__v3_TTS_PIPELINE_V1_RUN_3_subtitles.srt")
        self.assertTrue(vf.startswith("subtitles='7449357262730136851__v3_TTS_PIPELINE_V1_RUN_3_subtitles.srt'"))
        self.assertIn("force_style=", vf)

    def test_subtitles_vf_escapes_comma_and_quote_in_path(self) -> None:
        vf = build_subtitles_vf(r"C:\tmp\file,name's.srt")
        self.assertIn("\\,", vf)
        self.assertIn("\\'", vf)

    def test_mock_runner_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mp4"
            narration = Path(tmp) / "voice.wav"
            subtitle = Path(tmp) / "subtitle.srt"
            output = Path(tmp) / "final.mp4"
            source.write_bytes(b"video")
            narration.write_bytes(b"audio")
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chao\n")

            result = CopyMockRenderRunner().export(
                ExportInput(
                    source_video_path=str(source),
                    narration_path=str(narration),
                    subtitle_path=str(subtitle),
                    output_path=str(output),
                    profile=RenderProfile(),
                    source_probe=VideoProbe(width=720, height=1280, fps=30, duration_seconds=1),
                )
            )
            self.assertTrue(Path(result.output_path).exists())
            self.assertIn("mock_export_runner", result.warnings)

    def test_output_validator_accepts_non_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "final.mp4"
            output.write_bytes(b"rendered")
            validate_render_output(
                str(output),
                VideoProbe(width=None, height=None, fps=None, duration_seconds=None),
                VideoProbe(width=None, height=None, fps=None, duration_seconds=None),
            )

    def test_render_manifest_shape(self) -> None:
        resolved = ResolvedRenderInput(
            source_video_id=uuid4(),
            render_prep_manifest={"manifest_version": "RENDER_PREP_MANIFEST_V1"},
            source_video_storage_key="workspace/video/raw/source.mp4",
            narration_storage_key="workspace/video/audio/voice.wav",
            subtitle_storage_key="workspace/video/metadata/subtitle.srt",
            render_prep_manifest_asset_id=uuid4(),
        )
        manifest = build_render_manifest(
            source_video_id=str(resolved.source_video_id),
            render_output_id=str(uuid4()),
            render_version="RENDER_PIPELINE_V1_RUN_1",
            resolved_input=resolved,
            output_asset={"id": str(uuid4()), "storage_key": "workspace/video/renders/final.mp4"},
            render_profile=RenderProfile(),
            input_probe=VideoProbe(width=720, height=1280, fps=30, duration_seconds=20),
            output_probe=VideoProbe(width=720, height=1280, fps=30, duration_seconds=20),
            warnings=[],
            job_id=None,
        )
        self.assertEqual(manifest["manifest_version"], "RENDER_MANIFEST_V1")
        self.assertEqual(manifest["render_settings"]["audio_strategy"], "replace_with_vietnamese_narration")
        self.assertEqual(manifest["inputs"]["narration_storage_key"], resolved.narration_storage_key)


if __name__ == "__main__":
    unittest.main()
