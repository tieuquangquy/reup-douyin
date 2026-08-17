from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.audio_pipeline.translation_provider_preflight import (
    clear_translation_provider_preflight_cache,
    preflight_translation_provider,
)


def settings(**overrides):  # noqa: ANN003, ANN201
    values = {
        "translation_provider_preflight_enabled": True,
        "translation_provider_preflight_timeout_seconds": 12.0,
        "translation_provider_preflight_success_ttl_seconds": 300,
        "translation_provider_preflight_failure_ttl_seconds": 30,
        "audio_translation_provider": "auto",
        "gemini_api_key": "",
        "ollama_translation_model": "qwen2.5:14b",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def workspace_config():
    return SimpleNamespace(
        enabled=True,
        provider="openai_compatible",
        model="gpt-test",
        api_key="secret-not-logged",
        base_url="https://provider.example/v1",
        timeout_seconds=90.0,
        fallback_provider="none",
        fallback_model="",
    )


class TranslationProviderPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_translation_provider_preflight_cache()

    def tearDown(self) -> None:
        clear_translation_provider_preflight_cache()

    def test_403_is_non_retryable_configuration_failure_and_is_cached(self) -> None:
        with patch(
            "src.audio_pipeline.translation_provider_preflight.probe_translation_ai_client",
            return_value=(False, "openai_compatible", "openai_compatible_http_403:error code: 1010"),
        ) as probe:
            first = preflight_translation_provider(workspace_config(), settings=settings())
            second = preflight_translation_provider(workspace_config(), settings=settings())

        self.assertFalse(first.ok)
        self.assertFalse(first.retryable)
        self.assertEqual(first.error_context["http_status"], 403)
        self.assertEqual(first.error_context["provider_error_code"], "1010")
        self.assertEqual(first.error_context["recovery_action"], "CHECK_TRANSLATION_AI_CONNECTION")
        self.assertTrue(second.cached)
        probe.assert_called_once()

    def test_healthy_explicit_fallback_is_accepted_as_degraded(self) -> None:
        with patch(
            "src.audio_pipeline.translation_provider_preflight.probe_translation_ai_client",
            return_value=(True, "gemini", "fallback_ok:OK"),
        ):
            result = preflight_translation_provider(workspace_config(), settings=settings())

        self.assertTrue(result.ok)
        self.assertTrue(result.degraded_to_fallback)
        self.assertEqual(result.provider, "gemini")

    def test_transient_fallback_failure_stays_retryable_when_primary_is_blocked(self) -> None:
        with patch(
            "src.audio_pipeline.translation_provider_preflight.probe_translation_ai_client",
            return_value=(
                False,
                "qwen_ollama",
                "fallback=qwen_ollama_timeout:TimeoutError; "
                "primary=openai_compatible_http_403:error code: 1010",
            ),
        ):
            result = preflight_translation_provider(workspace_config(), settings=settings())

        self.assertFalse(result.ok)
        self.assertTrue(result.retryable)
        self.assertEqual(result.error_context["recovery_action"], "RETRY_TRANSLATION_PROVIDER")


if __name__ == "__main__":
    unittest.main()
