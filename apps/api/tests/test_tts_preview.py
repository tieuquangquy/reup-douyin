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

    def test_preview_preserves_google_oauth_credential_fields(self) -> None:
        class _GoogleFakeProvider:
            provider_name = "google"

            def synthesize(self, request):  # noqa: ANN001
                return TtsProviderOutput(
                    audio_bytes=b"google-audio",
                    duration_seconds=0.5,
                    mime_type="audio/mpeg",
                    file_extension="mp3",
                    provider_metadata={"provider": "google"},
                    warnings=[],
                )

        cfg = SimpleNamespace(
            enabled=False,
            provider="google",
            voice_id="vi-VN-Standard-A",
            speaking_rate=1.0,
            language_code="vi-VN",
            model_id="",
            api_key=None,
            credential_mode="google_service_account",
            google_service_account_json="service-account-json",
            google_service_account_email="tts@example.iam.gserviceaccount.com",
            google_service_account_project_id="tts-project",
            base_url="https://texttospeech.googleapis.com/v1",
            timeout_seconds=30.0,
            fallback_provider="none",
            fallback_voice_id="",
            local_backend="auto",
            device="auto",
            cli_binary="",
            options_json={},
        )

        def capture_factory(*, workspace_tts):  # noqa: ANN001
            self.assertEqual(workspace_tts.credential_mode, "google_service_account")
            self.assertEqual(workspace_tts.google_service_account_json, "service-account-json")
            self.assertEqual(workspace_tts.google_service_account_project_id, "tts-project")
            return _GoogleFakeProvider()

        with patch("src.tts_pipeline.preview.build_default_tts_provider", side_effect=capture_factory):
            result = preview_tts_speech(workspace_tts=cfg, text="Xin chÃ o Google")

        self.assertTrue(result["ok"])

    def test_preview_preserves_gemini_expressive_draft_fields(self) -> None:
        class _GeminiFakeProvider:
            provider_name = "google_gemini"

            def synthesize(self, request):  # noqa: ANN001
                self.assert_request(request)
                return TtsProviderOutput(
                    audio_bytes=b"gemini-expressive-audio",
                    duration_seconds=0.75,
                    mime_type="audio/wav",
                    file_extension="wav",
                    provider_metadata={
                        "provider": "google_gemini",
                        "voice_id": "Aoede",
                        "requested_voice_id": "vi-VN-Chirp3-HD-Aoede",
                        "resolved_voice_id": "Aoede",
                        "requested_model_id": "gemini-3.1-flash-preview-tts",
                        "resolved_model_id": "gemini-2.5-flash-tts",
                    },
                    warnings=["google_cloud_tts_model_fallback"],
                )

            @staticmethod
            def assert_request(request):  # noqa: ANN001
                assert request.voice_config.voice_id == "vi-VN-Chirp3-HD-Aoede"

        cfg = SimpleNamespace(
            enabled=False,
            provider="google_gemini",
            voice_id="vi-VN-Chirp3-HD-Aoede",
            speaking_rate=1.05,
            language_code="vi-VN",
            model_id="gemini-2.5-flash-preview-tts",
            api_key="gemini-api-key",
            credential_mode="api_key",
            google_service_account_json=None,
            google_service_account_email="",
            google_service_account_project_id="",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            timeout_seconds=45.0,
            fallback_provider="none",
            fallback_voice_id="",
            local_backend="auto",
            device="auto",
            cli_binary="",
            options_json={
                "expressive_tts": {"mode": "required"},
                "emotion_plan": {"version": "text-conditioned-emotion-planner-v1"},
            },
        )

        def capture_factory(*, workspace_tts):  # noqa: ANN001
            self.assertEqual(workspace_tts.provider, "google_gemini")
            self.assertEqual(workspace_tts.credential_mode, "api_key")
            self.assertEqual(workspace_tts.api_key, "gemini-api-key")
            self.assertEqual(workspace_tts.model_id, "gemini-2.5-flash-preview-tts")
            self.assertEqual(workspace_tts.voice_id, "vi-VN-Chirp3-HD-Aoede")
            self.assertEqual(workspace_tts.options_json["expressive_tts"]["mode"], "required")
            self.assertEqual(
                workspace_tts.options_json["emotion_plan"]["version"],
                "text-conditioned-emotion-planner-v1",
            )
            return _GeminiFakeProvider()

        with patch("src.tts_pipeline.preview.build_default_tts_provider", side_effect=capture_factory):
            result = preview_tts_speech(workspace_tts=cfg, text="Xin chÃƒÂ o Gemini Expressive")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "google_gemini")
        self.assertEqual(result["requested_voice_id"], "vi-VN-Chirp3-HD-Aoede")
        self.assertEqual(result["resolved_voice_id"], "Aoede")
        self.assertEqual(result["requested_model_id"], "gemini-3.1-flash-preview-tts")
        self.assertEqual(result["resolved_model_id"], "gemini-2.5-flash-tts")
        self.assertIn("model fallback", result["detail"])
        self.assertEqual(base64.b64decode(result["audio_base64"]), b"gemini-expressive-audio")


if __name__ == "__main__":
    unittest.main()
