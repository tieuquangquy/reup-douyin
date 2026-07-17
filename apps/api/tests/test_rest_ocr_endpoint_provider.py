"""Rest OCR endpoint provider parses Cloud Run /predict JSON."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import os

from src.media_pipeline.ocr_filtering.providers import (
    RestOcrEndpointProvider,
    build_default_ocr_provider,
    normalize_predict_endpoint,
    parse_predict_response,
)


class ParsePredictResponseTests(unittest.TestCase):
    def test_parse_bbox_text_score_array(self) -> None:
        payload = [
            {"bbox": [[10, 800], [400, 800], [400, 860], [10, 860]], "text": "硬字幕", "score": 0.97},
            {"bbox": [[20, 100], [80, 100], [80, 130], [20, 130]], "text": "TOP", "score": 0.9},
        ]
        boxes = parse_predict_response(payload, width=1000, height=1000)
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0].text, "硬字幕")
        self.assertAlmostEqual(boxes[0].y, 0.8, places=2)
        self.assertAlmostEqual(boxes[0].confidence, 0.97)

    def test_normalize_predict_endpoint_appends_suffix(self) -> None:
        self.assertEqual(
            normalize_predict_endpoint("https://svc.a.run.app"),
            "https://svc.a.run.app/predict",
        )
        self.assertEqual(
            normalize_predict_endpoint("https://svc.a.run.app/predict"),
            "https://svc.a.run.app/predict",
        )


class RestOcrEndpointProviderTests(unittest.TestCase):
    def test_default_http_timeout_allows_cloud_run_cold_start(self) -> None:
        from src.media_pipeline.ocr_filtering import providers as providers_mod

        self.assertGreaterEqual(providers_mod.DEFAULT_TIMEOUT_SECONDS, 300.0)
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("OCR_HTTP_TIMEOUT_SECONDS", None)
            self.assertGreaterEqual(providers_mod.resolve_ocr_http_timeout_seconds(), 300.0)

    def test_ocr_http_timeout_env_override(self) -> None:
        from src.media_pipeline.ocr_filtering.providers import resolve_ocr_http_timeout_seconds

        with patch.dict("os.environ", {"OCR_HTTP_TIMEOUT_SECONDS": "420"}, clear=False):
            self.assertEqual(resolve_ocr_http_timeout_seconds(), 420.0)

    def test_detect_image_posts_multipart_and_maps_boxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.jpg"
            path.write_bytes(b"fake-jpg")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {"bbox": [[0, 700], [100, 700], [100, 750], [0, 750]], "text": "字幕", "score": 0.95},
            ]
            mock_response.raise_for_status = MagicMock()
            with patch(
                "src.media_pipeline.ocr_filtering.providers.requests.post",
                return_value=mock_response,
            ) as post:
                provider = RestOcrEndpointProvider(
                    "https://example.run.app/predict",
                    skip_warmup=True,
                )
                with patch(
                    "src.media_pipeline.ocr_filtering.providers._image_size",
                    return_value=(1000, 1000),
                ):
                    result = provider.detect_image(path)
            called_url = post.call_args.args[0] if post.call_args.args else post.call_args.kwargs.get("url")
            self.assertEqual(called_url, "https://example.run.app/predict")
            self.assertIn("files", post.call_args.kwargs)
            self.assertGreaterEqual(float(post.call_args.kwargs.get("timeout") or 0), 300.0)
            self.assertEqual(result.boxes[0].text, "字幕")
            self.assertAlmostEqual(result.boxes[0].y, 0.7, places=2)
            self.assertEqual(result.frame_width, 1000)

    def test_build_default_uses_ocr_endpoint_url_env(self) -> None:
        with patch.dict("os.environ", {"OCR_ENDPOINT_URL": "https://svc.a.run.app/predict"}, clear=False):
            with patch("src.media_pipeline.ocr_filtering.providers.RestOcrEndpointProvider") as cls:
                instance = MagicMock()
                instance.provider_name = "rest_ocr"
                cls.return_value = instance
                provider = build_default_ocr_provider(prefer_mock=False)
                cls.assert_called_once()
                self.assertEqual(provider.provider_name, "retry(rest_ocr)")


if __name__ == "__main__":
    unittest.main()
