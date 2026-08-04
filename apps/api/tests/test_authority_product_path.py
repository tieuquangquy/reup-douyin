"""Product path: dense authority → translate → cover+VI (not sparse SKE hold)."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.media_pipeline.video_renderer.overlays import (
    is_artifact_vi_text,
    overlays_from_ocr_payload,
)


class PlaceholderViTests(unittest.TestCase):
    def test_ellipsis_and_dry_prefix_are_artifacts(self) -> None:
        self.assertTrue(is_artifact_vi_text("..."))
        self.assertTrue(is_artifact_vi_text("[vi]花"))
        self.assertFalse(is_artifact_vi_text("Thêm muối"))

    def test_overlays_clear_placeholder_vi_but_keep_cover_box(self) -> None:
        payload = {
            "frames": [
                {
                    "frame_index": 0,
                    "time_ms": 2500,
                    "boxes": [
                        {
                            "x": 0.2,
                            "y": 0.5,
                            "w": 0.2,
                            "h": 0.05,
                            "text": "加盐",
                            "confidence": 0.9,
                        }
                    ],
                },
                {
                    "frame_index": 1,
                    "time_ms": 4500,
                    "boxes": [
                        {
                            "x": 0.2,
                            "y": 0.5,
                            "w": 0.2,
                            "h": 0.05,
                            "text": "花",
                            "confidence": 0.9,
                        }
                    ],
                },
            ]
        }
        overlays = overlays_from_ocr_payload(
            payload,
            {"2500#0": "...", "4500#0": "Bông cải"},
            hold_ms=500,
        )
        first = next(o for o in overlays if o.start_ms == 2500)
        self.assertEqual(first.text_vi, "")
        self.assertEqual(first.end_ms, 4500)
        second = next(o for o in overlays if o.start_ms == 4500)
        self.assertEqual(second.text_vi, "Bông cải")


class TranslateSubtitlesDryTests(unittest.TestCase):
    def test_dry_env_returns_map_without_live_llm(self) -> None:
        from src.media_pipeline.translator.service import translate_subtitles

        payload = {
            "frames": [
                {
                    "time_ms": 2000,
                    "boxes": [
                        {
                            "x": 0.1,
                            "y": 0.5,
                            "w": 0.2,
                            "h": 0.05,
                            "text": "加盐",
                            "confidence": 0.99,
                        }
                    ],
                }
            ]
        }
        with patch.dict(os.environ, {"TRANSLATE_LLM_DRY": "1"}, clear=False):
            vi = translate_subtitles(payload)
        self.assertIn("2000#0", vi)
        self.assertEqual(vi["2000#0"], "Thêm muối")
        self.assertNotIn("[vi]", vi["2000#0"])


class E2EScriptUsesAuthorityPathTests(unittest.TestCase):
    def test_script_calls_hardsub_production_not_ske_cleaner(self) -> None:
        import tempfile

        path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "run_e2e_steps_1_to_4.py"
        )
        spec = importlib.util.spec_from_file_location("e2e_steps_1_to_4", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertTrue(hasattr(mod, "run_product_authority_e2e"))
        dummy_video = Path(__file__).resolve().parents[1] / "scripts" / "run_e2e_steps_1_to_4.py"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            fake_out = out / "final_complete.mp4"
            fake_out.write_bytes(b"mp4")
            fake_result = SimpleNamespace(
                output_path=str(fake_out),
                ocr_payload={"authority": "ocr_authority_v3.6", "frames": []},
                vi_texts={"0#0": "ok"},
                ocr_provider_name="ocr_authority_v3.6",
                caption_ai_source="dry",
                frame_count=1,
                sample_fps=25.0,
            )
            with (
                patch.object(mod, "run_hardsub_phases_1_to_4", return_value=fake_result) as hardsub,
                patch.dict(os.environ, {"OCR_QUALITY_PROFILE": "best", "TRANSLATE_LLM_DRY": "1"}),
            ):
                code = mod.run_product_authority_e2e(video=dummy_video, out_dir=out)
            self.assertEqual(code, 0)
            hardsub.assert_called_once()
            self.assertTrue((out / "ocr_authority.json").is_file())
            self.assertTrue((out / "vi_texts.json").is_file())


if __name__ == "__main__":
    unittest.main()
