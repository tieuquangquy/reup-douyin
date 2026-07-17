from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import tempfile
import unittest

from src.downloaders.base import DownloadedObject
from src.downloaders.mock import MappingAssetDownloader
from src.downloaders.errors import DownloadError
from src.enums import MediaAssetStatus, MediaAssetType, SourcePlatformEnum
from src.storage.asset_health import validate_asset_health
from src.storage.local import LocalStorageBackend
from src.storage.manifest import assemble_asset_manifest
from src.storage.path_strategy import VideoStorageContext, asset_logical_key, video_storage_prefix


class StorageManifestTests(unittest.TestCase):
    def test_path_strategy_layout(self) -> None:
        context = VideoStorageContext(
            workspace_id="workspace-id",
            source_platform=SourcePlatformEnum.DOUYIN,
            source_profile_external_id="profile/unsafe",
            source_video_external_id="video:123",
            niche_slug="food clips",
            profile_handle="chef",
        )
        prefix = video_storage_prefix(context)
        self.assertIn("workspace_workspace-id", prefix)
        self.assertIn("/dy/", prefix)
        self.assertIn("@chef__", prefix)
        self.assertIn("niche_food_clips", prefix)
        key = asset_logical_key(context, MediaAssetType.SOURCE_VIDEO_RAW, filename="source video.mp4")
        self.assertTrue(key.endswith("/source_video.mp4"))
        self.assertNotIn("/raw/", key)
        thumb = asset_logical_key(context, MediaAssetType.THUMBNAIL, filename="thumbnail.jpg")
        self.assertIn("/previews/video_123__", thumb)

    def test_local_storage_write_metadata_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageBackend(tmp)
            result = storage.write_bytes("workspace_a/video_b/raw/v1.mp4", b"video-bytes")
            self.assertTrue(storage.exists(result.storage_key))
            metadata = storage.metadata(result.storage_key)
            self.assertTrue(metadata.exists)
            self.assertEqual(metadata.size_bytes, len(b"video-bytes"))
            self.assertEqual(metadata.checksum_sha256, result.checksum_sha256)
            self.assertTrue(Path(result.absolute_path).exists())

    def test_asset_health_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageBackend(tmp)
            result = storage.write_bytes("workspace_a/video_b/raw/v1.mp4", b"video-bytes")
            healthy = validate_asset_health(
                storage,
                result.storage_key,
                expected_checksum_sha256=result.checksum_sha256,
            )
            self.assertTrue(healthy.is_valid)
            self.assertEqual(healthy.errors, [])

            missing = validate_asset_health(storage, "missing/file.mp4")
            self.assertFalse(missing.is_valid)
            self.assertEqual(missing.errors, ["missing_file"])

    def test_manifest_assembly(self) -> None:
        source_video_id = uuid4()
        source_profile_id = uuid4()
        asset_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            source_video_external_id="742",
            source_url="https://example.test/video.mp4",
            caption="caption",
            posted_at=None,
            duration_seconds=22.0,
        )
        source_profile = SimpleNamespace(
            id=source_profile_id,
            source_profile_external_id="profile-1",
            display_name="Creator",
        )
        asset = SimpleNamespace(
            id=asset_id,
            asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
            status=MediaAssetStatus.AVAILABLE,
            version=1,
            is_current=True,
            logical_key="workspace/video/raw/v1.mp4",
            storage_key="workspace/video/raw/v1.mp4",
            relative_path="workspace/video/raw/v1.mp4",
            mime_type="video/mp4",
            size_bytes=10,
            checksum_sha256="abc",
            source_url="https://example.test/video.mp4",
            created_at=None,
            updated_at=None,
        )
        manifest = assemble_asset_manifest(
            source_video=source_video,
            source_profile=source_profile,
            assets=[asset],
            storage_root="C:/storage",
        )
        self.assertEqual(manifest["manifest_version"], "ASSET_MANIFEST_V1")
        self.assertEqual(manifest["source_video"]["external_id"], "742")
        self.assertEqual(manifest["assets"][0]["asset_type"], MediaAssetType.SOURCE_VIDEO_RAW)

    def test_mock_downloader(self) -> None:
        downloader = MappingAssetDownloader(
            {"https://example.test/video.mp4": DownloadedObject(b"video", "video/mp4", "video.mp4")}
        )
        result = downloader.fetch("https://example.test/video.mp4")
        self.assertEqual(result.content, b"video")
        self.assertEqual(result.mime_type, "video/mp4")
        with self.assertRaises(DownloadError):
            downloader.fetch("https://example.test/missing.mp4")


if __name__ == "__main__":
    unittest.main()
