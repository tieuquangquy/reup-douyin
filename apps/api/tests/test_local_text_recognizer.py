"""Unit tests for the local CTC recognizer boundary."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.frame_sampling.ensure_text_recognizer_model import (
    download_verified_asset,
)
from src.media_pipeline.frame_sampling.local_text_recognizer import (
    ctc_decode,
    ctc_decode_batch,
    preprocess_bgr_for_text_recognition,
)


class LocalTextRecognizerTests(unittest.TestCase):
    def test_ctc_decode_removes_blanks_and_repeated_tokens(self) -> None:
        # blank, 字, 字, blank, 幕
        logits = np.full((1, 5, 3), -8.0, dtype=np.float32)
        for step, token in enumerate((0, 1, 1, 0, 2)):
            logits[0, step, token] = 8.0

        result = ctc_decode(logits, ["字", "幕"])

        self.assertEqual(result.text, "字幕")
        self.assertGreater(result.confidence, 0.99)
        self.assertEqual(result.valid_char_ratio, 1.0)

    def test_ctc_decode_does_not_softmax_model_probabilities_twice(self) -> None:
        probabilities = np.array(
            [[[0.01, 0.98, 0.01], [0.99, 0.005, 0.005], [0.01, 0.01, 0.98]]],
            dtype=np.float32,
        )

        result = ctc_decode(probabilities, ["字", "幕"])

        self.assertEqual(result.text, "字幕")
        self.assertGreater(result.confidence, 0.95)

    def test_ctc_decode_batch_returns_every_sample(self) -> None:
        probabilities = np.array(
            [
                [[0.01, 0.98, 0.01], [0.99, 0.005, 0.005]],
                [[0.01, 0.01, 0.98], [0.99, 0.005, 0.005]],
            ],
            dtype=np.float32,
        )

        results = ctc_decode_batch(probabilities, ["字", "幕"])

        self.assertEqual([result.text for result in results], ["字", "幕"])

    def test_preprocess_preserves_aspect_ratio_and_pads_right(self) -> None:
        crop = np.full((20, 100, 3), 255, dtype=np.uint8)

        tensor = preprocess_bgr_for_text_recognition(crop, image_shape=(3, 48, 320))

        self.assertEqual(tensor.shape, (1, 3, 48, 320))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertTrue(np.allclose(tensor[:, :, :, 240:], 0.0))

    def test_verified_download_replaces_corrupt_cached_asset(self) -> None:
        expected = b"valid-model-bytes"
        expected_sha = hashlib.sha256(expected).hexdigest()
        calls: list[str] = []

        def fake_download(url: str, dest: str) -> None:
            calls.append(url)
            Path(dest).write_bytes(expected)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recognizer.onnx"
            path.write_bytes(b"corrupt")

            result = download_verified_asset(
                url="https://example.invalid/model.onnx",
                dest=path,
                expected_sha256=expected_sha,
                min_bytes=4,
                downloader=fake_download,
            )

            self.assertEqual(result, path)
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(calls, ["https://example.invalid/model.onnx"])


if __name__ == "__main__":
    unittest.main()
