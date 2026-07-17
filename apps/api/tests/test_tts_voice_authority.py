"""Workspace TTS settings are authority for Generate TTS voice when enabled."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.tts_pipeline.services.tts_service import TtsPipelineService
from src.tts_pipeline.types import TtsRequest, VoiceConfig


class TtsVoiceAuthorityTests(unittest.TestCase):
    def test_workspace_enabled_overrides_client_edge_default(self) -> None:
        service = TtsPipelineService(db=MagicMock())
        workspace_tts = SimpleNamespace(
            enabled=True,
            voice_id="Ngọc Linh",
            speaking_rate=1.15,
            language_code="vi",
        )
        request = TtsRequest(
            source_video_id=uuid4(),
            voice_config=VoiceConfig(
                voice_id="vi-VN-HoaiMyNeural",
                language_code="vi",
                speaking_rate=1.0,
            ),
        )
        with patch(
            "src.tts_pipeline.services.tts_service.WorkspaceSettingsService"
        ) as service_cls:
            service_cls.return_value.get_tts_ai.return_value = workspace_tts
            with patch("src.tts_pipeline.services.tts_service.get_settings") as get_settings:
                get_settings.return_value = SimpleNamespace(
                    audio_tts_voice_id="vi-VN-HoaiMyNeural",
                    audio_tts_speaking_rate=1.0,
                )
                resolved = service._voice_config_for_request(request, uuid4())
        self.assertEqual(resolved.voice_id, "Ngọc Linh")
        self.assertEqual(resolved.speaking_rate, 1.15)
        self.assertEqual(resolved.language_code, "vi")

    def test_workspace_disabled_keeps_client_voice(self) -> None:
        service = TtsPipelineService(db=MagicMock())
        workspace_tts = SimpleNamespace(
            enabled=False,
            voice_id="Ngọc Linh",
            speaking_rate=1.15,
            language_code="vi",
        )
        request = TtsRequest(
            source_video_id=uuid4(),
            voice_config=VoiceConfig(
                voice_id="vi-VN-NamMinhNeural",
                language_code="vi",
                speaking_rate=0.9,
            ),
        )
        with patch(
            "src.tts_pipeline.services.tts_service.WorkspaceSettingsService"
        ) as service_cls:
            service_cls.return_value.get_tts_ai.return_value = workspace_tts
            with patch("src.tts_pipeline.services.tts_service.get_settings") as get_settings:
                get_settings.return_value = SimpleNamespace(
                    audio_tts_voice_id="vi-VN-HoaiMyNeural",
                    audio_tts_speaking_rate=1.0,
                )
                resolved = service._voice_config_for_request(request, uuid4())
        self.assertEqual(resolved.voice_id, "vi-VN-NamMinhNeural")
        self.assertEqual(resolved.speaking_rate, 0.9)

    def test_workspace_enabled_empty_voice_falls_back_to_env(self) -> None:
        service = TtsPipelineService(db=MagicMock())
        workspace_tts = SimpleNamespace(
            enabled=True,
            voice_id="",
            speaking_rate=1.0,
            language_code="vi",
        )
        request = TtsRequest(
            source_video_id=uuid4(),
            voice_config=VoiceConfig(voice_id="vi-VN-HoaiMyNeural"),
        )
        with patch(
            "src.tts_pipeline.services.tts_service.WorkspaceSettingsService"
        ) as service_cls:
            service_cls.return_value.get_tts_ai.return_value = workspace_tts
            with patch("src.tts_pipeline.services.tts_service.get_settings") as get_settings:
                get_settings.return_value = SimpleNamespace(
                    audio_tts_voice_id="vi-VN-NamMinhNeural",
                    audio_tts_speaking_rate=1.0,
                )
                resolved = service._voice_config_for_request(request, uuid4())
        self.assertEqual(resolved.voice_id, "vi-VN-NamMinhNeural")


if __name__ == "__main__":
    unittest.main()
