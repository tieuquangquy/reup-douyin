from __future__ import annotations

import unittest

from src.downloaders.source_video_filename import (
    build_source_video_raw_filename,
    parse_height_from_format_label,
)
from src.storage.path_strategy import profile_storage_folder


class FormatHeightParseTests(unittest.TestCase):
    def test_parses_1080p_token_from_playwright_format_label(self) -> None:
        self.assertEqual(parse_height_from_format_label("play_addr|1080p|br30178359"), 1080)
        self.assertEqual(parse_height_from_format_label("bit_rate|720p|br1"), 720)
        self.assertIsNone(parse_height_from_format_label("play_addr|br123"))
        self.assertIsNone(parse_height_from_format_label(None))

    def test_filename_uses_parsed_height_when_primary_height_missing(self) -> None:
        from datetime import UTC, datetime

        height = parse_height_from_format_label("play_addr|1080p|br1")
        name = build_source_video_raw_filename(
            aweme_id="123",
            caption="test",
            watermark_free=True,
            posted_at=datetime(2026, 1, 2, tzinfo=UTC),
            height=height,
        )
        self.assertTrue(name.endswith("__1080p__nl.mp4"))
        self.assertNotIn("__unkp__", name)


class ProfileFolderLabelTests(unittest.TestCase):
    def test_prefers_handle_over_generic_user(self) -> None:
        folder = profile_storage_folder(
            handle="Agu_z",
            display_name="阿古",
            source_profile_external_id="MS4wLjABAAAA965SRwbGiCEbLONG",
        )
        self.assertTrue(folder.startswith("@Agu_z__"))
        self.assertNotIn("@user__", folder)

    def test_falls_back_to_display_name_when_handle_missing(self) -> None:
        folder = profile_storage_folder(
            handle=None,
            display_name="阿古同学",
            source_profile_external_id="MS4wLjABAAAA965SRwbGiCEbLONG",
        )
        self.assertTrue(folder.startswith("@"))
        self.assertNotIn("@user__", folder)


if __name__ == "__main__":
    unittest.main()
