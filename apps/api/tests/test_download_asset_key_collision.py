"""Re-download must never insert a second row for an existing storage key.

`uq_media_assets_workspace_storage_key` makes a duplicate insert abort the whole
transaction, which previously left DOWNLOAD_VIDEO jobs stuck as RUNNING at ~71%.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.downloaders.errors import DownloadError
from src.enums import MediaAssetStatus, MediaAssetType
from src.services.download_service import DownloadService
from src.storage.path_strategy import VideoStorageContext, asset_logical_key


def _write_result(storage_key: str) -> SimpleNamespace:
    return SimpleNamespace(
        storage_key=storage_key,
        logical_key=storage_key,
        relative_path=storage_key,
        absolute_path=f"C:/storage/{storage_key}",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        storage_provider="local",
    )


class AssetKeyCollisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_id = uuid4()
        self.source_video = SimpleNamespace(id=uuid4(), workspace_id=self.workspace_id)
        self.context = VideoStorageContext(
            workspace_id=str(self.workspace_id),
            source_platform="DOUYIN",
            source_profile_external_id="MS4wLjABAAAA",
            source_video_external_id="7645290232053928811",
            profile_handle="agu_z",
            profile_display_name="Agu",
        )
        self.storage = MagicMock()
        self.db = MagicMock()
        self.service = DownloadService(
            self.db,
            storage=self.storage,
            downloader=MagicMock(),
            primary_fetcher=MagicMock(),
        )

    def _existing_raw_asset(self, storage_key: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=uuid4(),
            workspace_id=self.workspace_id,
            source_video_id=self.source_video.id,
            asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
            status=MediaAssetStatus.AVAILABLE,
            version=1,
            is_current=True,
            storage_key=storage_key,
            logical_key=storage_key,
            relative_path=storage_key,
            size_bytes=10,
            checksum_sha256="b" * 64,
            created_by_job_id=None,
            source_url=None,
            mime_type=None,
            metadata_json={},
            manifest_group="source_download",
            storage_provider="local",
            error_message="boom",
        )

    def test_force_refresh_reuses_row_when_storage_key_unchanged(self) -> None:
        leaf = "2026-05-29__7645290232053928811__clip.mp4"
        storage_key = asset_logical_key(self.context, MediaAssetType.SOURCE_VIDEO_RAW, filename=leaf)
        existing = self._existing_raw_asset(storage_key)
        self.db.scalar.return_value = existing
        self.storage.write_bytes.return_value = _write_result(storage_key)
        job_id = uuid4()

        asset = self.service._persist_bytes_asset(
            self.source_video,
            self.context,
            MediaAssetType.SOURCE_VIDEO_RAW,
            b"video-bytes",
            filename=leaf,
            mime_type="video/mp4",
            source_url="https://example.test/v.mp4",
            job_id=job_id,
            force_refresh=True,
        )

        self.assertIs(asset, existing, "Re-download must update the existing row, not insert a duplicate")
        self.assertFalse(self.db.add.called, "Inserting a second row would violate the storage-key unique index")
        self.assertTrue(existing.is_current)
        self.assertEqual(existing.status, MediaAssetStatus.AVAILABLE)
        self.assertEqual(existing.size_bytes, 1024)
        self.assertEqual(existing.created_by_job_id, job_id)
        self.assertIsNone(existing.error_message)

    def test_force_refresh_inserts_new_version_when_storage_key_changes(self) -> None:
        old_key = asset_logical_key(
            self.context, MediaAssetType.SOURCE_VIDEO_RAW, filename="old__clip.mp4"
        )
        new_key = asset_logical_key(
            self.context, MediaAssetType.SOURCE_VIDEO_RAW, filename="new__clip.mp4"
        )
        existing = self._existing_raw_asset(old_key)
        # _current_asset -> existing ; lookup by new storage key -> nothing to reuse.
        self.db.scalar.side_effect = [existing, None]
        self.storage.write_bytes.return_value = _write_result(new_key)

        asset = self.service._persist_bytes_asset(
            self.source_video,
            self.context,
            MediaAssetType.SOURCE_VIDEO_RAW,
            b"video-bytes",
            filename="new__clip.mp4",
            mime_type="video/mp4",
            source_url=None,
            job_id=uuid4(),
            force_refresh=True,
        )

        self.assertTrue(self.db.add.called)
        self.assertEqual(asset.version, 2)
        self.assertFalse(existing.is_current)

    def test_repeated_failure_reuses_placeholder_row(self) -> None:
        placeholder_key = asset_logical_key(
            self.context, MediaAssetType.THUMBNAIL, filename="failed.placeholder"
        )
        existing = self._existing_raw_asset(placeholder_key)
        existing.asset_type = MediaAssetType.THUMBNAIL
        self.db.scalar.return_value = existing

        asset = self.service._register_failed_asset(
            self.source_video,
            self.context,
            MediaAssetType.THUMBNAIL,
            "https://example.test/t.jpg",
            DownloadError("download_failed", "nope"),
            uuid4(),
        )

        self.assertIs(asset, existing, "A second failure must not duplicate the placeholder storage key")
        self.assertFalse(self.db.add.called)
        self.assertEqual(existing.status, MediaAssetStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
