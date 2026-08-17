"""Native Google Cloud Agent Platform TTS integration tests (offline)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.api.routes.operations import test_tts_ai as _test_tts_ai_route
from src.audio_pipeline.google_cloud_genai import build_google_cloud_sdk_client
from src.schemas.operations import TtsAiTestRequest
from src.services.workspace_settings_service import WorkspaceSettingsService
from src.tts_pipeline.catalog import discover_tts_catalog
from src.tts_pipeline.google_cloud_agent_tts_provider import (
    GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
    GoogleCloudAgentTtsProvider,
)
from src.tts_pipeline.provider_factory import (
    TtsProbeResult,
    build_default_tts_provider,
    probe_tts_ai_client,
)
from src.tts_pipeline.services.emotion_planner import planner_enabled
from src.tts_pipeline.services.gemini_whole_video import resolve_gemini_synthesis_strategy
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput, VoiceConfig


class _FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        inline = SimpleNamespace(
            data=b"\x00\x00" * 2205,
            mime_type="audio/L16;codec=pcm;rate=22050",
        )
        part = SimpleNamespace(inline_data=inline)
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))]
        )


class _ModelNotFoundError(RuntimeError):
    status_code = 404


class _FallbackModels(_FakeModels):
    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"] == "gemini-3.1-flash-preview-tts":
            raise _ModelNotFoundError("Publisher model was not found in this project location")
        inline = SimpleNamespace(
            data=b"\x00\x00" * 2205,
            mime_type="audio/L16;codec=pcm;rate=22050",
        )
        part = SimpleNamespace(inline_data=inline)
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))]
        )


def _workspace(**overrides):
    base = {
        "enabled": True,
        "provider": "google_cloud_tts",
        "api_key": "agent-key",
        "base_url": "",
        "options_json": {
            "google_cloud_tts": {"region": "global"},
            "expressive_tts": {
                "mode": "required",
                "single_voice_mode": "required",
                "synthesis_strategy": "whole_video",
            },
        },
        "voice_id": "Achernar",
        "speaking_rate": 1.0,
        "language_code": "vi-VN",
        "model_id": GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
        "local_backend": "auto",
        "device": "auto",
        "cli_binary": "",
        "timeout_seconds": 30.0,
        "fallback_provider": "none",
        "fallback_voice_id": "",
        "credential_mode": "api_key",
        "google_service_account_json": None,
        "google_service_account_email": "",
        "google_service_account_project_id": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_native_provider_generates_audio_with_selected_model_voice_and_emotion_prompt() -> None:
    models = _FakeModels()
    provider = GoogleCloudAgentTtsProvider(
        api_key="agent-key",
        model_id=GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
        region="global",
        options={
            "expressive_tts": {
                "single_voice_mode": "required",
                "min_request_interval_seconds": 0,
            }
        },
        sdk_client=SimpleNamespace(models=models),
    )
    output = provider.synthesize(
        TtsProviderInput(
            text="[excited]\nHôm nay thật tuyệt vời!",
            language_code="vi-VN",
            voice_config=VoiceConfig(voice_id="Achernar", language_code="vi-VN"),
            voice_direction="Keep exactly one narrator identity.",
            requested_features=("emotion", "voice_direction"),
            expressive_mode="required",
        )
    )

    assert output.audio_bytes.startswith(b"RIFF")
    assert output.provider_metadata["provider"] == "google_cloud_tts"
    assert output.provider_metadata["adapter"] == "google-cloud-agent-tts-sdk-v1"
    assert output.provider_metadata["resolved_voice_id"] == "Achernar"
    assert len(models.calls) == 1
    call = models.calls[0]
    assert call["model"] == "gemini-2.5-flash-tts"
    assert call["config"]["response_modalities"] == ["AUDIO"]
    assert call["config"]["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"] == "Achernar"
    assert "[excited]" in call["contents"]


def test_factory_selects_new_provider_without_changing_legacy_google_gemini() -> None:
    provider = build_default_tts_provider(workspace_tts=_workspace(), allow_fallback=False)
    assert isinstance(provider, GoogleCloudAgentTtsProvider)
    assert provider.provider_name == "google_cloud_tts"


def test_agent_catalog_contains_new_and_stable_fallback_models() -> None:
    catalog = discover_tts_catalog("google_cloud_tts", language_code="vi-VN")
    assert catalog.default_model_id == "gemini-2.5-flash-tts"
    assert catalog.default_voice_id == "Achernar"
    assert "gemini-2.5-flash-tts" in catalog.models
    assert "gemini-2.5-pro-tts" in catalog.models
    assert "gemini-2.5-flash-lite-preview-tts" in catalog.models
    assert len(catalog.models) == 4
    assert any(voice.id == "Achernar" for voice in catalog.voices)


def test_agent_provider_falls_back_once_on_model_404_and_reuses_resolved_model() -> None:
    models = _FallbackModels()
    provider = GoogleCloudAgentTtsProvider(
        api_key="agent-key",
        model_id="gemini-3.1-flash-preview-tts",
        region="global",
        options={"expressive_tts": {"single_voice_mode": "required"}},
        sdk_client=SimpleNamespace(models=models),
    )
    request = TtsProviderInput(
        text="Xin chào.",
        language_code="vi-VN",
        voice_config=VoiceConfig(voice_id="Orus", language_code="vi-VN"),
    )

    first = provider.synthesize(request)
    second = provider.synthesize(request)

    assert [call["model"] for call in models.calls] == [
        "gemini-3.1-flash-preview-tts",
        "gemini-2.5-flash-tts",
        "gemini-2.5-flash-tts",
    ]
    assert first.provider_metadata["requested_model_id"] == "gemini-3.1-flash-preview-tts"
    assert first.provider_metadata["resolved_model_id"] == "gemini-2.5-flash-tts"
    assert first.provider_metadata["model_fallback_used"] is True
    assert first.provider_metadata["resolved_voice_id"] == "Orus"
    assert any("google_cloud_tts_model_fallback" in warning for warning in first.warnings)
    assert second.provider_metadata["resolved_model_id"] == "gemini-2.5-flash-tts"


def test_agent_provider_enables_existing_emotion_and_whole_video_algorithms() -> None:
    capabilities = {
        "supports_audio_tags": True,
        "supports_voice_direction": True,
    }
    assert planner_enabled(
        provider="google_cloud_tts",
        options={"emotion_planner": {"enabled": True}},
        capabilities=capabilities,
    )
    assert resolve_gemini_synthesis_strategy(
        provider="google_cloud_tts",
        expressive_options={
            "synthesis_strategy": "whole_video",
            "single_voice_mode": "required",
        },
    ) == "whole_video"


def test_ops_test_uses_real_audio_probe_only_when_remote_discovery_requested() -> None:
    cfg = _workspace()
    probe_output = TtsProviderOutput(
        audio_bytes=b"RIFF-probe",
        duration_seconds=0.1,
        mime_type="audio/wav",
        file_extension="wav",
        provider_metadata={},
        warnings=[],
    )
    with patch.object(GoogleCloudAgentTtsProvider, "synthesize", return_value=probe_output) as synthesize:
        offline = probe_tts_ai_client(cfg, discover_remote=False)
        assert offline.ok
        assert offline.catalog is not None
        synthesize.assert_not_called()

        live = probe_tts_ai_client(cfg, discover_remote=True)
    assert live.ok
    assert live.provider == "google_cloud_tts"
    assert "generated probe audio" in live.detail
    synthesize.assert_called_once()


def test_agent_api_key_client_ignores_project_and_regional_environment() -> None:
    with patch.dict(
        os.environ,
        {
            "GOOGLE_CLOUD_PROJECT": "must-not-leak",
            "GOOGLE_CLOUD_LOCATION": "asia-east1",
        },
    ):
        client = build_google_cloud_sdk_client(
            api_key="fake-agent-key",
            region="global",
            timeout_seconds=10,
        )
    api_client = client._api_client
    assert api_client.project is None
    assert api_client.location is None
    assert api_client.api_key == "fake-agent-key"
    assert api_client._http_options.base_url == "https://aiplatform.googleapis.com/"


def test_ops_catalog_mode_disables_only_agent_tts_remote_probe() -> None:
    service = MagicMock()
    service.get_tts_ai.return_value = _workspace()
    service.patch_tts_ai_runtime.return_value = {"last_probe": None}
    probe_result = TtsProbeResult(True, "google_cloud_tts", "Curated catalog ready.")

    with (
        patch("src.api.routes.operations.WorkspaceSettingsService", return_value=service),
        patch("src.api.routes.operations.probe_tts_ai_client", return_value=probe_result) as probe,
    ):
        response = _test_tts_ai_route(
            TtsAiTestRequest(probe_mode="catalog"),
            workspace_id=uuid4(),
            db=MagicMock(),
        )
    assert response.ok
    probe.assert_called_once()
    assert probe.call_args.kwargs["discover_remote"] is False

    service.get_tts_ai.return_value = _workspace(provider="google_gemini")
    with (
        patch("src.api.routes.operations.WorkspaceSettingsService", return_value=service),
        patch("src.api.routes.operations.probe_tts_ai_client", return_value=probe_result) as legacy_probe,
    ):
        _test_tts_ai_route(
            TtsAiTestRequest(probe_mode="catalog"),
            workspace_id=uuid4(),
            db=MagicMock(),
        )
    assert legacy_probe.call_args.kwargs["discover_remote"] is True


def test_workspace_persists_agent_api_key_without_touching_legacy_auth_modes() -> None:
    workspace = SimpleNamespace(id=uuid4(), settings_json={})
    db = MagicMock()
    db.get.return_value = workspace
    service = WorkspaceSettingsService(db)
    service.set_tts_ai(
        workspace.id,
        {
            "enabled": True,
            "provider": "google_cloud_tts",
            "voice_id": "Achernar",
            "speaking_rate": 1.0,
            "language_code": "vi-VN",
            "model_id": GOOGLE_CLOUD_TTS_DEFAULT_MODEL,
            "api_key": "agent-key",
            "credential_mode": "api_key",
            "base_url": "",
            "timeout_seconds": 90,
            "fallback_provider": "none",
            "fallback_voice_id": "",
            "local_backend": "auto",
            "device": "auto",
            "cli_binary": "",
            "options_json": {"google_cloud_tts": {"region": "global"}},
        },
    )
    saved = service.get_tts_ai(workspace.id)
    assert saved.provider == "google_cloud_tts"
    assert saved.api_key == "agent-key"
    assert saved.model_id == GOOGLE_CLOUD_TTS_DEFAULT_MODEL
