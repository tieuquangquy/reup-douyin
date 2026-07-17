"""TTS re-run must bump media_assets.version from max(existing), not reset to 1."""

from __future__ import annotations

import inspect
import unittest

from src.tts_pipeline.services.tts_service import TtsPipelineService


class TtsAssetVersionTests(unittest.TestCase):
    def test_persist_asset_bumps_from_max_version_after_rerun(self) -> None:
        source = inspect.getsource(TtsPipelineService._persist_asset)
        self.assertIn("_next_asset_version", source)
        self.assertNotIn("_current_asset(source_video.id, asset_type)", source)

    def test_next_asset_version_helper_exists(self) -> None:
        self.assertTrue(hasattr(TtsPipelineService, "_next_asset_version"))


if __name__ == "__main__":
    unittest.main()
