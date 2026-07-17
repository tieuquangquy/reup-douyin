from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.storage.local import LocalStorageBackend, to_windows_long_path


class WindowsLongPathStorageTests(unittest.TestCase):
    def test_to_windows_long_path_adds_prefix(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows only")
        path = Path(r"C:\Users\PC\Desktop\reup_douyin\apps\worker\data\storage\workspace_x")
        converted = to_windows_long_path(path)
        self.assertTrue(str(converted).startswith("\\\\?\\"))
        self.assertIn("workspace_x", str(converted))

    def test_write_bytes_succeeds_for_path_over_260(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows only")
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            # Force a nested key that makes absolute path exceed 260 chars.
            long_profile = "MS4wLjABAAAA" + ("A" * 140)
            key = (
                f"workspace_00f25893-c1c2-4f13-abdd-79e809ae5fc9/douyin/"
                f"profile_{long_profile}/niche_default/video_7502793329186262326/raw/"
                f"v1_7502793329186262326.mp4"
            )
            absolute = (root.resolve() / key.replace("/", "\\"))
            self.assertGreater(len(str(absolute)), 260)

            backend = LocalStorageBackend(root)
            result = backend.write_bytes(key, b"video-bytes")
            self.assertEqual(result.size_bytes, len(b"video-bytes"))
            self.assertTrue(backend.exists(key))
            written = to_windows_long_path(backend.resolve(key).absolute_path).read_bytes()
            self.assertEqual(written, b"video-bytes")
            meta = backend.metadata(key)
            self.assertTrue(meta.exists)
            self.assertEqual(meta.size_bytes, len(b"video-bytes"))
            # Best-effort cleanup of long paths before TemporaryDirectory exits.
            try:
                backend.delete(key)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
