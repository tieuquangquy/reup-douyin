"""OCR provider: fail-closed on Paddle runtime crash (no silent mock for real video)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.ocr_pipeline.errors import OcrPipelineError, OcrPipelineErrorCode
from src.ocr_pipeline.providers import (
    FallbackOcrProvider,
    MockOcrProvider,
    is_paddle_runtime_failure,
)
from src.ocr_pipeline.types import FrameOcrResult, OcrBox


class OcrProviderFallbackTests(unittest.TestCase):
    def test_is_paddle_runtime_failure_detects_onednn(self) -> None:
        exc = OcrPipelineError(
            OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
            "PaddleOCR failed: (Unimplemented) ConvertPirAttribute2RuntimeAttribute not support "
            "[pir::ArrayAttribute<pir::DoubleAttribute>] (at ..\\onednn_instruction.cc:118)",
        )
        self.assertTrue(is_paddle_runtime_failure(exc))

    def test_fail_closed_raises_on_paddle_crash_by_default(self) -> None:
        primary = MagicMock()
        primary.provider_name = "paddleocr"
        primary.detect_frame.side_effect = OcrPipelineError(
            OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
            "PaddleOCR failed: ConvertPirAttribute2RuntimeAttribute not support onednn_instruction",
        )
        provider = FallbackOcrProvider(primary=primary, fallback=MockOcrProvider())

        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "frame.jpg"
            image.write_bytes(b"fake")
            with self.assertRaises(OcrPipelineError) as ctx:
                provider.detect_frame(image, frame_time_ms=1000)

        self.assertEqual(ctx.exception.code, OcrPipelineErrorCode.OCR_PROVIDER_FAILED)
        self.assertIn("fail_closed", ctx.exception.message.lower().replace("-", "_"))
        self.assertEqual(provider.warnings, [])
        self.assertEqual(provider.provider_name, "paddleocr")

    def test_explicit_allow_mock_fallback_still_switches(self) -> None:
        primary = MagicMock()
        primary.provider_name = "paddleocr"
        primary.detect_frame.side_effect = OcrPipelineError(
            OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
            "PaddleOCR failed: ConvertPirAttribute2RuntimeAttribute not support onednn_instruction",
        )
        provider = FallbackOcrProvider(
            primary=primary,
            fallback=MockOcrProvider(text="fallback"),
            allow_mock_fallback=True,
        )

        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "frame.jpg"
            image.write_bytes(b"fake")
            result = provider.detect_frame(image, frame_time_ms=1000)

        self.assertEqual(result.boxes[0].text, "fallback")
        self.assertIn("paddleocr_runtime_fallback_mock", provider.warnings)
        self.assertEqual(provider.provider_name, "mock_ocr")

    def test_fallback_provider_keeps_paddle_when_healthy(self) -> None:
        primary = MagicMock()
        primary.provider_name = "paddleocr"
        primary.detect_frame.return_value = FrameOcrResult(
            frame_time_ms=0,
            frame_width=100,
            frame_height=100,
            boxes=[OcrBox(x=0.1, y=0.8, width=0.8, height=0.1, text="ok", confidence=0.9)],
        )
        provider = FallbackOcrProvider(primary=primary, fallback=MockOcrProvider())
        result = provider.detect_frame(Path("x.jpg"), frame_time_ms=0)
        self.assertEqual(result.boxes[0].text, "ok")
        self.assertEqual(provider.warnings, [])


if __name__ == "__main__":
    unittest.main()
