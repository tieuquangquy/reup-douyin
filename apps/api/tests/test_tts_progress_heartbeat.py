"""TTS pipeline reports progress for Generate TTS percent UI."""

from __future__ import annotations

import unittest
import wave
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.tts_pipeline.errors import TtsPipelineError
from src.tts_pipeline.services.tts_service import TtsPipelineService
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput, TtsRequest, VoiceConfig


class _FakeProvider:
    provider_name = "fake"

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        output = BytesIO()
        with wave.open(output, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24_000)
            handle.writeframes(b"\x00\x00" * 4_800)
        return TtsProviderOutput(
            audio_bytes=output.getvalue(),
            duration_seconds=0.2,
            mime_type="audio/wav",
            file_extension="wav",
            provider_metadata={"provider": "fake"},
            warnings=[],
        )


class TtsProgressHeartbeatTests(unittest.TestCase):
    def test_run_pipeline_emits_progress_per_segment(self) -> None:
        service = TtsPipelineService(db=MagicMock(), tts_provider=_FakeProvider())
        source_id = uuid4()
        workspace_id = uuid4()
        segments = [
            SimpleNamespace(
                translation_segment_id=uuid4(),
                segment_index=0,
                translated_text="Một",
                duration_budget_ms=500,
                start_ms=0,
                end_ms=500,
            ),
            SimpleNamespace(
                translation_segment_id=uuid4(),
                segment_index=1,
                translated_text="Hai",
                duration_budget_ms=500,
                start_ms=500,
                end_ms=1000,
            ),
        ]
        progress: list[tuple[str, int | None]] = []

        def on_progress(phase: str, pct: int | None) -> None:
            progress.append((phase, pct))
            if len(progress) >= 2:
                raise RuntimeError("stop_after_progress_samples")

        with (
            patch.object(service, "_load_source_video") as load_sv,
            patch.object(service, "_provider_for_workspace", return_value=_FakeProvider()),
            patch.object(
                service,
                "_voice_config_for_request",
                return_value=VoiceConfig(voice_id="v", language_code="vi", speaking_rate=1.0),
            ),
            patch.object(service, "_storage_context", return_value=SimpleNamespace()),
            patch("src.tts_pipeline.services.tts_service.TranslationInputResolver") as resolver_cls,
            patch.object(service, "_next_subtitle_version", return_value=1),
            patch.object(service, "_mark_previous_outputs_non_current"),
            patch.object(service, "_persist_asset", return_value=MagicMock()),
            patch.object(service.db, "rollback"),
        ):
            load_sv.return_value = SimpleNamespace(id=source_id, workspace_id=workspace_id)
            resolver_cls.return_value.resolve.return_value = segments
            with self.assertRaises(TtsPipelineError):
                service.run_pipeline(
                    TtsRequest(source_video_id=source_id, voice_config=VoiceConfig(voice_id="v")),
                    on_progress=on_progress,
                )

        self.assertEqual(progress[0], ("synthesize_segment", 0))
        self.assertEqual(progress[1], ("synthesize_segment", 45))


if __name__ == "__main__":
    unittest.main()
