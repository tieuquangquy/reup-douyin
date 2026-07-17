from __future__ import annotations

import unittest
from datetime import UTC, datetime

from src.downloaders.source_video_filename import build_source_video_raw_filename
from src.enums import MediaAssetType, SourcePlatformEnum
from src.storage.path_strategy import (
    VideoStorageContext,
    asset_logical_key,
    profile_storage_folder,
    video_storage_prefix,
)


class OperatorProfileFolderTests(unittest.TestCase):
    def test_profile_folder_uses_handle_and_sec_short(self) -> None:
        folder = profile_storage_folder(
            handle="Agu_z",
            display_name="阿古",
            source_profile_external_id="MS4wLjABAAAA965SRwbGiCEbLONGSTRING",
        )
        self.assertTrue(folder.startswith("@"))
        self.assertIn("Agu_z", folder)
        self.assertIn("__MS4wLjAB", folder)
        self.assertLessEqual(len(folder), 80)

    def test_profile_folder_falls_back_to_user_when_no_handle(self) -> None:
        folder = profile_storage_folder(
            handle=None,
            display_name=None,
            source_profile_external_id="MS4wLjABAAAA965SRwbGiCEb",
        )
        self.assertTrue(folder.startswith("@user__"))

    def test_videos_from_same_profile_share_prefix(self) -> None:
        ctx_a = VideoStorageContext(
            workspace_id="ws1",
            source_platform=SourcePlatformEnum.DOUYIN,
            source_profile_external_id="MS4wLjABAAAA965SRwbGiCEbLONG",
            source_video_external_id="111",
            profile_handle="chef",
            profile_display_name="Chef",
        )
        ctx_b = VideoStorageContext(
            workspace_id="ws1",
            source_platform=SourcePlatformEnum.DOUYIN,
            source_profile_external_id="MS4wLjABAAAA965SRwbGiCEbLONG",
            source_video_external_id="222",
            profile_handle="chef",
            profile_display_name="Chef",
        )
        prefix_a = video_storage_prefix(ctx_a)
        prefix_b = video_storage_prefix(ctx_b)
        self.assertEqual(prefix_a, prefix_b)
        self.assertTrue(prefix_a.startswith("workspace_ws1/dy/@"))
        self.assertNotIn("video_111", prefix_a)
        self.assertNotIn("niche_", prefix_a)


class OperatorFilenameTests(unittest.TestCase):
    def test_filename_date_aweme_caption_height_tag(self) -> None:
        name = build_source_video_raw_filename(
            aweme_id="7423381219443887414",
            caption="靠吃瘦了51.8斤 减肥食谱",
            watermark_free=True,
            posted_at=datetime(2026, 7, 14, tzinfo=UTC),
            height=1080,
        )
        self.assertTrue(name.startswith("2026-07-14__7423381219443887414__"))
        self.assertIn("靠吃瘦了", name)
        self.assertTrue(name.endswith("__1080p__nl.mp4"))
        self.assertNotIn("Agu", name)

    def test_filename_wm_and_unknown_height(self) -> None:
        name = build_source_video_raw_filename(
            aweme_id="123",
            caption=None,
            watermark_free=False,
            posted_at=None,
            height=None,
            fallback_date=datetime(2026, 1, 2, tzinfo=UTC),
        )
        self.assertEqual(name, "2026-01-02__123__nocap__unkp__wm.mp4")


class OperatorAssetKeyTests(unittest.TestCase):
    def test_raw_key_is_flat_under_profile(self) -> None:
        ctx = VideoStorageContext(
            workspace_id="ws",
            source_platform=SourcePlatformEnum.DOUYIN,
            source_profile_external_id="MS4wLjABAAAAsecuidvalue",
            source_video_external_id="7423381219443887414",
            profile_handle="Agu_z",
        )
        name = build_source_video_raw_filename(
            aweme_id="7423381219443887414",
            caption="午餐",
            watermark_free=True,
            posted_at=datetime(2026, 7, 14, tzinfo=UTC),
            height=1080,
        )
        key = asset_logical_key(ctx, MediaAssetType.SOURCE_VIDEO_RAW, filename=name)
        self.assertTrue(key.startswith("workspace_ws/dy/@Agu_z__"))
        self.assertIn("/2026-07-14__7423381219443887414__", key)
        self.assertNotIn("/raw/", key)
        self.assertNotIn("/video_", key)
        self.assertNotIn("/v1_", key)

    def test_sidecar_assets_share_profile_and_aweme_prefix(self) -> None:
        ctx = VideoStorageContext(
            workspace_id="ws",
            source_platform=SourcePlatformEnum.DOUYIN,
            source_profile_external_id="MS4wLjABAAAAsecuidvalue",
            source_video_external_id="7423381219443887414",
            profile_handle="Agu_z",
        )
        key = asset_logical_key(ctx, MediaAssetType.THUMBNAIL, filename="thumbnail.jpg")
        self.assertIn("/previews/7423381219443887414__", key)
        self.assertTrue(key.endswith("thumbnail.jpg"))


if __name__ == "__main__":
    unittest.main()
