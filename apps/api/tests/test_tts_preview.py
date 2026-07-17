"""Ops TTS short speech preview (no durable job)."""

from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.tts_pipeline.preview import PreviewTtsError, preview_tts_speech
from src.tts_pipeline.types import TtsProviderOutput


class _FakeProvider:
    provider_name = "edge"

    def synthesize(self, request):  # noqa: ANN001
        assert "Xin chào" in request.text
        return TtsProviderOutput(
            audio_bytes=b"RIFF....wav",
            duration_seconds=1.25,
            mime_type="audio/wav",
            file_extension="wav",
            provider_metadata={"provider": "edge"},
            warnings=[],
        )


class TtsPreviewTests(unittest.TestCase):
    def test_preview_returns_base64_audio(self) -> None:
        cfg = SimpleNamespace(
            enabled=True,
            provider="edge",
            voice_id="vi-VN-HoaiMyNeural",
            speaking_rate=1.0,
            language_code="vi",
            model_id="",
            api_key=None,
            base_url="",
            timeout_seconds=60.0,
            fallback_provider="none",
            fallback_voice_id="",
            local_backend="auto",
            device="auto",
            cli_binary="",
            options_json={},
        )
        with patch(
            "src.tts_pipeline.preview.build_default_tts_provider",
            return_value=_FakeProvider(),
        ):
            result = preview_tts_speech(workspace_tts=cfg, text="Xin chào Việt Nam")
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "edge")
        self.assertEqual(result["mime_type"], "audio/wav")
        self.assertEqual(result["duration_seconds"], 1.25)
        self.assertEqual(base64.b64decode(result["audio_base64"]), b"RIFF....wav")

    def test_preview_rejects_empty_text(self) -> None:
        with self.assertRaises(PreviewTtsError):
            preview_tts_speech(workspace_tts=SimpleNamespace(enabled=True), text="   ")

    def test_preview_truncates_long_text(self) -> None:
        seen: dict[str, str] = {}

        class _Capture:
            provider_name = "placeholder"

            def synthesize(self, request):  # noqa: ANN001
                seen["text"] = request.text
                return TtsProviderOutput(
                    audio_bytes=b"RIFF",
                    duration_seconds=0.1,
                    mime_type="audio/wav",
                    file_extension="wav",
                    provider_metadata={},
                    warnings=[],
                )

        cfg = SimpleNamespace(
            enabled=True,
            provider="placeholder",
            voice_id="",
            speaking_rate=1.0,
            language_code="vi",
            model_id="",
            api_key=None,
            base_url="",
            timeout_seconds=30.0,
            fallback_provider="none",
            fallback_voice_id="",
            local_backend="auto",
            device="auto",
            cli_binary="",
            options_json={},
        )
        long_text = "a" * 500
        with patch(
            "src.tts_pipeline.preview.build_default_tts_provider",
            return_value=_Capture(),
        ):
            preview_tts_speech(workspace_tts=cfg, text=long_text, max_chars=40)
        self.assertEqual(len(seen["text"]), 40)


if __name__ == "__main__":
    unittest.main()
