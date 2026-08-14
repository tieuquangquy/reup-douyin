"""Production TTS uses exactly one active, enabled Ops setup."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.services.workspace_settings_service import TtsAiConfig
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.services.profile_authority import (
    TTS_PROFILE_AUTHORITY_SCHEMA,
    assert_manifest_tts_authority_active,
    bind_active_tts_profile_authority,
    resolve_active_tts_profile_authority,
)
from src.tts_pipeline.services.tts_service import TtsPipelineService, _same_tts_authority
from src.tts_pipeline.provider_factory import build_default_tts_provider
from src.tts_pipeline.types import TtsRequest, VoiceConfig


def _workspace(*, enabled: bool = True, fallback: str = "none"):
    return SimpleNamespace(
        id=uuid4(),
        settings_json={
            "tts_ai": {
                "active_profile_id": "genmax",
                "profiles": [
                    {
                        "id": "genmax",
                        "name": "GenMax - ElevenLabs VI",
                        "enabled": enabled,
                        "provider": "http_custom",
                        "voice_id": "Sis3lVCb7dLbeqH5ZkiC",
                        "speaking_rate": 1.0,
                        "language_code": "vi",
                        "model_id": "eleven_v3",
                        "api_key": "secret-key",
                        "base_url": "https://tts.example.test",
                        "timeout_seconds": 120.0,
                        "fallback_provider": fallback,
                        "fallback_voice_id": "",
                        "local_backend": "auto",
                        "device": "auto",
                        "cli_binary": "",
                        "options_json": {"http_connector": {"schema_version": "http_tts_connector_v1"}},
                    },
                    {
                        "id": "omnivoice",
                        "name": "OmniVoice",
                        "enabled": False,
                        "provider": "omnivoice",
                        "voice_id": "instruct:vi_female_north",
                        "model_id": "k2-fsa/OmniVoice",
                    },
                ],
            }
        },
    )


class TtsVoiceAuthorityTests(unittest.TestCase):
    def test_bind_uses_only_active_enabled_setup_and_redacts_secret(self) -> None:
        workspace = _workspace()
        db = MagicMock()
        db.get.return_value = workspace

        authority = bind_active_tts_profile_authority(db, workspace.id)

        self.assertEqual(authority["schema_version"], TTS_PROFILE_AUTHORITY_SCHEMA)
        self.assertEqual(authority["profile_id"], "genmax")
        self.assertEqual(authority["provider"], "http_custom")
        self.assertEqual(authority["model_id"], "eleven_v3")
        self.assertEqual(authority["voice_id"], "Sis3lVCb7dLbeqH5ZkiC")
        self.assertNotIn("api_key", authority)
        self.assertNotIn("base_url", authority)

    def test_no_setup_on_fails_before_job_creation(self) -> None:
        workspace = _workspace(enabled=False)
        db = MagicMock()
        db.get.return_value = workspace

        with self.assertRaises(TtsPipelineError) as caught:
            bind_active_tts_profile_authority(db, workspace.id)

        self.assertEqual(caught.exception.code, TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED)

    def test_unique_on_setup_wins_over_stale_active_pointer(self) -> None:
        workspace = _workspace()
        store = workspace.settings_json["tts_ai"]
        store["active_profile_id"] = "omnivoice"
        db = MagicMock()
        db.get.return_value = workspace

        authority = bind_active_tts_profile_authority(db, workspace.id)

        self.assertEqual(authority["profile_id"], "genmax")
        self.assertEqual(authority["provider"], "http_custom")
        self.assertEqual(authority["model_id"], "eleven_v3")

    def test_multiple_setups_on_fail_closed(self) -> None:
        workspace = _workspace()
        workspace.settings_json["tts_ai"]["profiles"][1]["enabled"] = True
        db = MagicMock()
        db.get.return_value = workspace

        with self.assertRaises(TtsPipelineError) as caught:
            bind_active_tts_profile_authority(db, workspace.id)

        self.assertEqual(caught.exception.code, TtsPipelineErrorCode.TTS_ACTIVE_SETUP_REQUIRED)
        self.assertIn("Multiple TTS setups are On", caught.exception.message)

    def test_saved_fallback_is_suppressed_for_production(self) -> None:
        workspace = _workspace(fallback="edge")
        db = MagicMock()
        db.get.return_value = workspace

        authority = bind_active_tts_profile_authority(db, workspace.id)
        config, _ = resolve_active_tts_profile_authority(
            db, workspace.id, authority
        )

        self.assertEqual(authority["fallback_provider"], "none")
        self.assertTrue(authority["configured_fallback_suppressed"])
        self.assertEqual(config.fallback_provider, "none")

    def test_provider_factory_strict_mode_never_builds_fallback(self) -> None:
        primary = SimpleNamespace(provider_name="edge")
        fallback = SimpleNamespace(provider_name="vieneu")
        cfg = TtsAiConfig(
            enabled=True,
            provider="edge",
            voice_id="vi-VN-HoaiMyNeural",
            fallback_provider="vieneu",
        )
        provider = build_default_tts_provider(
            workspace_tts=cfg,
            edge_provider_factory=lambda: primary,
            vieneu_provider_factory=lambda: fallback,
            allow_fallback=False,
        )
        self.assertIs(provider, primary)

    def test_queued_job_fails_if_active_setup_changes(self) -> None:
        workspace = _workspace()
        db = MagicMock()
        db.get.return_value = workspace
        authority = bind_active_tts_profile_authority(db, workspace.id)
        store = workspace.settings_json["tts_ai"]
        store["active_profile_id"] = "omnivoice"
        store["profiles"][0]["enabled"] = False
        store["profiles"][1]["enabled"] = True

        with self.assertRaises(TtsPipelineError) as caught:
            resolve_active_tts_profile_authority(db, workspace.id, authority)

        self.assertEqual(caught.exception.code, TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED)

    def test_client_voice_cannot_override_active_setup(self) -> None:
        service = TtsPipelineService(db=MagicMock())
        cfg = TtsAiConfig(
            enabled=True,
            provider="http_custom",
            model_id="eleven_v3",
            voice_id="active-voice",
            speaking_rate=1.15,
            language_code="vi",
            fallback_provider="none",
        )
        authority = {
            "schema_version": TTS_PROFILE_AUTHORITY_SCHEMA,
            "provider": "http_custom",
            "model_id": "eleven_v3",
            "voice_id": "active-voice",
        }
        request = TtsRequest(
            source_video_id=uuid4(),
            voice_config=VoiceConfig(voice_id="client-voice", speaking_rate=0.8),
            runtime_authority=authority,
        )
        with patch(
            "src.tts_pipeline.services.tts_service.resolve_active_tts_profile_authority",
            return_value=(cfg, authority),
        ):
            resolved = service._voice_config_for_request(request, uuid4())

        self.assertEqual(resolved.voice_id, "active-voice")
        self.assertEqual(resolved.speaking_rate, 1.15)

    def test_provider_output_cannot_switch_model_or_fallback(self) -> None:
        service = TtsPipelineService(db=MagicMock())
        service._runtime_tts_authority = {
            "provider": "http_custom",
            "model_id": "eleven_v3",
            "voice_id": "active-voice",
        }
        with self.assertRaises(TtsPipelineError):
            service._verified_provider_metadata(
                {
                    "provider": "omnivoice",
                    "model_id": "k2-fsa/OmniVoice",
                    "voice_id": "other",
                },
                [],
            )
        with self.assertRaises(TtsPipelineError):
            service._verified_provider_metadata(
                {
                    "provider": "http_custom",
                    "model_id": "eleven_v3",
                    "voice_id": "active-voice",
                    "fallback_used": True,
                },
                ["tts_used_fallback_provider"],
            )

    def test_active_job_from_another_setup_is_not_reusable(self) -> None:
        current = {
            "schema_version": TTS_PROFILE_AUTHORITY_SCHEMA,
            "workspace_id": str(uuid4()),
            "profile_id": "genmax",
            "provider": "http_custom",
            "model_id": "eleven_v3",
            "voice_id": "active-voice",
            "config_fingerprint": "a" * 64,
        }
        legacy = {
            **current,
            "profile_id": "omnivoice",
            "provider": "omnivoice",
            "config_fingerprint": "b" * 64,
        }
        self.assertTrue(_same_tts_authority(current, dict(current)))
        self.assertFalse(_same_tts_authority(legacy, current))

    def test_render_manifest_must_match_setup_still_on(self) -> None:
        workspace = _workspace()
        db = MagicMock()
        db.get.return_value = workspace
        authority = bind_active_tts_profile_authority(db, workspace.id)
        manifest = {
            "current_outputs": {"joined_narration": [{"storage_key": "joined.wav"}]},
            "provider_summary": {"tts_authority": authority},
        }
        current = assert_manifest_tts_authority_active(db, workspace.id, manifest)
        self.assertEqual(current["profile_id"], "genmax")

        workspace.settings_json["tts_ai"]["profiles"][0]["enabled"] = False
        with self.assertRaises(TtsPipelineError):
            assert_manifest_tts_authority_active(db, workspace.id, manifest)

    def test_verified_no_dialogue_manifest_does_not_require_tts_setup(self) -> None:
        workspace = _workspace(enabled=False)
        db = MagicMock()
        db.get.return_value = workspace
        manifest = {
            "current_outputs": {
                "joined_narration": [
                    {"role": "verified_no_dialogue_source_audio"}
                ]
            }
        }
        self.assertIsNone(
            assert_manifest_tts_authority_active(db, workspace.id, manifest)
        )


if __name__ == "__main__":
    unittest.main()
