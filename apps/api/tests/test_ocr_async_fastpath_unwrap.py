"""Regression: async REST fast-path must unwrap (frame, warns) tuples into by_index."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media_pipeline.ocr_filtering.pipeline import run_ocr_filtering
from src.media_pipeline.ocr_filtering.providers import RestOcrEndpointProvider, RetryingOcrProvider
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrFilterResult


class AsyncRestFastPathUnwrapTests(unittest.TestCase):
    def test_fast_path_to_dict_does_not_treat_batch_tuples_as_frames(self) -> None:
        """Bug: by_index.update(batch) stored tuples → frame.frame_id AttributeError."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f0.jpg"
            from PIL import Image

            Image.new("RGB", (100, 200), color=(1, 2, 3)).save(path, format="JPEG")

            frame = FrameOcrFilterResult(
                frame_id="f0",
                path=str(path),
                time_ms=0,
                frame_width=100,
                frame_height=200,
                boxes=[
                    DetectedTextBox(x=0.1, y=0.8, width=0.8, height=0.1, text="字幕", confidence=0.9),
                ],
                raw_box_count=1,
                filtered_out_count=0,
            )
            batch = {0: (frame, [])}
            rest = RestOcrEndpointProvider(
                endpoint_url="https://example.test/predict",
                skip_warmup=True,
            )
            provider = RetryingOcrProvider(rest, max_attempts=1, base_delay_seconds=0.0)

            with patch(
                "src.media_pipeline.ocr_filtering.pipeline._run_async_rest_batch",
                return_value=batch,
            ):
                result = run_ocr_filtering(
                    [path],
                    ocr_provider=provider,
                    crop_band=False,
                    probe_stride=1,
                )

            self.assertIsInstance(result.frames[0], FrameOcrFilterResult)
            payload = result.to_dict()
            self.assertEqual(payload["frames"][0]["frame_id"], "f0")
            self.assertEqual(payload["frames"][0]["boxes"][0]["text"], "字幕")


if __name__ == "__main__":
    unittest.main()
