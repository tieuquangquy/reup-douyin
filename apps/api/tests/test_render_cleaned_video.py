"""Render prefers CLEANED_VIDEO when present."""

from __future__ import annotations

import inspect
import unittest

from src.render_pipeline.services import render_input_resolver
from src.tts_pipeline.services import render_prep_manifest_builder


class RenderCleanedVideoContractTests(unittest.TestCase):
    def test_resolver_prefers_cleaned_video(self) -> None:
        source = inspect.getsource(render_input_resolver.RenderInputResolver.resolve)
        self.assertIn("CLEANED_VIDEO", source)
        self.assertIn("SOURCE_VIDEO_RAW", source)
        self.assertIn("using_cleaned_video", source)
        self.assertIn("no_cleaned_video_fallback_raw", source)

    def test_render_service_merges_cleaned_and_subtitle_warnings(self) -> None:
        from src.render_pipeline.services import render_service

        source = inspect.getsource(render_service.RenderService.run_render)
        self.assertIn("prepare_srt_file_for_burn", source)
        self.assertIn("merged_warnings", source)
        self.assertIn("no_cleaned_video_fallback_raw", inspect.getsource(render_input_resolver.RenderInputResolver.resolve))



if __name__ == "__main__":
    unittest.main()
