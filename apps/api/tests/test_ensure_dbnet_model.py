"""ensure_dbnet_onnx downloads when missing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.media_pipeline.frame_sampling.ensure_dbnet_model import ensure_dbnet_onnx


class EnsureDbnetModelTests(unittest.TestCase):
    def test_skips_download_when_file_large_enough(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dbnet.onnx"
            dest.write_bytes(b"x" * 150_000)
            with patch(
                "src.media_pipeline.frame_sampling.ensure_dbnet_model.urllib.request.urlretrieve"
            ) as retrieve:
                got = ensure_dbnet_onnx(dest)
            self.assertEqual(got, dest)
            retrieve.assert_not_called()

    def test_downloads_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dbnet.onnx"

            def fake_retrieve(_url: str, path: str) -> None:
                Path(path).write_bytes(b"y" * 120_000)

            with patch(
                "src.media_pipeline.frame_sampling.ensure_dbnet_model.urllib.request.urlretrieve",
                side_effect=fake_retrieve,
            ):
                got = ensure_dbnet_onnx(dest)
            self.assertEqual(got, dest)
            self.assertGreaterEqual(dest.stat().st_size, 100_000)


if __name__ == "__main__":
    unittest.main()
