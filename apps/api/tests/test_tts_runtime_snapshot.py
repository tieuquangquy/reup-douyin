"""TTS Ops runtime snapshot persistence."""

from __future__ import annotations

import unittest

from src.tts_pipeline.runtime_snapshot import (
    build_last_install,
    build_last_probe,
    detect_already_satisfied,
    merge_runtime,
    normalize_runtime,
)


class TtsRuntimeSnapshotTests(unittest.TestCase):
    def test_merge_preserves_install_when_updating_probe(self) -> None:
        existing = {
            "last_install": {"at": "2026-01-01T00:00:00Z", "ok": True, "command": "pip install vieneu"},
            "last_probe": None,
        }
        probe = build_last_probe(
            ok=True,
            provider="vieneu",
            detail="ready",
            catalog={"source": "sdk", "voices": [{"id": "A", "label": "A"}]},
        )
        merged = merge_runtime(existing, last_probe=probe)
        self.assertEqual(merged["last_install"]["command"], "pip install vieneu")
        self.assertTrue(merged["last_probe"]["ok"])
        self.assertEqual(merged["last_probe"]["catalog"]["source"], "sdk")

    def test_detect_already_satisfied(self) -> None:
        self.assertTrue(
            detect_already_satisfied(
                "Requirement already satisfied: vieneu in c:\\python\\lib\\site-packages"
            )
        )
        self.assertFalse(detect_already_satisfied("Successfully installed vieneu-0.0.4"))

    def test_normalize_empty(self) -> None:
        self.assertEqual(normalize_runtime(None), {"last_install": None, "last_probe": None})

    def test_build_last_install_flags_reinstall(self) -> None:
        row = build_last_install(
            ok=True,
            command="pip install vieneu",
            package="vieneu",
            detail="ok",
            already_satisfied=True,
        )
        self.assertTrue(row["already_satisfied"])
        self.assertEqual(row["package"], "vieneu")


if __name__ == "__main__":
    unittest.main()
