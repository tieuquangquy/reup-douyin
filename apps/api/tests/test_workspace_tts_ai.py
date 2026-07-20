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
        active = next(
            p
            for p in workspace.settings_json[TTS_AI_KEY]["profiles"]
            if p["id"] == workspace.settings_json[TTS_AI_KEY]["active_profile_id"]
        )
        self.assertEqual(active["api_key"], "gcp-secret-abcdef12")
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
        active = next(
            p
            for p in workspace.settings_json[TTS_AI_KEY]["profiles"]
            if p["id"] == workspace.settings_json[TTS_AI_KEY]["active_profile_id"]
        )
        self.assertEqual(active["api_key"], "keep-me")
        self.assertEqual(active["voice_id"], "vi-VN-NamMinhNeural")

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
        active = next(
            p
            for p in workspace.settings_json[TTS_AI_KEY]["profiles"]
            if p["id"] == workspace.settings_json[TTS_AI_KEY]["active_profile_id"]
        )
        self.assertEqual(active["provider"], "my_tts_sdk")

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

    def test_factory_workspace_when_disabled(self) -> None:
        """Option A: active Ops profile builds provider even when Enabled is off."""
        cfg = SimpleNamespace(
            enabled=False,
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
        with patch("src.core.settings.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                audio_tts_provider="edge",
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
            provider = build_default_tts_provider(
                workspace_tts=cfg,
                edge_provider_factory=lambda: EdgeTtsProvider(
                    synthesize_audio=lambda **_: (b"RIFF", 0.1)
                ),
            )
        # Workspace placeholder must win; env edge must not.
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

    def test_probe_uses_draft_provider_when_workspace_disabled(self) -> None:
        """Ops Test must probe the draft form provider even when Enabled is off."""
        cfg = SimpleNamespace(
            enabled=False,
            provider="edge",
            api_key=None,
            base_url="",
            language_code="vi",
        )
        with patch("src.core.settings.get_settings") as get_settings:
            get_settings.return_value = SimpleNamespace(
                audio_tts_provider="placeholder",
                audio_tts_language_code="en",
                audio_tts_api_key=None,
                audio_tts_base_url="",
            )
            with patch.dict("sys.modules", {"edge_tts": MagicMock()}):
                with patch(
                    "src.tts_pipeline.provider_factory.discover_tts_catalog"
                ) as discover:
                    discover.return_value = MagicMock(
                        to_dict=lambda: {
                            "source": "sdk",
                            "voices": [],
                            "styles": [],
                            "models": [],
                            "default_voice_id": "",
                            "warning": "",
                        },
                        warning="",
                        source="sdk",
                    )
                    result = probe_tts_ai_client(cfg)
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "edge")
        self.assertNotEqual(result.provider, "placeholder")

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

    def test_probe_unknown_slug_fails(self) -> None:
        cfg = SimpleNamespace(
            enabled=True,
            provider="my_cloud",
            api_key=None,
            base_url="",
            language_code="vi",
            cli_binary="",
        )
        result = probe_tts_ai_client(cfg)
        self.assertFalse(result.ok)
        self.assertEqual(result.provider, "my_cloud")
        self.assertIn("unknown", result.detail.lower())

    def test_probe_cloud_requires_api_key(self) -> None:
        for name in ("google", "openai", "azure", "elevenlabs"):
            cfg = SimpleNamespace(
                enabled=True,
                provider=name,
                api_key=None,
                base_url="",
                language_code="vi",
                cli_binary="",
            )
            result = probe_tts_ai_client(cfg)
            self.assertFalse(result.ok, msg=f"{name} without key must fail")
            self.assertIn("api_key", result.detail.lower())

        cfg_ok = SimpleNamespace(
            enabled=True,
            provider="google",
            api_key="sk-test",
            base_url="",
            language_code="vi",
            cli_binary="",
        )
        result_ok = probe_tts_ai_client(cfg_ok)
        self.assertTrue(result_ok.ok)
        self.assertEqual(result_ok.provider, "google")

    def test_probe_http_requires_base_url(self) -> None:
        cfg_missing = SimpleNamespace(
            enabled=True,
            provider="http_custom",
            api_key=None,
            base_url="",
            language_code="vi",
            cli_binary="",
        )
        result_missing = probe_tts_ai_client(cfg_missing)
        self.assertFalse(result_missing.ok)
        self.assertIn("base_url", result_missing.detail.lower())

        cfg_ok = SimpleNamespace(
            enabled=True,
            provider="openai_compatible",
            api_key=None,
            base_url="https://example.com/v1",
            language_code="vi",
            cli_binary="",
        )
        result_ok = probe_tts_ai_client(cfg_ok)
        self.assertTrue(result_ok.ok)

    def test_probe_cli_requires_binary(self) -> None:
        cfg_missing = SimpleNamespace(
            enabled=True,
            provider="cli",
            api_key=None,
            base_url="",
            language_code="vi",
            cli_binary="",
        )
        result_missing = probe_tts_ai_client(cfg_missing)
        self.assertFalse(result_missing.ok)
        self.assertIn("cli_binary", result_missing.detail.lower())

        cfg_ok = SimpleNamespace(
            enabled=True,
            provider="cli",
            api_key=None,
            base_url="",
            language_code="vi",
            cli_binary="edge-tts",
        )
        result_ok = probe_tts_ai_client(cfg_ok)
        self.assertTrue(result_ok.ok)

    def _active_profile(self, workspace: SimpleNamespace) -> dict:
        store = workspace.settings_json[TTS_AI_KEY]
        active_id = store["active_profile_id"]
        return next(p for p in store["profiles"] if p["id"] == active_id)

    def test_legacy_flat_migrates_to_default_profile(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                TTS_AI_KEY: {
                    "enabled": True,
                    "provider": "vieneu",
                    "voice_id": "Phạm Tuyên",
                    "speaking_rate": 1.0,
                    "language_code": "vi",
                    "model_id": "",
                    "api_key": "legacy-key",
                    "base_url": "",
                    "timeout_seconds": 120.0,
                    "fallback_provider": "edge",
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
        cfg = service.get_tts_ai(workspace.id)
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.provider, "vieneu")
        self.assertEqual(cfg.api_key, "legacy-key")
        public = service.get_tts_ai_public(workspace.id)
        self.assertEqual(len(public["profiles"]), 1)
        self.assertEqual(public["profiles"][0]["name"], "Default")
        self.assertEqual(public["active_profile_id"], public["profiles"][0]["id"])
        self.assertEqual(public["active_profile_name"], "Default")
        summary = public["profiles"][0]
        self.assertEqual(summary["provider"], "vieneu")
        self.assertEqual(summary["voice_id"], "Phạm Tuyên")
        self.assertEqual(summary["language_code"], "vi")
        self.assertEqual(summary["speaking_rate"], 1.0)
        self.assertEqual(summary["fallback_provider"], "edge")
        self.assertTrue(summary["api_key_set"])
        self.assertEqual(summary["api_key_masked"], "••••-key")
        self.assertNotIn("api_key", summary)

    def test_create_profile_blank_keeps_active_and_old(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "vieneu",
                "voice_id": "Ngọc Linh",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "api_key": None,
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "none",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        old_active = self._active_profile(workspace)
        old_id = old_active["id"]
        created = service.create_tts_ai_profile(workspace.id, name="Cloud draft")
        self.assertEqual(created["name"], "Cloud draft")
        self.assertFalse(created.get("enabled", True))
        self.assertEqual(created.get("provider", "x"), "auto")
        store = workspace.settings_json[TTS_AI_KEY]
        self.assertEqual(len(store["profiles"]), 2)
        self.assertEqual(store["active_profile_id"], old_id)
        old = next(p for p in store["profiles"] if p["id"] == old_id)
        self.assertEqual(old["provider"], "vieneu")
        self.assertEqual(old["voice_id"], "Ngọc Linh")
        cfg = service.get_tts_ai(workspace.id)
        self.assertEqual(cfg.provider, "vieneu")
        self.assertTrue(cfg.enabled)

    def test_activate_switches_get_tts_ai(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "edge",
                "voice_id": "vi-VN-HoaiMyNeural",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "none",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        first_id = self._active_profile(workspace)["id"]
        service.create_tts_ai_profile(workspace.id, name="Blank B")
        second_id = next(p["id"] for p in workspace.settings_json[TTS_AI_KEY]["profiles"] if p["name"] == "Blank B")
        self.assertEqual(workspace.settings_json[TTS_AI_KEY]["active_profile_id"], first_id)
        service.activate_tts_ai_profile(workspace.id, second_id)
        self.assertEqual(workspace.settings_json[TTS_AI_KEY]["active_profile_id"], second_id)
        self.assertEqual(service.get_tts_ai(workspace.id).provider, "auto")
        service.activate_tts_ai_profile(workspace.id, first_id)
        self.assertEqual(service.get_tts_ai(workspace.id).provider, "edge")

    def test_rename_and_delete_profile(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "edge",
                "voice_id": "vi-VN-HoaiMyNeural",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "none",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        first_id = self._active_profile(workspace)["id"]
        created = service.create_tts_ai_profile(workspace.id, name="Temp")
        service.rename_tts_ai_profile(workspace.id, created["id"], name="Renamed")
        renamed = next(p for p in workspace.settings_json[TTS_AI_KEY]["profiles"] if p["id"] == created["id"])
        self.assertEqual(renamed["name"], "Renamed")
        service.delete_tts_ai_profile(workspace.id, created["id"])
        store = workspace.settings_json[TTS_AI_KEY]
        self.assertEqual(len(store["profiles"]), 1)
        self.assertEqual(store["active_profile_id"], first_id)
        with self.assertRaises(ValueError) as ctx:
            service.delete_tts_ai_profile(workspace.id, first_id)
        self.assertIn("last_profile", str(ctx.exception))

    def test_create_rejects_duplicate_name(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.create_tts_ai_profile(workspace.id, name="Alpha")
        with self.assertRaises(ValueError) as ctx:
            service.create_tts_ai_profile(workspace.id, name=" alpha ")
        self.assertIn("duplicate_name", str(ctx.exception))

    def test_set_writes_active_profile_only(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "vieneu",
                "voice_id": "A",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "none",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        first_id = self._active_profile(workspace)["id"]
        service.create_tts_ai_profile(workspace.id, name="Blank")
        # create must NOT steal active (overview controls active / on-off)
        self.assertEqual(workspace.settings_json[TTS_AI_KEY]["active_profile_id"], first_id)
        blank = next(p for p in workspace.settings_json[TTS_AI_KEY]["profiles"] if p["name"] == "Blank")
        service.set_tts_ai_profile(
            workspace.id,
            blank["id"],
            {
                "enabled": False,
                "provider": "edge",
                "voice_id": "vi-VN-HoaiMyNeural",
                "speaking_rate": 1.2,
                "language_code": "vi",
                "model_id": "",
                "base_url": "",
                "timeout_seconds": 90.0,
                "fallback_provider": "none",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        store = workspace.settings_json[TTS_AI_KEY]
        first = next(p for p in store["profiles"] if p["id"] == first_id)
        saved_blank = next(p for p in store["profiles"] if p["id"] == blank["id"])
        self.assertEqual(store["active_profile_id"], first_id)
        self.assertEqual(first["provider"], "vieneu")
        self.assertEqual(first["voice_id"], "A")
        self.assertEqual(saved_blank["provider"], "edge")
        self.assertEqual(saved_blank["voice_id"], "vi-VN-HoaiMyNeural")
        self.assertEqual(service.get_tts_ai(workspace.id).provider, "vieneu")

    def test_set_profile_enabled_does_not_change_active(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_tts_ai(
            workspace.id,
            {
                "enabled": False,
                "provider": "edge",
                "voice_id": "vi-VN-HoaiMyNeural",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "none",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        active_id = self._active_profile(workspace)["id"]
        created = service.create_tts_ai_profile(workspace.id, name="Other")
        service.set_tts_ai_profile_enabled(workspace.id, created["id"], enabled=True)
        store = workspace.settings_json[TTS_AI_KEY]
        self.assertEqual(store["active_profile_id"], active_id)
        other = next(p for p in store["profiles"] if p["id"] == created["id"])
        self.assertTrue(other["enabled"])
        self.assertFalse(service.get_tts_ai(workspace.id).enabled)

    def test_get_profile_public_returns_named_setup(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_tts_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "vieneu",
                "voice_id": "Ngọc Linh",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "none",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        created = service.create_tts_ai_profile(workspace.id, name="Draft")
        service.set_tts_ai_profile(
            workspace.id,
            created["id"],
            {
                "enabled": False,
                "provider": "edge",
                "voice_id": "vi-VN-NamMinhNeural",
                "speaking_rate": 1.0,
                "language_code": "vi",
                "model_id": "",
                "base_url": "",
                "timeout_seconds": 120.0,
                "fallback_provider": "none",
                "fallback_voice_id": "",
                "local_backend": "auto",
                "device": "auto",
                "cli_binary": "",
                "options_json": {},
            },
        )
        public = service.get_tts_ai_profile_public(workspace.id, created["id"])
        self.assertEqual(public["provider"], "edge")
        self.assertEqual(public["voice_id"], "vi-VN-NamMinhNeural")
        self.assertEqual(public["active_profile_name"], "Default")
        self.assertNotEqual(public["active_profile_id"], created["id"])


if __name__ == "__main__":
    unittest.main()
