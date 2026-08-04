from __future__ import annotations

import hashlib
import json
import unittest
from types import SimpleNamespace

from src.services.pipeline_recipe import (
    PIPELINE_RECIPE_SCHEMA,
    build_pipeline_recipe,
    recipe_fingerprint,
    stamp_pipeline_recipe,
)
from src.services.reup_pipeline_meta import PIPELINE_RECIPE_KEY, meta_dict


class PipelineRecipeUnitTests(unittest.TestCase):
    def test_same_inputs_yield_same_fingerprint(self) -> None:
        settings = SimpleNamespace(
            render_loudness_normalization_enabled=True,
            render_loudness_target_lufs=-14.0,
            audio_tts_provider="edge",
            audio_tts_voice_id="vi-VN-HoaiMyNeural",
            audio_tts_speaking_rate=1.0,
            audio_tts_model_id="",
            audio_tts_fallback_provider="none",
        )
        left = build_pipeline_recipe(
            settings=settings,
            pipeline_mode="auto_to_render",
            skip_dubbing=False,
        )
        right = build_pipeline_recipe(
            settings=settings,
            pipeline_mode="auto_to_render",
            skip_dubbing=False,
        )
        self.assertEqual(left["fingerprint"], right["fingerprint"])
        self.assertEqual(left["schema"], PIPELINE_RECIPE_SCHEMA)
        self.assertFalse(
            left["recipe"]["phase1"]["authority_v3_6_full_duration"]
        )
        self.assertEqual(
            left["recipe"]["phase1"]["extractor_version"], "v58_candidate"
        )
        self.assertEqual(
            left["recipe"]["phase1"]["final_coverage_fade_tail_max_frames"],
            5,
        )

    def test_quality_knob_change_changes_fingerprint(self) -> None:
        base = SimpleNamespace(
            render_loudness_normalization_enabled=True,
            render_loudness_target_lufs=-14.0,
            audio_tts_provider="edge",
            audio_tts_voice_id="vi-VN-HoaiMyNeural",
            audio_tts_speaking_rate=1.0,
            audio_tts_model_id="",
            audio_tts_fallback_provider="none",
        )
        quiet = SimpleNamespace(**{**base.__dict__, "render_loudness_target_lufs": -16.0})
        a = recipe_fingerprint(build_pipeline_recipe(settings=base, pipeline_mode="auto_to_render", skip_dubbing=False)["recipe"])
        b = recipe_fingerprint(build_pipeline_recipe(settings=quiet, pipeline_mode="auto_to_render", skip_dubbing=False)["recipe"])
        self.assertNotEqual(a, b)

    def test_fingerprint_is_stable_hex_prefix(self) -> None:
        recipe = {"a": 1, "b": "x"}
        digest = hashlib.sha256(
            json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        self.assertEqual(recipe_fingerprint(recipe), digest[:16])

    def test_stamp_writes_onto_item_metadata(self) -> None:
        item = SimpleNamespace(
            metadata_json={"pipeline_mode": "auto_to_render", "pipeline_step": "render"},
        )
        settings = SimpleNamespace(
            render_loudness_normalization_enabled=True,
            render_loudness_target_lufs=-14.0,
            audio_tts_provider="edge",
            audio_tts_voice_id="vi-VN-HoaiMyNeural",
            audio_tts_speaking_rate=1.0,
            audio_tts_model_id="",
            audio_tts_fallback_provider="none",
        )
        stamped = stamp_pipeline_recipe(
            item,
            settings=settings,
            pipeline_mode="auto_to_render",
            skip_dubbing=True,
        )
        meta = meta_dict(item)
        self.assertIn(PIPELINE_RECIPE_KEY, meta)
        self.assertEqual(meta[PIPELINE_RECIPE_KEY]["fingerprint"], stamped["fingerprint"])
        self.assertTrue(meta[PIPELINE_RECIPE_KEY]["recipe"]["skip_dubbing"])
        # Existing pipeline keys must survive the stamp.
        self.assertEqual(meta["pipeline_mode"], "auto_to_render")
        self.assertEqual(meta["pipeline_step"], "render")


class PipelineRecipeOrchestratorContractTests(unittest.TestCase):
    def test_orchestrator_stamps_recipe_when_render_completes(self) -> None:
        import inspect

        from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator

        source = inspect.getsource(ReupPipelineOrchestrator._advance_after_success)
        self.assertIn(
            "stamp_pipeline_recipe",
            source,
            "Render completion must stamp the recipe next to the QA verdict — "
            "that is the only moment every finished product passes through",
        )


if __name__ == "__main__":
    unittest.main()
