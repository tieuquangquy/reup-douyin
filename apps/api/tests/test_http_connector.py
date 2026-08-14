"""Focused tests for the declarative universal HTTP TTS connector."""

from __future__ import annotations

import base64
import io
import json
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

from src.tts_pipeline.http_connector import (
    GenericHttpTtsProvider,
    HttpConnectorConfigError,
    discover_http_connector_catalog,
    normalize_http_connector_options,
    normalize_connector_api_key,
    parse_http_connector_manifest,
    redact_http_connector_options,
)
from src.tts_pipeline.types import TtsProviderInput, VoiceConfig


class _Response:
    def __init__(self, payload, *, status: int = 200, content_type: str = "application/json", binary: bool = False):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = payload if binary else json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def getcode(self):
        return self.status

    def read(self, size: int = -1):
        return self._body if size < 0 else self._body[:size]


def _public_resolver(*_, **__):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


class HttpConnectorTests(unittest.TestCase):
    def test_key_normalization_removes_one_prefix_and_rejects_duplicate(self):
        key, warnings = normalize_connector_api_key("  Bearer sk_raw_123456  ")
        self.assertEqual(key, "sk_raw_123456")
        self.assertTrue(warnings)
        with self.assertRaises(HttpConnectorConfigError):
            normalize_connector_api_key("Bearer Bearer sk_raw_123456")

    def test_manifest_rejects_secrets_and_accepts_blank_ui_blocks(self):
        manifest = parse_http_connector_manifest(
            {
                "http_connector": {
                    "mode": "custom",
                    "auth": {"type": "header", "header_name": "X-API-Key"},
                    "catalog": {"models": {"path": ""}, "voices": {}, "languages": {}},
                    "synthesis": {"path": "", "body": {}, "response": {"type": "binary"}},
                }
            }
        )
        assert manifest is not None
        self.assertIsNone(manifest.catalog.models)
        self.assertIsNone(manifest.synthesis)
        with self.assertRaises(HttpConnectorConfigError):
            parse_http_connector_manifest(
                {
                    "http_connector": {
                        "synthesis": {
                            "path": "/tts",
                            "headers": {"X-Token": "secret-value"},
                        }
                    }
                }
            )
        normalized = normalize_http_connector_options(
            {
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "request_template": '{"api_key":"legacy-secret"}',
                    }
                }
            }
        )
        self.assertNotIn(
            "request_template",
            normalized["http_connector"]["synthesis"],
        )
        with self.assertRaises(HttpConnectorConfigError):
            normalize_http_connector_options({"http_connector": "Bearer leaked-secret"})
        self.assertNotIn(
            "http_connector",
            redact_http_connector_options({"http_connector": "Bearer leaked-secret"}),
        )
        redacted = redact_http_connector_options(
            {
                "http_connector": {
                    "synthesis": {
                        "request_template": '{"accessToken":"legacy-plain-secret"'
                    }
                }
            }
        )
        self.assertEqual(
            redacted["http_connector"]["synthesis"]["request_template"],
            "",
        )

    def test_custom_catalog_has_separate_auth_and_catalog_checks(self):
        seen = []

        def opener(request, *, timeout):
            path = request.full_url.split("example.com", 1)[1]
            seen.append((path, request.get_header("Authorization")))
            if path.endswith("/health"):
                return _Response({})
            if path.endswith("/models"):
                return _Response({"data": [{"id": "m1", "name": "Fast", "supported_languages": ["vi"]}]})
            raise AssertionError(path)

        manifest = parse_http_connector_manifest(
            {
                "http_connector": {
                    "mode": "custom",
                    "auth": {"type": "bearer", "test_path": "/health"},
                    "catalog": {
                        "models": {
                            "path": "/models",
                            "items_path": "data",
                            "id_path": "id",
                            "label_path": "name",
                            "languages_path": "supported_languages",
                        }
                    },
                }
            }
        )
        assert manifest is not None
        catalog = discover_http_connector_catalog(
            "http_custom",
            base_url="https://api.example.com/v1",
            api_key="Bearer sk_private_123456",
            language_code="vi",
            timeout_seconds=8,
            manifest=manifest,
            opener=opener,
            resolver=_public_resolver,
        )
        self.assertEqual(catalog.models, ["m1"])
        self.assertEqual(catalog.discovery.checks[0]["stage"], "authentication")
        self.assertEqual(catalog.discovery.checks[0]["status"], "passed")
        self.assertEqual(catalog.discovery.checks[-1]["stage"], "catalog")
        self.assertNotIn("sk_private", json.dumps(catalog.to_dict()))
        self.assertEqual(seen[0][1], "Bearer sk_private_123456")

    def test_json_rpc_post_catalog_loads_user_voices(self):
        seen = []

        def opener(request, *, timeout):
            payload = json.loads((request.data or b"{}").decode("utf-8"))
            seen.append((request.method, payload, request.get_header("Authorization")))
            return _Response(
                {
                    "result": {
                        "items": [
                            {"id": "voice-1", "name": "Narrator", "isActive": True},
                            {"id": "voice-2", "name": "Presenter", "isActive": True},
                        ],
                        "total": 2,
                    }
                }
            )

        manifest = parse_http_connector_manifest(
            {
                "http_connector": {
                    "mode": "custom",
                    "auth": {"type": "bearer"},
                    "catalog": {
                        "voices": {
                            "path": "/json-rpc",
                            "method": "POST",
                            "content_type": "application/json",
                            "body": {
                                "method": "getUserVoices",
                                "input": {"limit": 10, "page": 1},
                            },
                            "items_path": "result.items",
                            "id_path": "id",
                            "label_path": "name",
                        }
                    },
                }
            }
        )
        assert manifest is not None
        catalog = discover_http_connector_catalog(
            "http_custom",
            base_url="https://api.lucylab.io",
            api_key="sk_lucylab_test",
            language_code="vi",
            timeout_seconds=8,
            manifest=manifest,
            opener=opener,
            resolver=_public_resolver,
        )
        self.assertEqual([voice.id for voice in catalog.voices], ["voice-1", "voice-2"])
        self.assertEqual(seen[0][0], "POST")
        self.assertEqual(seen[0][1]["method"], "getUserVoices")
        self.assertEqual(seen[0][2], "Bearer sk_lucylab_test")

    def test_query_auth_is_appended_server_side_and_not_returned_in_catalog(self):
        seen_urls = []

        def opener(request, *, timeout):
            seen_urls.append(request.full_url)
            self.assertIsNone(request.get_header("Authorization"))
            return _Response({"data": [{"id": "m-query", "name": "Query auth"}]})

        manifest = parse_http_connector_manifest(
            {
                "http_connector": {
                    "mode": "custom",
                    "auth": {"type": "query", "query_name": "api_key"},
                    "catalog": {
                        "models": {
                            "path": "/models",
                            "items_path": "data",
                            "id_path": "id",
                            "label_path": "name",
                        }
                    },
                }
            }
        )
        assert manifest is not None
        catalog = discover_http_connector_catalog(
            "http_custom",
            base_url="https://api.example.com/v1",
            api_key="Bearer sk_query_123456",
            language_code="vi",
            timeout_seconds=8,
            manifest=manifest,
            opener=opener,
            resolver=_public_resolver,
        )
        self.assertEqual(catalog.models, ["m-query"])
        self.assertIn("api_key=sk_query_123456", seen_urls[0])
        self.assertNotIn("sk_query_123456", json.dumps(catalog.to_dict()))

    def test_openapi_mode_is_same_origin_and_infers_model_endpoint(self):
        def opener(request, *, timeout):
            path = request.full_url.split("example.com", 1)[1]
            if path.endswith("/openapi.json"):
                return _Response({"openapi": "3.0.0", "paths": {"/v1/models": {"get": {"operationId": "listModels"}}}})
            if path.endswith("/v1/models"):
                return _Response({"data": [{"id": "m-openapi", "name": "OpenAPI model"}]})
            raise AssertionError(path)

        manifest = parse_http_connector_manifest(
            {
                "http_connector": {
                    "mode": "openapi",
                    "openapi": {"url": "https://api.example.com/openapi.json"},
                }
            }
        )
        assert manifest is not None
        catalog = discover_http_connector_catalog(
            "openai_compatible",
            base_url="https://api.example.com/v1",
            api_key="",
            language_code="vi",
            timeout_seconds=8,
            manifest=manifest,
            opener=opener,
            resolver=_public_resolver,
        )
        self.assertEqual(catalog.models, ["m-openapi"])
        self.assertEqual(catalog.discovery.status, "complete")

    def test_auth_check_does_not_accept_injected_non_2xx_response(self):
        manifest = parse_http_connector_manifest(
            {"http_connector": {"mode": "custom", "auth": {"test_path": "/health"}}}
        )
        assert manifest is not None
        catalog = discover_http_connector_catalog(
            "http_custom",
            base_url="https://api.example.com/v1",
            api_key="sk_raw_123456",
            language_code="vi",
            timeout_seconds=8,
            manifest=manifest,
            opener=lambda request, timeout: _Response({}, status=401),
            resolver=_public_resolver,
        )
        self.assertEqual(catalog.discovery.error_code, "authentication_failed")
        self.assertEqual(catalog.discovery.checks[0]["status"], "failed")

    def test_generic_base64_synthesis_escapes_text_and_returns_audio(self):
        encoded = base64.b64encode(b"ID3audio").decode("ascii")
        seen_body = []

        def opener(request, *, timeout):
            seen_body.append(request.data)
            return _Response({"audio": encoded})

        options = {
            "http_connector": {
                "mode": "custom",
                "synthesis": {
                    "path": "/tts",
                    "body": {"input": "{{text}}", "voice": "{{voice_id}}"},
                    "response": {"type": "json_base64", "audio_path": "audio", "mime_type": "audio/mpeg"},
                },
            }
        }
        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key="sk_raw_123456",
            model_id="model-1",
            options=options,
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        output = provider.synthesize(
            TtsProviderInput(
                text='hello "quoted"',
                language_code="vi",
                voice_config=VoiceConfig(voice_id="voice-1"),
            )
        )
        self.assertEqual(output.audio_bytes, b"ID3audio")
        self.assertEqual(json.loads(seen_body[0].decode("utf-8"))["input"], 'hello "quoted"')
        self.assertEqual(output.file_extension, "mp3")

    def test_synthesis_exposes_provider_neutral_performance_context(self):
        seen_body = []

        def opener(request, *, timeout):
            seen_body.append(json.loads(request.data.decode("utf-8")))
            return _Response(
                b"RIFFaudio",
                content_type="audio/wav",
                binary=True,
            )

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="expressive-1",
            options={
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {
                            "input": "{{rendered_text}}",
                            "direction": "{{voice_direction}}",
                            "context": "{{sample_context}}",
                            "tags": "{{audio_tags}}",
                            "ssml": "{{ssml_text}}",
                            "state": "{{prosody_state}}",
                            "chunk": "{{performance_chunk_id}}",
                        },
                        "response": {"type": "binary", "mime_type": "audio/wav"},
                    }
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        provider.synthesize(
            TtsProviderInput(
                text="[serious]\nXin chÃ o",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="voice-1"),
                voice_direction="speak naturally",
                sample_context="opening reference",
                audio_tags=("serious", "slow"),
                prosody_state={"emotion": "neutral"},
                performance_chunk_id="chunk-01",
                ssml_text="<speak>Xin chÃ o</speak>",
            )
        )
        body = seen_body[0]
        self.assertEqual(body["input"], "[serious]\nXin chÃ o")
        self.assertEqual(body["direction"], "speak naturally")
        self.assertEqual(body["context"], "opening reference")
        self.assertEqual(body["tags"], "serious, slow")
        self.assertEqual(json.loads(body["state"]), {"emotion": "neutral"})
        self.assertEqual(body["chunk"], "chunk-01")

    def test_required_expressive_mode_fails_before_network_when_manifest_drops_emotion(self):
        called = []

        def opener(request, *, timeout):
            called.append(True)
            return _Response(b"RIFFaudio", content_type="audio/wav", binary=True)

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="plain-1",
            options={
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "binary", "mime_type": "audio/wav"},
                    }
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        with self.assertRaises(Exception) as raised:
            provider.synthesize(
                TtsProviderInput(
                    text="hello",
                    language_code="vi",
                    voice_config=VoiceConfig(),
                    expressive_mode="required",
                    requested_features=("emotion",),
                    audio_tags=("excited",),
                )
            )
        self.assertIn("expressive", str(raised.exception).lower())
        self.assertFalse(called)

    def test_required_pause_is_applied_through_canonical_voice_direction(self):
        called = []

        def opener(request, *, timeout):
            called.append(json.loads(request.data.decode("utf-8")))
            return _Response(b"RIFFaudio", content_type="audio/wav", binary=True)

        provider = GenericHttpTtsProvider(
            provider_name="google_gemini",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="expressive-1",
            options={
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {
                            "input": "{{rendered_text}}",
                            "direction": "{{voice_direction}}",
                        },
                        "response": {"type": "binary", "mime_type": "audio/wav"},
                    }
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )

        output = provider.synthesize(
            TtsProviderInput(
                text="Xin chào",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="Sadachbia"),
                voice_direction="emotion neutral; emphasize: none; pauses: before 0ms, after 180ms.",
                expressive_mode="required",
                requested_features=("pause",),
            )
        )

        self.assertEqual(output.audio_bytes, b"RIFFaudio")
        self.assertEqual(len(called), 1)
        contract = output.provider_metadata["execution_contract"]
        self.assertIn("pause", contract["applied_features"])
        self.assertEqual(contract["degraded_features"], [])

    def test_synthesis_requires_https_even_without_auth(self):
        options = {
            "http_connector": {
                "synthesis": {"path": "/tts", "response": {"type": "binary"}},
            }
        }
        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="http://api.example.com/v1",
            api_key=None,
            model_id="",
            options=options,
            timeout_seconds=8,
            resolver=_public_resolver,
        )
        with self.assertRaises(Exception):
            provider.synthesize(
                TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
            )

    def test_synthesis_http_error_surfaces_allowlisted_provider_reason_without_secrets(self):
        provider_payload = {
            "detail": {
                "type": "invalid_request_error",
                "code": "model_not_supported",
                "message": "The selected model is not available for this voice; key sk_should_not_leak_123456.",
                "api_key": "sk_nested_should_not_leak_123456",
                "request_id": "provider-request-id",
            }
        }

        def opener(request, *, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {"Content-Type": "application/json"},
                io.BytesIO(json.dumps(provider_payload).encode("utf-8")),
            )

        provider = GenericHttpTtsProvider(
            provider_name="elevenlabs",
            base_url="https://api.example.com/v1",
            api_key="sk_workspace_test_123456",
            model_id="model-1",
            options={
                "http_connector": {
                    "auth": {"type": "header", "header_name": "xi-api-key", "prefix": ""},
                    "synthesis": {
                        "path": "/text-to-speech/{{voice_id}}",
                        "body": {"text": "{{text}}", "model_id": "{{model_id}}"},
                        "response": {"type": "binary", "mime_type": "audio/mpeg"},
                    },
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )

        with self.assertRaises(Exception) as raised:
            provider.synthesize(
                TtsProviderInput(
                    text="hello",
                    language_code="vi",
                    voice_config=VoiceConfig(voice_id="voice-1"),
                )
            )
        detail = str(raised.exception)
        self.assertIn("model_not_supported", detail)
        self.assertIn("The selected model is not available", detail)
        self.assertNotIn("sk_should_not_leak", detail)
        self.assertNotIn("provider-request-id", detail)

    def test_async_polling_returns_bounded_base64_audio(self):
        calls = []

        def opener(request, *, timeout):
            calls.append(request.full_url)
            if request.full_url.endswith("/tts"):
                return _Response({"task": {"id": "job/1"}})
            if request.full_url.endswith("/jobs/job%2F1"):
                return _Response(
                    {
                        "status": "completed",
                        "result": {"audio": base64.b64encode(b"ID3async").decode("ascii")},
                    }
                )
            raise AssertionError(request.full_url)

        options = {
            "http_connector": {
                "synthesis": {
                    "path": "/tts",
                    "body": {"input": "{{text}}"},
                    "response": {"type": "async_json", "mime_type": "audio/mpeg"},
                    "polling": {
                        "job_id_path": "task.id",
                        "poll_path": "/jobs/{{job_id}}",
                        "status_path": "status",
                        "response_type": "json_base64",
                        "audio_path": "result.audio",
                        "interval_seconds": 0.1,
                        "max_attempts": 2,
                    },
                }
            }
        }
        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="",
            options=options,
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
            sleeper=lambda _: None,
        )
        output = provider.synthesize(
            TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
        )
        self.assertEqual(output.audio_bytes, b"ID3async")
        self.assertEqual(len(calls), 2)

    def test_async_polling_supports_json_rpc_post_body(self):
        calls = []

        def opener(request, *, timeout):
            payload = json.loads((request.data or b"{}").decode("utf-8"))
            headers = {key.lower(): value for key, value in request.header_items()}
            calls.append((request.method, payload, headers.get("authorization")))
            if payload.get("method") == "ttsLongText":
                return _Response({"result": {"projectExportId": "job/1"}}, status=202)
            if payload.get("method") == "getExportStatus":
                self.assertEqual(payload["input"]["projectExportId"], "job/1")
                return _Response(
                    {
                        "result": {
                            "state": "completed",
                            "url": "https://cdn.example.com/job-1.mp3",
                        }
                    }
                )
            if request.full_url.endswith("/job-1.mp3"):
                return _Response(b"ID3lucylab", content_type="audio/mpeg", binary=True)
            raise AssertionError(request.full_url)

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.lucylab.io",
            api_key="sk_lucylab_test",
            model_id="",
            options={
                "http_connector": {
                    "auth": {
                        "type": "bearer",
                        "header_name": "Authorization",
                        "prefix": "Bearer ",
                    },
                    "synthesis": {
                        "path": "/json-rpc",
                        "body": {
                            "method": "ttsLongText",
                            "input": {
                                "text": "{{text}}",
                                "userVoiceId": "{{voice_id}}",
                                "speed": "{{speaking_rate}}",
                            },
                        },
                        "response": {
                            "type": "async_json",
                            "mime_type": "audio/mpeg",
                            "file_extension": "mp3",
                        },
                        "polling": {
                            "method": "POST",
                            "content_type": "application/json",
                            "body": {
                                "method": "getExportStatus",
                                "input": {"projectExportId": "{{job_id}}"},
                            },
                            "job_id_path": "result.projectExportId",
                            "poll_path": "/json-rpc",
                            "status_path": "result.state",
                            "success_values": ["completed"],
                            "failure_values": ["failed"],
                            "response_type": "json_url",
                            "audio_path": "result.url",
                            "interval_seconds": 0.1,
                            "max_attempts": 2,
                        },
                    },
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
            sleeper=lambda _: None,
        )
        output = provider.synthesize(
            TtsProviderInput(
                text="hello",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="voice-1"),
            )
        )
        self.assertEqual(output.audio_bytes, b"ID3lucylab")
        self.assertEqual([call[0] for call in calls[:2]], ["POST", "POST"])
        self.assertEqual(calls[0][2], "Bearer sk_lucylab_test")
        self.assertEqual(calls[1][2], "Bearer sk_lucylab_test")

    def test_async_polling_accepts_raw_binary_terminal_response(self):
        def opener(request, *, timeout):
            if request.full_url.endswith("/tts"):
                return _Response({"task_id": "job-raw"})
            return _Response(
                b"ID3raw-audio",
                content_type="audio/mpeg",
                binary=True,
            )

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="",
            options={
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "async_json", "mime_type": "audio/mpeg"},
                        "polling": {
                            "job_id_path": "task_id",
                            "poll_path": "/jobs/{{job_id}}",
                            "response_type": "binary",
                            "max_attempts": 1,
                        },
                    }
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
            sleeper=lambda _: None,
        )
        output = provider.synthesize(
            TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
        )
        self.assertEqual(output.audio_bytes, b"ID3raw-audio")

    def test_async_json_url_accepts_mpeg_frame_without_id3_tag(self):
        def opener(request, *, timeout):
            if request.full_url.endswith("/tts"):
                return _Response({"id": "job-genmax", "status": "pending"})
            if request.full_url.endswith("/history/job-genmax"):
                return _Response(
                    {"id": "job-genmax", "status": "completed", "result": {"audio_url": "https://cdn.example.com/audio.mp3"}}
                )
            if request.full_url.endswith("/audio.mp3"):
                # MPEG-2 frame without an ID3 header; some providers also omit
                # or mislabel the audio Content-Type on their public media URL.
                return _Response(b"\xff\xe3genmax-mp3", content_type="text/plain", binary=True)
            raise AssertionError(request.full_url)

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.genmax.io/v1",
            api_key="sk_test_genmax",
            model_id="eleven_multilingual_v2",
            options={
                "http_connector": {
                    "auth": {"type": "header", "header_name": "xi-api-key", "prefix": ""},
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "async_json", "mime_type": "audio/mpeg", "file_extension": "mp3"},
                        "polling": {
                            "job_id_path": "id",
                            "poll_path": "/history/{{job_id}}",
                            "status_path": "status",
                            "success_values": ["completed"],
                            "failure_values": ["failed"],
                            "response_type": "json_url",
                            "audio_path": "result.audio_url",
                            "interval_seconds": 0.1,
                            "max_attempts": 2,
                        },
                    },
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
            sleeper=lambda _: None,
        )
        output = provider.synthesize(
            TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig(voice_id="voice-1"))
        )
        self.assertEqual(output.audio_bytes, b"\xff\xe3genmax-mp3")
        self.assertEqual(output.mime_type, "audio/mpeg")

    def test_json_url_uses_configured_audio_mime_when_media_mime_is_wrong(self):
        def opener(request, *, timeout):
            if request.full_url.endswith("/tts"):
                return _Response({"url": "https://cdn.example.com/audio.mp3"})
            return _Response(b"\x00\x01provider-audio", content_type="application/json", binary=True)

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="",
            options={
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "json_url", "audio_path": "url", "mime_type": "audio/mpeg"},
                    }
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        output = provider.synthesize(
            TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
        )
        self.assertEqual(output.mime_type, "audio/mpeg")

    def test_same_origin_media_url_reuses_connector_auth(self):
        seen_media_headers = {}

        def opener(request, *, timeout):
            if request.full_url.endswith("/tts"):
                return _Response({"url": "https://api.example.com/audio/task.mp3"})
            if request.full_url.endswith("/audio/task.mp3"):
                seen_media_headers.update({key.lower(): value for key, value in request.header_items()})
                if seen_media_headers.get("xi-api-key") != "sk_same_origin":
                    return _Response(b"<html>login</html>", content_type="text/html", binary=True)
                return _Response(b"ID3protected-audio", content_type="audio/mpeg", binary=True)
            raise AssertionError(request.full_url)

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key="sk_same_origin",
            model_id="",
            options={
                "http_connector": {
                    "auth": {"type": "header", "header_name": "xi-api-key", "prefix": ""},
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "json_url", "audio_path": "url", "mime_type": "audio/mpeg"},
                    },
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        output = provider.synthesize(
            TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
        )
        self.assertEqual(output.audio_bytes, b"ID3protected-audio")
        self.assertEqual(seen_media_headers.get("xi-api-key"), "sk_same_origin")

    def test_cross_origin_media_url_never_receives_connector_auth(self):
        seen_media_headers = {}

        def opener(request, *, timeout):
            if request.full_url.endswith("/tts"):
                return _Response({"url": "https://cdn.example.com/audio/task.mp3"})
            if request.full_url.endswith("/audio/task.mp3"):
                seen_media_headers.update({key.lower(): value for key, value in request.header_items()})
                return _Response(b"ID3public-audio", content_type="audio/mpeg", binary=True)
            raise AssertionError(request.full_url)

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key="sk_private",
            model_id="",
            options={
                "http_connector": {
                    "auth": {"type": "header", "header_name": "xi-api-key", "prefix": ""},
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "json_url", "audio_path": "url", "mime_type": "audio/mpeg"},
                    },
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        output = provider.synthesize(
            TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
        )
        self.assertEqual(output.audio_bytes, b"ID3public-audio")
        self.assertNotIn("xi-api-key", seen_media_headers)

    def test_json_url_still_rejects_json_error_with_configured_audio_mime(self):
        def opener(request, *, timeout):
            if request.full_url.endswith("/tts"):
                return _Response({"url": "https://cdn.example.com/audio.mp3"})
            return _Response(b'{"error":"not ready"}', content_type="application/json", binary=True)

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="",
            options={
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "json_url", "audio_path": "url", "mime_type": "audio/mpeg"},
                    }
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        with self.assertRaises(Exception):
            provider.synthesize(
                TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
            )

    def test_json_url_rejects_html_download(self):
        def opener(request, *, timeout):
            if request.full_url.endswith("/tts"):
                return _Response({"url": "https://cdn.example.com/audio.mp3"})
            return _Response(b"<html>not audio</html>", content_type="text/html", binary=True)

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="",
            options={
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "json_url", "audio_path": "url"},
                    }
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        with self.assertRaises(Exception):
            provider.synthesize(
                TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
            )

    def test_json_url_rejects_non_2xx_even_when_body_looks_like_audio(self):
        def opener(request, *, timeout):
            if request.full_url.endswith("/tts"):
                return _Response({"url": "https://cdn.example.com/audio.mp3"})
            return _Response(
                b"ID3error-body",
                status=404,
                content_type="audio/mpeg",
                binary=True,
            )

        provider = GenericHttpTtsProvider(
            provider_name="http_custom",
            base_url="https://api.example.com/v1",
            api_key=None,
            model_id="",
            options={
                "http_connector": {
                    "synthesis": {
                        "path": "/tts",
                        "body": {"input": "{{text}}"},
                        "response": {"type": "json_url", "audio_path": "url"},
                    }
                }
            },
            timeout_seconds=8,
            opener=opener,
            resolver=_public_resolver,
        )
        with self.assertRaises(Exception):
            provider.synthesize(
                TtsProviderInput(text="hello", language_code="vi", voice_config=VoiceConfig())
            )


if __name__ == "__main__":
    unittest.main()
