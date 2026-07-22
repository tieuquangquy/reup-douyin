"""Best OCR profile must use Authority V3.6 full-timeline in the production E2E path."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.media_pipeline.hardsub_e2e import run_hardsub_phases_1_to_4


class HardsubE2EV3WiringTests(unittest.TestCase):
    def test_best_profile_uses_v3_and_force_refresh_invalidates_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            output = root / "cleaned.mp4"
            sample = root / "sample.jpg"
            sample.write_bytes(b"jpeg")
            cache = root / "cache.json"
            cache.write_text("stale", encoding="utf-8")
            payload = {
                "authority": "ocr_authority_v3.6",
                "endcard_mode": "text_only",
                "frame_count": 694,
                "frames": [
                    {
                        "frame_index": index,
                        "time_ms": index * 40,
                        "boxes": (
                            [
                                {
                                    "x": 0.3,
                                    "y": 0.9,
                                    "w": 0.4,
                                    "h": 0.05,
                                    "text": "字幕",
                                    "confidence": 0.99,
                                }
                            ]
                            if index % 10 == 0
                            else []
                        ),
                    }
                    for index in range(694)
                ],
            }

            def fake_v3(*_args, **kwargs):
                self.assertFalse(cache.exists())
                self.assertEqual(kwargs["ocr_cache_path"], cache)
                out_json = Path(kwargs["out_json"])
                self.assertEqual(out_json.name, "ocr-authority-v3.6.json")
                # Full-timeline path: do not pass Phase-1 sample limiting knobs.
                self.assertNotIn("overlay_indices", kwargs)
                self.assertNotIn("positions_json", kwargs)
                self.assertTrue(
                    kwargs.get("frame_stride") is None
                    or int(kwargs.get("frame_stride") or 1) == 1
                )
                return payload

            with (
                patch(
                    "src.media_pipeline.hardsub_e2e.extract_phase1_frames",
                    return_value=[SimpleNamespace(path=sample, time_ms=0)],
                ),
                patch(
                    "src.media_pipeline.ocr_filtering.ocr_quality_profile.is_best_ocr_profile",
                    return_value=True,
                ),
                patch(
                    "src.media_pipeline.ocr_filtering.per_frame_position_authority.run_per_frame_position_authority",
                    side_effect=fake_v3,
                ) as run_v3,
                patch(
                    "src.media_pipeline.hardsub_e2e.build_default_ocr_provider"
                ) as legacy_provider,
                patch(
                    "src.media_pipeline.hardsub_e2e.translate_subtitles",
                    return_value={"0#0": "Phu de"},
                ),
                patch(
                    "src.media_pipeline.translator.resolve.resolve_translator_settings",
                    return_value=SimpleNamespace(source="test"),
                ),
                patch(
                    "src.media_pipeline.hardsub_e2e.render_video_single_pass",
                    return_value=output,
                ),
            ):
                result = run_hardsub_phases_1_to_4(
                    source,
                    output,
                    ocr_cache_path=cache,
                    force_refresh=True,
                )

        run_v3.assert_called_once()
        legacy_provider.assert_not_called()
        self.assertEqual(result.ocr_payload["authority"], "ocr_authority_v3.6")
        self.assertEqual(result.ocr_provider_name, "ocr_authority_v3.6")
        self.assertEqual(int(result.ocr_payload["frame_count"]), 694)
        self.assertEqual(len(result.ocr_payload["frames"]), 694)


if __name__ == "__main__":
    unittest.main()
