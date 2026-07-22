from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import MediaAssetType
from src.services.local_asset_reveal import (
    LocalAssetRevealError,
    reveal_local_file_in_file_manager,
    resolve_current_local_asset_path,
)


class LocalAssetRevealTests(unittest.TestCase):
    def test_reveal_windows_uses_explorer_select_without_returning_path(self) -> None:
        with TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "source.mp4"
            file_path.write_bytes(b"video")
            runner = MagicMock()
            with patch("src.services.local_asset_reveal.os.name", "nt"):
                result = reveal_local_file_in_file_manager(file_path, runner=runner)
            self.assertEqual(result, {"revealed": True})
            self.assertNotIn("path", result)
            self.assertNotIn(str(file_path), str(result))
            runner.assert_called_once()
            args = runner.call_args.args[0]
            self.assertEqual(args[0], "explorer")
            self.assertTrue(args[1].startswith("/select,"))
            self.assertTrue(args[1].endswith(str(file_path.resolve())))

    def test_reveal_missing_file_fails_closed(self) -> None:
        missing = Path("C:/definitely-missing-reup-douyin-asset.mp4")
        with self.assertRaises(LocalAssetRevealError) as ctx:
            reveal_local_file_in_file_manager(missing, runner=MagicMock())
        self.assertEqual(ctx.exception.code, "FILE_NOT_FOUND")
        self.assertNotIn("definitely-missing", ctx.exception.message)

    def test_resolve_requires_local_current_raw_asset(self) -> None:
        asset = MagicMock()
        asset.id = uuid4()
        asset.asset_type = MediaAssetType.SOURCE_VIDEO_RAW
        asset.storage_provider = "local"
        asset.storage_key = "workspace/raw/source.mp4"
        asset.is_current = True

        db = MagicMock()
        db.scalar.return_value = asset

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "workspace" / "raw" / "source.mp4"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"ok")
            storage = MagicMock()
            storage.resolve.return_value = MagicMock(absolute_path=target)
            resolved = resolve_current_local_asset_path(
                db,
                source_video_id=uuid4(),
                asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
                storage=storage,
            )
            self.assertEqual(resolved, target.resolve())

        remote = MagicMock()
        remote.storage_provider = "s3"
        remote.is_current = True
        remote.asset_type = MediaAssetType.SOURCE_VIDEO_RAW
        db.scalar.return_value = remote
        with self.assertRaises(LocalAssetRevealError) as ctx:
            resolve_current_local_asset_path(
                db,
                source_video_id=uuid4(),
                asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
                storage=MagicMock(),
            )
        self.assertEqual(ctx.exception.code, "NOT_LOCAL")


if __name__ == "__main__":
    unittest.main()
