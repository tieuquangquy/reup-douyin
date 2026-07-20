"""TTS Ops catalog discovery (voices/styles/models) for Test Connection."""

from __future__ import annotations

import unittest

from src.tts_pipeline.catalog import discover_tts_catalog


class TtsCatalogTests(unittest.TestCase):
    def test_vieneu_uses_sdk_voice_list(self) -> None:
        catalog = discover_tts_catalog(
            "vieneu",
            vieneu_list_voices=lambda: [("Phạm Tuyên", "Phạm Tuyên"), ("Trúc Ly", "Trúc Ly")],
        )
        self.assertEqual(catalog.source, "sdk")
        self.assertEqual(len(catalog.voices), 2)
        self.assertEqual(catalog.voices[0].id, "Phạm Tuyên")
        self.assertIn("tu_nhien", catalog.styles)
        self.assertIn("v3turbo", catalog.models)
        self.assertEqual(catalog.sample_rate, 48000)
        self.assertIn("remote", catalog.backends)
        payload = catalog.to_dict()
        self.assertEqual(payload["voices"][1]["label"], "Trúc Ly")
        self.assertEqual(payload["sample_rate"], 48000)

    def test_vieneu_falls_back_to_curated_when_sdk_raises(self) -> None:
        def boom() -> list[tuple[str, str]]:
            raise RuntimeError("model download blocked")

        catalog = discover_tts_catalog("vieneu", vieneu_list_voices=boom)
        self.assertEqual(catalog.source, "curated")
        self.assertGreaterEqual(len(catalog.voices), 1)
        self.assertIn("unavailable", catalog.warning.lower())

    def test_edge_filters_vietnamese_voices(self) -> None:
        catalog = discover_tts_catalog(
            "edge",
            language_code="vi",
            edge_list_voices=lambda: [
                {"ShortName": "vi-VN-HoaiMyNeural", "Locale": "vi-VN", "FriendlyName": "HoaiMy"},
                {"ShortName": "en-US-JennyNeural", "Locale": "en-US", "FriendlyName": "Jenny"},
                {"ShortName": "vi-VN-NamMinhNeural", "Locale": "vi-VN", "FriendlyName": "NamMinh"},
            ],
        )
        self.assertEqual(catalog.source, "sdk")
        ids = [v.id for v in catalog.voices]
        self.assertEqual(ids, ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"])
        self.assertEqual(catalog.default_voice_id, "vi-VN-HoaiMyNeural")

    def test_unknown_provider_returns_empty(self) -> None:
        catalog = discover_tts_catalog("google")
        self.assertEqual(catalog.source, "none")
        self.assertEqual(catalog.voices, [])
        payload = catalog.to_dict()
        self.assertIn("capabilities", payload)
        self.assertTrue(payload["capabilities"]["voice"])
        self.assertTrue(payload["capabilities"]["model"])
        self.assertTrue(payload["capabilities"]["api_key"])

    def test_edge_catalog_includes_capabilities(self) -> None:
        catalog = discover_tts_catalog(
            "edge",
            language_code="vi",
            edge_list_voices=lambda: [
                {"ShortName": "vi-VN-HoaiMyNeural", "Locale": "vi-VN", "FriendlyName": "HoaiMy"},
            ],
        )
        caps = catalog.to_dict()["capabilities"]
        self.assertTrue(caps["voice"])
        self.assertFalse(caps["model"])

    def test_omnivoice_curated_catalog(self) -> None:
        catalog = discover_tts_catalog("omnivoice")
        self.assertEqual(catalog.source, "curated")
        self.assertGreaterEqual(len(catalog.models), 12)
        self.assertIn("omnivoice", catalog.models)
        self.assertIn("cosyvoice", catalog.models)
        self.assertIn("kittentts", catalog.models)
        self.assertGreaterEqual(len(catalog.voices), 10)
        ids = [v.id for v in catalog.voices]
        self.assertIn("auto", ids)
        self.assertIn("alloy", ids)
        self.assertTrue(any(v.id.startswith("instruct:vi_") for v in catalog.voices))
        self.assertEqual(catalog.default_voice_id, "auto")
        caps = catalog.to_dict()["capabilities"]
        self.assertTrue(caps["voice"])
        self.assertTrue(caps["model"])


if __name__ == "__main__":
    unittest.main()
