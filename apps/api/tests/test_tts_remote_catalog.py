"""Remote TTS catalog discovery and safe Ops probe integration."""

from __future__ import annotations

import io
import json
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

from src.schemas.operations import TtsAiCatalog
from src.tts_pipeline.catalog import (
    TtsCatalogDiscovery,
    TtsModelOption,
    TtsProviderCatalog,
    TtsVoiceOption,
)
from src.tts_pipeline.provider_factory import probe_tts_ai_client
from src.tts_pipeline.remote_catalog import (
    REMOTE_CATALOG_TIMEOUT_CAP_SECONDS,
    discover_remote_tts_catalog,
    remote_catalog_timeout_seconds,
)


class _JsonResponse:
    def __init__(self, payload: object):
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_JsonResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.raw if size < 0 else self.raw[:size]


def _public_resolver(*_: object, **__: object) -> list[tuple[object, ...]]:
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


class RemoteTtsCatalogTests(unittest.TestCase):
    def test_openai_compatible_parses_models_voices_languages_and_relations(self) -> None:
        secret = "sk-super-secret-value"
        seen_requests: list[tuple[str, str, float]] = []

        def opener(request, *, timeout: float):
            path = request.full_url.split("api.example.com", 1)[1]
            seen_requests.append((path, request.get_header("Authorization") or "", timeout))
            if path == "/v1/models":
                return _JsonResponse(
                    {
                        "default_model_id": "tts-fast",
                        "data": [
                            {
                                "id": "tts-fast",
                                "display_name": "Fast speech",
                                "description": "Low latency TTS",
                                "modalities": ["text", "audio"],
                                "supported_languages": [
                                    {"code": "vi", "name": "Vietnamese"},
                                    {"code": "en", "name": "English"},
                                ],
                                "voices": ["linh", "nam"],
                            },
                            {"id": "tts-hq", "languages": ["vi"], "voices": ["linh"]},
                        ],
                    }
                )
            if path == "/v1/voices":
                return _JsonResponse(
                    {
                        "default_voice_id": "linh",
                        "voices": [
                            {
                                "voice_id": "linh",
                                "display_name": "Linh",
                                "languages": ["vi"],
                                "models": ["tts-fast", "tts-hq"],
                                "gender": "female",
                            },
                            {"voice_id": "nam", "name": "Nam", "language_code": "vi"},
                        ],
                    }
                )
            if path == "/v1/languages":
                return _JsonResponse(
                    {
                        "default_language_code": "vi",
                        "languages": [
                            {"code": "vi", "label": "Tiếng Việt"},
                            {"code": "en", "label": "English"},
                        ],
                    }
                )
            raise AssertionError(f"unexpected endpoint: {path}")

        catalog = discover_remote_tts_catalog(
            "openai_compatible",
            base_url="https://api.example.com/v1",
            api_key=secret,
            language_code="vi",
            timeout_seconds=90,
            opener=opener,
            resolver=_public_resolver,
        )

        self.assertIsNotNone(catalog)
        assert catalog is not None
        self.assertEqual(catalog.source, "provider")
        self.assertEqual(catalog.models, ["tts-fast", "tts-hq"])
        self.assertEqual(catalog.default_model_id, "tts-fast")
        self.assertEqual(catalog.default_voice_id, "linh")
        self.assertEqual(catalog.default_language_code, "vi")
        self.assertEqual(catalog.discovery.status, "complete")
        self.assertEqual(catalog.discovery.endpoints, ["/models", "/voices", "/languages"])
        self.assertEqual(catalog.voices[0].languages, ["vi"])
        self.assertEqual(catalog.voices[0].models, ["tts-fast", "tts-hq"])
        self.assertEqual(catalog.model_options[0].voices, ["linh", "nam"])
        self.assertEqual(catalog.model_options[0].capabilities, ["text", "audio"])
        self.assertEqual([row.code for row in catalog.languages], ["vi", "en"])
        self.assertTrue(all(header == f"Bearer {secret}" for _, header, _ in seen_requests))
        self.assertTrue(all(0 < timeout <= REMOTE_CATALOG_TIMEOUT_CAP_SECONDS for _, _, timeout in seen_requests))

        payload = catalog.to_dict()
        validated = TtsAiCatalog.model_validate(payload)
        self.assertEqual(validated.model_options[0].languages, ["vi", "en"])
        self.assertEqual(validated.model_options[0].capabilities, ["text", "audio"])
        self.assertNotIn(secret, json.dumps(payload, ensure_ascii=False))

    def test_optional_endpoints_fail_best_effort_without_echoing_secret(self) -> None:
        secret = "sk-never-return-this"

        def opener(request, *, timeout: float):
            _ = timeout
            if request.full_url.endswith("/models"):
                return _JsonResponse(
                    {
                        "data": [
                            {"id": "tts-safe"},
                            {"id": f"malicious-{secret}", "description": secret},
                        ]
                    }
                )
            raise urllib.error.HTTPError(
                request.full_url,
                404,
                f"reflected {secret}",
                {},
                io.BytesIO(f'{{"error":"{secret}"}}'.encode()),
            )

        catalog = discover_remote_tts_catalog(
            "openai_compatible",
            base_url="https://api.example.com/v1",
            api_key=secret,
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        payload = catalog.to_dict()
        serialized = json.dumps(payload)
        self.assertEqual(catalog.models, ["tts-safe"])
        self.assertEqual(catalog.discovery.status, "partial")
        self.assertIn("HTTP 404", catalog.warning)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("api.example.com", catalog.warning)

    def test_private_network_and_plain_http_credentials_are_rejected_before_request(self) -> None:
        opened = False

        def opener(*_: object, **__: object):
            nonlocal opened
            opened = True
            raise AssertionError("request must not run")

        private = discover_remote_tts_catalog(
            "openai_compatible",
            base_url="https://127.0.0.1:9000/v1",
            api_key="sk-secret",
            opener=opener,
            resolver=lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 9000))],
        )
        insecure = discover_remote_tts_catalog(
            "openai_compatible",
            base_url="http://api.example.com/v1",
            api_key="sk-secret",
            opener=opener,
            resolver=_public_resolver,
        )

        assert private is not None and insecure is not None
        self.assertFalse(opened)
        self.assertEqual(private.discovery.status, "unavailable")
        self.assertIn("private", private.warning.lower())
        self.assertEqual(insecure.discovery.status, "unavailable")
        self.assertIn("https", insecure.warning.lower())

    def test_api_key_header_injection_is_rejected_before_request(self) -> None:
        opened = False

        def opener(*_: object, **__: object):
            nonlocal opened
            opened = True
            raise AssertionError("request must not run")

        catalog = discover_remote_tts_catalog(
            "openai_compatible",
            base_url="https://api.example.com/v1",
            api_key="valid-prefix\r\nX-Injected: true",
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        self.assertFalse(opened)
        self.assertEqual(catalog.discovery.status, "unavailable")
        self.assertIn("invalid", catalog.warning.lower())

    def test_known_cloud_defaults_and_provider_specific_headers(self) -> None:
        requests: list[tuple[str, str]] = []

        def opener(request, *, timeout: float):
            _ = timeout
            requests.append((request.full_url, request.get_header("X-goog-api-key") or ""))
            return _JsonResponse(
                {
                    "voices": [
                        {
                            "name": "vi-VN-Standard-A",
                            "languageCodes": ["vi-VN"],
                            "ssmlGender": "FEMALE",
                        }
                    ]
                }
            )

        catalog = discover_remote_tts_catalog(
            "google",
            base_url="",
            api_key="google-key",
            language_code="vi-VN",
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        self.assertEqual(requests, [("https://texttospeech.googleapis.com/v1/voices", "google-key")])
        self.assertEqual(catalog.voices[0].id, "vi-VN-Standard-A")
        self.assertEqual(catalog.voices[0].gender, "FEMALE")
        self.assertEqual(catalog.languages[0].code, "vi-VN")
        self.assertEqual(catalog.discovery.status, "complete")

    def test_azure_full_voice_endpoint_is_not_appended_twice(self) -> None:
        requests: list[tuple[str, str]] = []

        def opener(request, *, timeout: float):
            _ = timeout
            requests.append(
                (
                    request.full_url,
                    request.get_header("Ocp-apim-subscription-key") or "",
                )
            )
            return _JsonResponse(
                [
                    {
                        "ShortName": "vi-VN-HoaiMyNeural",
                        "DisplayName": "Hoai My",
                        "Locale": "vi-VN",
                        "SecondaryLocaleList": ["en-US"],
                        "Gender": "Female",
                    }
                ]
            )

        catalog = discover_remote_tts_catalog(
            "azure",
            base_url="https://eastus.tts.speech.microsoft.com/cognitiveservices/voices/list",
            api_key="azure-key",
            language_code="vi-VN",
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        self.assertEqual(
            requests,
            [
                (
                    "https://eastus.tts.speech.microsoft.com/cognitiveservices/voices/list",
                    "azure-key",
                )
            ],
        )
        self.assertEqual(catalog.voices[0].label, "Hoai My")
        self.assertEqual(catalog.voices[0].languages, ["vi-VN", "en-US"])
        self.assertEqual(catalog.languages[0].code, "vi-VN")

    def test_openai_filters_non_tts_models_and_keeps_current_voice_presets(self) -> None:
        def opener(_request, *, timeout: float):
            _ = timeout
            return _JsonResponse(
                {
                    "data": [
                        {"id": "gpt-4.1"},
                        {"id": "tts-1"},
                        {"id": "tts-1-hd"},
                        {"id": "gpt-4o-mini-tts"},
                    ]
                }
            )

        catalog = discover_remote_tts_catalog(
            "openai",
            base_url="",
            api_key="openai-key",
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        self.assertEqual(catalog.models, ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"])
        voice_ids = [voice.id for voice in catalog.voices]
        self.assertIn("marin", voice_ids)
        self.assertIn("cedar", voice_ids)
        self.assertNotIn("gpt-4.1", catalog.models)

    def test_requested_language_is_prioritized_before_option_cap(self) -> None:
        rows = [{"voice_id": f"en-{index}", "languageCodes": ["en-US"]} for index in range(510)]
        rows.append({"voice_id": "vi-priority", "languageCodes": ["vi-VN"]})

        def opener(request, *, timeout: float):
            _ = timeout
            if request.full_url.endswith("/models"):
                return _JsonResponse({"data": [{"id": "tts-safe"}]})
            if request.full_url.endswith("/voices"):
                return _JsonResponse({"voices": rows})
            raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, io.BytesIO(b"{}"))

        catalog = discover_remote_tts_catalog(
            "openai_compatible",
            base_url="https://api.example.com/v1",
            api_key="sk-priority",
            language_code="vi",
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        self.assertLessEqual(len(catalog.voices), 500)
        self.assertEqual(catalog.voices[0].id, "vi-priority")

    def test_elevenlabs_language_id_and_tts_capability_fields(self) -> None:
        def opener(request, *, timeout: float):
            _ = timeout
            if request.full_url.endswith("/models"):
                return _JsonResponse(
                    [
                        {"model_id": "not-tts", "can_do_text_to_speech": False},
                        {
                            "model_id": "eleven_multilingual_v2",
                            "can_do_text_to_speech": True,
                            "languages": [{"language_id": "vi", "name": "Vietnamese"}],
                        },
                    ]
                )
            if request.full_url.endswith("/voices"):
                return _JsonResponse(
                    {
                        "voices": [
                            {
                                "voice_id": "voice-1",
                                "name": "Vietnamese voice",
                                "high_quality_base_model_ids": ["eleven_multilingual_v2"],
                                "labels": {"language": "vi", "gender": "female"},
                            }
                        ]
                    }
                )
            raise AssertionError(request.full_url)

        catalog = discover_remote_tts_catalog(
            "elevenlabs",
            base_url="",
            api_key="eleven-key",
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        self.assertEqual(catalog.models, ["eleven_multilingual_v2"])
        self.assertEqual(catalog.voices[0].models, ["eleven_multilingual_v2"])
        self.assertEqual(catalog.voices[0].gender, "female")
        self.assertEqual(catalog.languages[0].code, "vi")

    def test_authentication_failure_is_typed_without_response_body(self) -> None:
        secret = "sk-auth-secret"

        def opener(request, *, timeout: float):
            _ = timeout
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                f"invalid {secret}",
                {},
                io.BytesIO(secret.encode()),
            )

        catalog = discover_remote_tts_catalog(
            "openai_compatible",
            base_url="https://api.example.com/v1",
            api_key=secret,
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        self.assertEqual(catalog.discovery.error_code, "authentication_failed")
        self.assertIn("authentication", catalog.warning.lower())
        self.assertNotIn(secret, json.dumps(catalog.to_dict()))

    def test_timeout_is_clamped_and_failure_detail_is_safe(self) -> None:
        observed: list[float] = []

        def opener(_request, *, timeout: float):
            observed.append(timeout)
            raise TimeoutError("socket included sensitive vendor diagnostics")

        catalog = discover_remote_tts_catalog(
            "openai_compatible",
            base_url="https://api.example.com/v1",
            api_key="sk-secret",
            timeout_seconds=999,
            opener=opener,
            resolver=_public_resolver,
        )

        assert catalog is not None
        self.assertTrue(observed)
        self.assertTrue(all(0 < timeout <= REMOTE_CATALOG_TIMEOUT_CAP_SECONDS for timeout in observed))
        self.assertEqual(remote_catalog_timeout_seconds(999), REMOTE_CATALOG_TIMEOUT_CAP_SECONDS)
        self.assertEqual(catalog.discovery.status, "unavailable")
        self.assertNotIn("sensitive", catalog.warning)

    def test_ops_probe_remote_discovery_is_explicit_and_uses_draft_fields(self) -> None:
        cfg = SimpleNamespace(
            provider="openai_compatible",
            api_key="sk-draft",
            base_url="https://api.example.com/v1",
            language_code="vi",
            timeout_seconds=45.0,
            cli_binary="",
        )
        remote = TtsProviderCatalog(
            source="provider",
            models=["tts-1"],
            model_options=[TtsModelOption(id="tts-1", label="TTS 1")],
            voices=[TtsVoiceOption(id="linh", label="Linh")],
        )
        with patch(
            "src.tts_pipeline.provider_factory.discover_remote_tts_catalog",
            return_value=remote,
        ) as discover:
            without_remote = probe_tts_ai_client(cfg, settings=SimpleNamespace())
            with_remote = probe_tts_ai_client(
                cfg,
                settings=SimpleNamespace(),
                discover_remote=True,
            )

        self.assertIsNone(without_remote.catalog)
        self.assertEqual(with_remote.catalog["models"], ["tts-1"])
        discover.assert_called_once_with(
            "openai_compatible",
            base_url="https://api.example.com/v1",
            api_key="sk-draft",
            language_code="vi",
            timeout_seconds=45.0,
        )

    def test_ops_probe_fails_closed_for_remote_auth_rejection(self) -> None:
        cfg = SimpleNamespace(
            provider="openai_compatible",
            api_key="sk-invalid",
            base_url="https://api.example.com/v1",
            language_code="vi",
            timeout_seconds=5.0,
            cli_binary="",
        )
        remote = TtsProviderCatalog(
            source="none",
            warning="Model catalog authentication was rejected (HTTP 401).",
            discovery=TtsCatalogDiscovery(
                status="unavailable",
                warnings=["Model catalog authentication was rejected (HTTP 401)."],
                error_code="authentication_failed",
            ),
        )
        with patch(
            "src.tts_pipeline.provider_factory.discover_remote_tts_catalog",
            return_value=remote,
        ):
            result = probe_tts_ai_client(
                cfg,
                settings=SimpleNamespace(),
                discover_remote=True,
            )

        self.assertFalse(result.ok)
        self.assertIn("HTTP 401", result.detail)
        self.assertNotIn("sk-invalid", result.detail)

    def test_ops_probe_reports_remote_transport_failure(self) -> None:
        cfg = SimpleNamespace(
            provider="openai_compatible",
            api_key="sk-draft",
            base_url="https://api.example.com/v1",
            language_code="vi",
            timeout_seconds=5.0,
            cli_binary="",
        )
        remote = TtsProviderCatalog(
            source="none",
            warning="Model catalog: Catalog endpoint could not be reached.",
            discovery=TtsCatalogDiscovery(
                status="unavailable",
                warnings=["Model catalog: Catalog endpoint could not be reached."],
                error_code="connection_error",
            ),
        )
        with patch(
            "src.tts_pipeline.provider_factory.discover_remote_tts_catalog",
            return_value=remote,
        ):
            result = probe_tts_ai_client(
                cfg,
                settings=SimpleNamespace(),
                discover_remote=True,
            )

        self.assertFalse(result.ok)
        self.assertIn("could not be reached", result.detail)


if __name__ == "__main__":
    unittest.main()
