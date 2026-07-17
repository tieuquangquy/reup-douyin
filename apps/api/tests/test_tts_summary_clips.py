"""Contract: tts-summary exposes per-clip timing fit for Transcript Editor badges."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from src.enums import MediaAssetType
from src.tts_pipeline.services.tts_summary_clips import (
    build_timing_fit_summary,
    extract_tts_clip_fits,
    normalize_fit_status,
)
from src.tts_pipeline.types import TimingFitStatus


class TtsSummaryClipsTests(unittest.TestCase):
    def test_normalize_fit_status_accepts_str_enum_and_raw(self) -> None:
        self.assertEqual(normalize_fit_status(TimingFitStatus.TOO_LONG), "too_long")
        self.assertEqual(normalize_fit_status("slightly_long"), "slightly_long")
        self.assertEqual(normalize_fit_status("TimingFitStatus.FITS_WELL"), "fits_well")
        self.assertIsNone(normalize_fit_status(None))
        self.assertIsNone(normalize_fit_status("bogus"))

    def test_extract_tts_clip_fits_from_current_clip_metadata(self) -> None:
        translation_id = str(uuid4())
        clip = SimpleNamespace(
            id=uuid4(),
            asset_type=MediaAssetType.TTS_AUDIO_CLIP,
            is_current=True,
            metadata_json={
                "translation_segment_id": translation_id,
                "duration_seconds": 2.4,
                "fit_status": TimingFitStatus.SLIGHTLY_LONG,
                "fit_ratio": 1.12,
                "warnings": ["slightly_long"],
            },
        )
        joined = SimpleNamespace(
            id=uuid4(),
            asset_type=MediaAssetType.TTS_AUDIO_JOINED,
            is_current=True,
            metadata_json={"warnings": []},
        )
        stale = SimpleNamespace(
            id=uuid4(),
            asset_type=MediaAssetType.TTS_AUDIO_CLIP,
            is_current=False,
            metadata_json={
                "translation_segment_id": str(uuid4()),
                "fit_status": "too_long",
                "fit_ratio": 2.0,
                "warnings": ["too_long"],
            },
        )

        clips = extract_tts_clip_fits([stale, clip, joined])
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0]["translation_segment_id"], translation_id)
        self.assertEqual(clips[0]["fit_status"], "slightly_long")
        self.assertAlmostEqual(clips[0]["fit_ratio"], 1.12)
        self.assertEqual(clips[0]["warnings"], ["slightly_long"])
        self.assertAlmostEqual(clips[0]["duration_seconds"], 2.4)

        summary = build_timing_fit_summary(clips)
        self.assertEqual(summary["slightly_long"], 1)
        self.assertEqual(summary["fits_well"], 0)
        self.assertEqual(summary["too_long"], 0)
        self.assertEqual(summary["too_short"], 0)


if __name__ == "__main__":
    unittest.main()
