"""Additive native Google Cloud provider coverage for Translation + Caption AI."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.audio_pipeline.google_cloud_genai import (
    GoogleCloudAgentPlatformClient,
    GoogleCloudCaptionChatAdapter,
    is_google_cloud_retryable_error,
)
from src.audio_pipeline.provider_factory import build_default_translation_provider
from src.audio_pipeline.translation_ai_models import list_translation_ai_models
from src.audio_pipeline.translation_provider_mode import resolve_translation_provider_mode
from src.media_pipeline.translator.client import build_openai_client
from src.media_pipeline.translator.config import TranslatorSettings
from src.media_pipeline.translator.resolve import resolve_translator_settings
from src.services.workspace_settings_service import (
    CAPTION_AI_KEY,
    TRANSLATION_AI_KEY,
    TranslationAiConfig,
    WorkspaceSettingsService,
)


class _FakeGenerateModels:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


class GoogleCloudNativeClientTests(unittest.TestCase):
    def test_mode_is_native_without_changing_legacy_gcp_vertex(self) -> None:
        self.assertEqual(resolve_translation_provider_mode("google_cloud"), "google_cloud")
        self.assertEqual(resolve_translation_provider_mode("gcp_vertex"), "openai_compatible")

    def test_dialogue_completion_uses_native_sdk_shape(self) -> None:
        models = _FakeGenerateModels("Xin chào")
        client = GoogleCloudAgentPlatformClient(
            api_key="gcp-key",
            model="gemini-3.7-flash",
            region="global",
            sdk_client=SimpleNamespace(models=models),
        )
        self.assertEqual(client.complete("Dịch câu này"), "Xin chào")
        self.assertEqual(models.calls[0]["model"], "gemini-3.7-flash")
        self.assertEqual(models.calls[0]["contents"], "Dịch câu này")
        self.assertEqual(models.calls[0]["config"]["temperature"], 0.2)

    def test_caption_adapter_requests_json_via_native_sdk(self) -> None:
        models = _FakeGenerateModels(json.dumps({"box_0": "Xin chào"}, ensure_ascii=False))
        native = GoogleCloudAgentPlatformClient(
            api_key="gcp-key",
            model="gemini-3.7-flash",
            sdk_client=SimpleNamespace(models=models),
        )
        adapter = GoogleCloudCaptionChatAdapter(native)
        response = adapter.chat.completions.create(
            model="gemini-3.7-flash",
            messages=[
                {"role": "system", "content": "Trả JSON"},
                {"role": "user", "content": '{"box_0":"你好"}'},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        self.assertEqual(response.choices[0].message.content, '{"box_0": "Xin chào"}')
        cfg = models.calls[0]["config"]
        self.assertEqual(cfg["response_mime_type"], "application/json")
        self.assertEqual(cfg["system_instruction"], "Trả JSON")

    def test_model_discovery_uses_curated_catalog_without_oauth_only_list_call(self) -> None:
        with patch(
            "src.audio_pipeline.translation_ai_models.list_google_cloud_models",
            side_effect=AssertionError("must not call Vertex models.list with an API key"),
            create=True,
        ) as list_remote:
            ok, models, detail = list_translation_ai_models(
                provider="google_cloud",
                api_key="gcp-key",
                base_url="",
                region="global",
            )
        self.assertTrue(ok)
        self.assertIn("gemini-3.7-flash", models)
        self.assertEqual(detail, "")
        list_remote.assert_not_called()

    def test_retry_classifier_only_retries_transient_google_cloud_failures(self) -> None:
        self.assertTrue(is_google_cloud_retryable_error(RuntimeError("google_cloud_http_429:quota")))
        self.assertTrue(is_google_cloud_retryable_error(RuntimeError("google_cloud_http_503:down")))
        self.assertFalse(is_google_cloud_retryable_error(RuntimeError("google_cloud_http_401:bad key")))


class GoogleCloudRuntimeWiringTests(unittest.TestCase):
    def test_translation_factory_selects_google_cloud_only_for_new_provider(self) -> None:
        workspace_ai = SimpleNamespace(
            enabled=True,
            provider="google_cloud",
            model="gemini-3.7-flash",
            api_key="gcp-key",
            base_url="",
            region="global",
            timeout_seconds=45,
            fallback_provider="none",
            fallback_model="",
        )
        provider = build_default_translation_provider(
            settings=SimpleNamespace(), workspace_ai=workspace_ai
        )
        self.assertIsInstance(provider.primary, GoogleCloudAgentPlatformClient)
        self.assertEqual(provider.primary.region, "global")
        self.assertEqual(provider.primary.model, "gemini-3.7-flash")

    def test_caption_resolver_keeps_caption_store_and_native_provider(self) -> None:
        cfg = resolve_translator_settings(
            workspace_ai=TranslationAiConfig(
                enabled=True,
                provider="google_cloud",
                model="gemini-3.7-flash",
                api_key="gcp-key",
                region="global",
            ),
            system_prompt="Caption prompt",
        )
        self.assertEqual(cfg.provider, "google_cloud")
        self.assertEqual(cfg.region, "global")
        self.assertEqual(cfg.base_url, "")

    def test_caption_factory_selects_native_adapter_only_for_google_cloud(self) -> None:
        settings = TranslatorSettings(
            api_key="gcp-key",
            base_url="",
            model_name="gemini-3.7-flash",
            system_prompt="Caption prompt",
            provider="google_cloud",
            region="global",
        )
        with patch(
            "src.media_pipeline.translator.client.build_google_cloud_caption_client",
            return_value=MagicMock(name="native-adapter"),
        ) as build_native:
            client = build_openai_client(settings)
        self.assertIs(client, build_native.return_value)
        build_native.assert_called_once_with(
            api_key="gcp-key",
            model="gemini-3.7-flash",
            region="global",
            timeout_seconds=90.0,
        )

    def test_translation_and_caption_google_cloud_profiles_are_independent(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        common = {
            "enabled": True,
            "provider": "google_cloud",
            "model": "gemini-3.7-flash",
            "base_url": "",
            "region": "global",
            "timeout_seconds": 90,
            "fallback_provider": "none",
            "fallback_model": "",
        }
        service.set_translation_ai(workspace.id, {**common, "api_key": "translation-key"})
        service.set_caption_ai(workspace.id, {**common, "api_key": "caption-key"})

        self.assertIn(TRANSLATION_AI_KEY, workspace.settings_json)
        self.assertIn(CAPTION_AI_KEY, workspace.settings_json)
        self.assertEqual(service.get_translation_ai(workspace.id).api_key, "translation-key")
        self.assertEqual(service.get_caption_ai(workspace.id).api_key, "caption-key")
        self.assertEqual(service.get_translation_ai(workspace.id).region, "global")
        self.assertEqual(service.get_caption_ai(workspace.id).region, "global")


if __name__ == "__main__":
    unittest.main()
