"""Cold-start OCR: long retry on 503 + Cloud Run must not preload on startup."""

from __future__ import annotations

import importlib.util
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from src.media_pipeline.ocr_filtering.errors import OcrFilteringError, OcrFilteringErrorCode
from src.media_pipeline.ocr_filtering.providers import (
    RetryingOcrProvider,
    build_default_ocr_provider,
    is_transient_ocr_http_error,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox


def _load_cloud_run_app():
    path = (
        Path(__file__).resolve().parents[3]
        / "deploy"
        / "hf-paddle-ocr"
        / "app.py"
    )
    spec = importlib.util.spec_from_file_location("hf_paddle_ocr_app_cold", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TransientOcrRetryTests(unittest.TestCase):
    def test_is_transient_detects_503_and_timeout(self) -> None:
        self.assertTrue(
            is_transient_ocr_http_error(
                "OCR HTTP request failed: 503 Server Error: Service Unavailable"
            )
        )
        self.assertTrue(is_transient_ocr_http_error("Read timed out. (read timeout=300.0)"))
        self.assertFalse(is_transient_ocr_http_error("OCR /predict response must be a JSON array"))

    def test_wait_for_ocr_endpoint_ready_polls_until_200(self) -> None:
        from src.media_pipeline.ocr_filtering.providers import wait_for_ocr_endpoint_ready

        responses = [
            MagicMock(status_code=503),
            MagicMock(status_code=503),
            MagicMock(status_code=200),
        ]
        predict_ok = MagicMock(status_code=200)
        predict_ok.text = "[]"
        with (
            patch("src.media_pipeline.ocr_filtering.providers.requests.get", side_effect=responses) as get,
            patch(
                "src.media_pipeline.ocr_filtering.providers.requests.post",
                return_value=predict_ok,
            ) as post,
            patch("src.media_pipeline.ocr_filtering.providers.time.sleep"),
        ):
            wait_for_ocr_endpoint_ready("https://svc.a.run.app/predict", deadline_seconds=60)
        self.assertEqual(get.call_count, 3)
        self.assertTrue(str(get.call_args_list[0].args[0]).endswith("/health"))
        self.assertEqual(post.call_count, 1)

    def test_wait_for_ocr_endpoint_ready_retries_predict_503(self) -> None:
        from src.media_pipeline.ocr_filtering.providers import wait_for_ocr_endpoint_ready

        health_ok = MagicMock(status_code=200)
        predict_fail = MagicMock(status_code=503, text="unavailable")
        predict_ok = MagicMock(status_code=200, text="[]")
        with (
            patch("src.media_pipeline.ocr_filtering.providers.requests.get", return_value=health_ok),
            patch(
                "src.media_pipeline.ocr_filtering.providers.requests.post",
                side_effect=[predict_fail, predict_ok],
            ) as post,
            patch("src.media_pipeline.ocr_filtering.providers.time.sleep"),
        ):
            wait_for_ocr_endpoint_ready("https://svc.a.run.app/predict", deadline_seconds=60)
        self.assertEqual(post.call_count, 2)

    def test_wait_for_ocr_endpoint_ready_fails_after_deadline(self) -> None:
        from src.media_pipeline.ocr_filtering.providers import wait_for_ocr_endpoint_ready

        with (
            patch(
                "src.media_pipeline.ocr_filtering.providers.requests.get",
                return_value=MagicMock(status_code=503),
            ),
            patch("src.media_pipeline.ocr_filtering.providers.time.sleep"),
            patch(
                "src.media_pipeline.ocr_filtering.providers.time.monotonic",
                side_effect=[0.0, 0.0, 5.0, 5.0, 61.0],
            ),
        ):
            with self.assertRaises(OcrFilteringError) as ctx:
                wait_for_ocr_endpoint_ready(
                    "https://svc.a.run.app/predict",
                    deadline_seconds=60,
                    warm_predict=False,
                )
        self.assertIn("not ready", ctx.exception.message.lower())

    def test_retrying_uses_long_backoff_for_503(self) -> None:
        primary = MagicMock()
        primary.provider_name = "rest_ocr"
        ok = MagicMock(
            frame_width=100,
            frame_height=100,
            boxes=[DetectedTextBox(0.1, 0.8, 0.5, 0.1, "ok", 0.9)],
        )
        primary.detect_image.side_effect = [
            OcrFilteringError(
                OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                "OCR HTTP request failed: 503 Server Error: Service Unavailable for url: https://x/predict",
            ),
            ok,
        ]
        sleeps: list[float] = []
        provider = RetryingOcrProvider(
            primary,
            max_attempts=6,
            base_delay_seconds=5.0,
            max_delay_seconds=45.0,
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("src.media_pipeline.ocr_filtering.providers.time.sleep", side_effect=sleeps.append),
        ):
            path = Path(tmp) / "frame.jpg"
            path.write_bytes(b"x")
            result = provider.detect_image(path)
        self.assertEqual(result.boxes[0].text, "ok")
        self.assertEqual(primary.detect_image.call_count, 2)
        self.assertGreaterEqual(sleeps[0], 5.0)

    def test_build_default_rest_uses_cold_start_retry_policy(self) -> None:
        with patch.dict("os.environ", {"OCR_ENDPOINT_URL": "https://svc.a.run.app/predict"}, clear=False):
            with patch("src.media_pipeline.ocr_filtering.providers.RestOcrEndpointProvider") as cls:
                cls.return_value = MagicMock(provider_name="rest_ocr")
                provider = build_default_ocr_provider(prefer_mock=False)
        self.assertIsInstance(provider, RetryingOcrProvider)
        # Outer wrapper is light; gateway 502/503/504 retries live in RestOcrEndpointProvider.
        self.assertGreaterEqual(provider._max_attempts, 2)

    def test_rest_provider_retries_503_with_fixed_15s_wait(self) -> None:
        from src.media_pipeline.ocr_filtering.providers import RestOcrEndpointProvider

        fail = MagicMock()
        fail.status_code = 503
        fail.raise_for_status.side_effect = requests.HTTPError(
            "503",
            response=MagicMock(status_code=503),
        )
        ok = MagicMock()
        ok.status_code = 200
        ok.json.return_value = []
        ok.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.jpg"
            path.write_bytes(b"fake-jpg")
            sleeps: list[float] = []
            with (
                patch(
                    "src.media_pipeline.ocr_filtering.providers.requests.post",
                    side_effect=[fail, ok],
                ) as post,
                patch(
                    "src.media_pipeline.ocr_filtering.providers.time.sleep",
                    side_effect=lambda s: sleeps.append(float(s)),
                ),
                patch(
                    "src.media_pipeline.ocr_filtering.providers._image_size",
                    return_value=(100, 100),
                ),
                patch(
                    "src.media_pipeline.ocr_filtering.providers.logger.warning"
                ) as warn,
            ):
                provider = RestOcrEndpointProvider(
                    "https://example.run.app/predict",
                    skip_warmup=True,
                )
                result = provider.detect_image(path)
            self.assertEqual(post.call_count, 2)
            self.assertEqual(result.boxes, [])
            self.assertTrue(any(s >= 15.0 for s in sleeps))
            self.assertTrue(
                any(
                    "Container OCR đang khởi động lạnh" in str(call.args[0])
                    for call in warn.call_args_list
                    if call.args
                )
            )

    def test_rest_provider_warms_endpoint_before_first_detect(self) -> None:
        from src.media_pipeline.ocr_filtering.providers import RestOcrEndpointProvider

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.jpg"
            path.write_bytes(b"fake-jpg")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_response.raise_for_status = MagicMock()
            with (
                patch(
                    "src.media_pipeline.ocr_filtering.providers.wait_for_ocr_endpoint_ready"
                ) as warm,
                patch(
                    "src.media_pipeline.ocr_filtering.providers.requests.post",
                    return_value=mock_response,
                ),
                patch(
                    "src.media_pipeline.ocr_filtering.providers._image_size",
                    return_value=(100, 100),
                ),
            ):
                provider = RestOcrEndpointProvider("https://example.run.app/predict")
                provider.detect_image(path)
                provider.detect_image(path)
            self.assertEqual(warm.call_count, 1)


class CloudRunNoStartupPreloadTests(unittest.TestCase):
    def test_startup_does_not_preload_paddle(self) -> None:
        app = _load_cloud_run_app()
        # Fast ready: lifespan must not call get_ocr_engine / preload.
        if hasattr(app, "lifespan"):
            source = inspect.getsource(app.lifespan)
            self.assertNotIn("get_ocr_engine", source)
            self.assertNotIn("preload_ocr_on_startup", source)
        self.assertFalse(hasattr(app, "preload_ocr_on_startup"))


if __name__ == "__main__":
    unittest.main()
