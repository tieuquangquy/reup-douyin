"""Workspace DB-backed TTS AI settings + factory resolution."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.services.workspace_settings_service import TTS_AI_KEY, WorkspaceSettingsService
from src.tts_pipeline.edge_tts_provider import EdgeTtsProvider
from src.tts_pipeline.provider_factory import build_default_tts_provider, probe_tts_ai_client
from src.tts_pipeline.providers import PlaceholderToneTtsProvider


class WorkspaceTtsAiTests(unittest.TestCase):
    def test_get_returns_disabled_when_unset(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json=None)
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        cfg = service.get_tts_ai(workspace.id)
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.provider, "auto")
        self.assertIsNone(cfg.api_key)

    def test_set_masks_api_key_on_public_view(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        saved = service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "google",
                "voice_id": "vi-VN-Neural2-A",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "api_key": "gcp-secret-abcdef12",
                "base_url": "",
                "timeout_seconds": 120,
                "fallback_provider": "edge",
                "fallback_voice_id": "vi-VN-HoaiMyNeural",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        self.assertTrue(saved.enabled)
        self.assertEqual(workspace.settings_json[TTS_AI_KEY]["api_key"], "gcp-secret-abcdef12")
        public = service.get_tts_ai_public(workspace.id)
        self.assertTrue(public["api_key_set"])
        self.assertNotIn("gcp-secret", public["api_key_masked"])
        self.assertTrue(public["api_key_masked"].endswith("ef12"))
        self.assertNotIn("api_key", public)
        self.assertEqual(public["fallback_provider"], "edge")

    def test_put_keeps_existing_key_when_api_key_omitted(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                TTS_AI_KEY: {
                    "enabled": True,
                    "provider": "azure",
                    "voice_id": "vi-VN-HoaiMyNeural",
                    "speaking_rate": 1.0,
                    "language_code": "vi",
                    "model_id": "",
                    "api_key": "keep-me",
                    "base_url": "https://eastus.api.cognitive.microsoft.com",
                    "timeout_seconds": 120,
                    "fallback_provider": "none",
                    "fallback_voice_id": "",
                    "local_backend": "auto",
                    "device": "auto",
                    "cli_binary": "",
                    "options_json": {},
                }
            },
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "azure",
                "voice_id": "vi-VN-NamMinhNeural",
                "speaking_rate": 1.1,
                "language_code": "vi",
                "model_id": "",
                "base_url": "https://eastus.api.cognitive.microsoft.com",
                "timeout_seconds": 90,
                "fallback_provider": "edge",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
            keep_existing_api_key=True,
        )
        self.assertEqual(workspace.settings_json[TTS_AI_KEY]["api_key"], "keep-me")
        self.assertEqual(workspace.settings_json[TTS_AI_KEY]["voice_id"], "vi-VN-NamMinhNeural")

    def test_rejects_invalid_provider(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        with self.assertRaises(ValueError) as ctx:
            service.set_tts_ai(workspace.id, {"enabled": True, "provider": "Bad Name!"})
        self.assertIn("invalid_provider", str(ctx.exception))

    def test_allows_custom_local_provider_slug(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        saved = service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "my_tts_sdk",
                "voice_id": "",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "api_key": None,
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "edge",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {"package_name": "some-tts"},
            },
            keep_existing_api_key=False,
        )
        self.assertEqual(saved.provider, "my_tts_sdk")
        self.assertEqual(workspace.settings_json[TTS_AI_KEY]["provider"], "my_tts_sdk")

    def test_factory_workspace_placeholder_when_enabled(self) -> None:
        cfg = SimpleNamespace(
            enabled=True,
            provider="placeholder",
            voice_id="",
            speaking_rate=1.0,
            language_code="vi",
            model_id="",
            api_key=None,
            base_url="",
            timeout_seconds=120.0,
            fallback_provider="none",
            fallback_voice_id="",
            local_backend="auto",
            device="auto",
            cli_binary="",
            options_json={},
        )
        provider = build_default_tts_provider(workspace_tts=cfg)
        self.assertIsInstance(provider, PlaceholderToneTtsProvider)

    def test_factory_workspace_edge_when_enabled(self) -> None:
        cfg = SimpleNamespace(
            enabled=True,
            provider="edge",
            voice_id="vi-VN-HoaiMyNeural",
            speaking_rate=1.0,
            language_code="vi",
            model_id="",
            api_key=None,
            base_url="",
            timeout_seconds=120.0,
            fallback_provider="none",
            fallback_voice_id="",
            local_backend="auto",
            device="auto",
            cli_binary="",
            options_json={},
        )
        provider = build_default_tts_provider(
            workspace_tts=cfg,
            edge_provider_factory=lambda: EdgeTtsProvider(synthesize_audio=lambda **_: (b"RIFF", 0.1)),
        )
        self.assertIsInstance(provider, EdgeTtsProvider)

    def test_factory_env_when_workspace_disabled(self) -> None:
        cfg = SimpleNamespace(enabled=False, provider="vieneu")
        with patch("src.core.settings.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                audio_tts_provider="placeholder",
                audio_tts_voice_id="vi-VN-HoaiMyNeural",
                audio_tts_speaking_rate=1.0,
                audio_tts_api_key=None,
                audio_tts_base_url="",
                audio_tts_model_id="",
                audio_tts_fallback_provider="none",
                audio_tts_fallback_voice_id="",
                audio_tts_local_backend="auto",
                audio_tts_device="auto",
                audio_tts_cli_binary="",
                audio_tts_timeout_seconds=120.0,
            )
            provider = build_default_tts_provider(workspace_tts=cfg)
        self.assertIsInstance(provider, PlaceholderToneTtsProvider)

    def test_probe_edge_reports_ok_when_importable(self) -> None:
        cfg = SimpleNamespace(
            enabled=True,
            provider="edge",
            api_key=None,
            base_url="",
            model_id="",
            language_code="vi",
            local_backend="auto",
            device="auto",
            cli_binary="",
        )
        with patch.dict("sys.modules", {"edge_tts": MagicMock()}):
            with patch(
                "src.tts_pipeline.provider_factory.discover_tts_catalog"
            ) as discover:
                discover.return_value = MagicMock(
                    to_dict=lambda: {
                        "source": "sdk",
                        "voices": [{"id": "vi-VN-HoaiMyNeural", "label": "HoaiMy"}],
                        "styles": [],
                        "models": [],
                        "default_voice_id": "vi-VN-HoaiMyNeural",
                        "warning": "",
                    },
                    warning="",
                    source="sdk",
                )
                result = probe_tts_ai_client(cfg)
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "edge")
        self.assertIn("ready", result.detail.lower())
        self.assertIsNotNone(result.catalog)
        self.assertEqual(result.catalog["source"], "sdk")
        self.assertEqual(result.catalog["voices"][0]["id"], "vi-VN-HoaiMyNeural")

    def test_save_preserves_runtime_snapshot(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                TTS_AI_KEY: {
                    "enabled": True,
                    "provider": "vieneu",
                    "voice_id": "Phạm Tuyên",
                    "speaking_rate": 1.0,
                    "language_code": "vi",
                    "model_id": "v3turbo",
                    "api_key": "",
                    "base_url": "",
                    "timeout_seconds": 120.0,
                    "fallback_provider": "edge",
                    "fallback_voice_id": "",
                    "local_backend": "auto",
                    "device": "auto",
                    "cli_binary": "",
                    "options_json": {},
                    "runtime": {
                        "last_install": {
                            "at": "2026-07-16T00:00:00Z",
                            "ok": True,
                            "command": "pip install vieneu",
                            "package": "vieneu",
                            "detail": "ok",
                            "already_satisfied": False,
                        },
                        "last_probe": {
                            "at": "2026-07-16T00:00:01Z",
                            "ok": True,
                            "provider": "vieneu",
                            "detail": "ready",
                            "catalog": {"source": "sdk", "voices": [{"id": "A", "label": "A"}]},
                        },
                    },
                }
            },
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        saved = service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "vieneu",
                "voice_id": "Trúc Ly",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "v3turbo",
                "api_key": None,
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "edge",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {"install_command": "pip install vieneu"},
            },
            keep_existing_api_key=True,
        )
        self.assertEqual(saved.voice_id, "Trúc Ly")
        self.assertEqual(saved.runtime["last_install"]["package"], "vieneu")
        self.assertEqual(saved.runtime["last_probe"]["catalog"]["source"], "sdk")
        public = service.get_tts_ai_public(workspace.id)
        self.assertEqual(public["runtime"]["last_install"]["command"], "pip install vieneu")

    def test_patch_tts_ai_runtime_merges(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        runtime = service.patch_tts_ai_runtime(
            workspace.id,
            last_install={
                "at": "2026-07-16T00:00:00Z",
                "ok": True,
                "command": "pip install edge-tts",
                "package": "edge-tts",
                "detail": "ok",
                "already_satisfied": True,
            },
        )
        self.assertTrue(runtime["last_install"]["already_satisfied"])
        runtime2 = service.patch_tts_ai_runtime(
            workspace.id,
            last_probe={
                "at": "2026-07-16T00:00:01Z",
                "ok": True,
                "provider": "edge",
                "detail": "ready",
                "catalog": {"source": "curated", "voices": []},
            },
        )
        self.assertEqual(runtime2["last_install"]["package"], "edge-tts")
        self.assertEqual(runtime2["last_probe"]["provider"], "edge")

    def test_probe_not_installed_has_no_catalog(self) -> None:
        from src.tts_pipeline.provider_factory import TtsProbeResult

        cfg = SimpleNamespace(enabled=True, provider="vieneu", language_code="vi")
        with patch(
            "src.tts_pipeline.provider_factory._probe_named",
            return_value=TtsProbeResult(False, "vieneu", "vieneu not installed. Run: pip install vieneu"),
        ):
            result = probe_tts_ai_client(cfg)
        self.assertFalse(result.ok)
        self.assertIsNone(result.catalog)


if __name__ == "__main__":
    unittest.main()
