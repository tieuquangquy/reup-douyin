"""One declarative plan decides the next auto-pipeline hop.

The stop point comes from the pipeline mode and the dubbing steps are the only ones a
silent clip may skip: skipping dubbing must not also cancel hardsub cleanup and render.
"""

from __future__ import annotations

import unittest

from src.services.reup_pipeline_meta import (
    PIPELINE_MODE_AUTO_TO_RENDER,
    PIPELINE_MODE_AUTO_TO_TTS,
    PIPELINE_MODE_MANUAL,
    PIPELINE_STEP_ANALYZE_AUDIO,
    PIPELINE_STEP_DOWNLOAD,
    PIPELINE_STEP_OCR,
    PIPELINE_STEP_RENDER,
    PIPELINE_STEP_TRANSLATE,
    PIPELINE_STEP_TTS,
)
from src.services.reup_pipeline_plan import (
    PIPELINE_STEP_ORDER,
    auto_last_step,
    next_pipeline_step,
)


class PipelinePlanShapeTests(unittest.TestCase):
    def test_step_order_matches_production_flow(self) -> None:
        self.assertEqual(
            PIPELINE_STEP_ORDER,
            (
                PIPELINE_STEP_DOWNLOAD,
                PIPELINE_STEP_ANALYZE_AUDIO,
                PIPELINE_STEP_TRANSLATE,
                PIPELINE_STEP_TTS,
                PIPELINE_STEP_OCR,
                PIPELINE_STEP_RENDER,
            ),
        )

    def test_auto_last_step_per_mode(self) -> None:
        self.assertEqual(auto_last_step(PIPELINE_MODE_AUTO_TO_TTS), PIPELINE_STEP_TTS)
        self.assertEqual(auto_last_step(PIPELINE_MODE_AUTO_TO_RENDER), PIPELINE_STEP_RENDER)
        self.assertIsNone(auto_last_step(PIPELINE_MODE_MANUAL))


class NextPipelineStepTests(unittest.TestCase):
    def test_fresh_item_starts_with_download(self) -> None:
        self.assertEqual(
            next_pipeline_step(current_step=None, mode=PIPELINE_MODE_AUTO_TO_TTS, skip_dubbing=False),
            PIPELINE_STEP_DOWNLOAD,
        )

    def test_talking_clip_walks_the_full_chain(self) -> None:
        chain = []
        step: str | None = None
        for _ in range(len(PIPELINE_STEP_ORDER) + 1):
            step = next_pipeline_step(
                current_step=step, mode=PIPELINE_MODE_AUTO_TO_RENDER, skip_dubbing=False
            )
            if step is None:
                break
            chain.append(step)
        self.assertEqual(chain, list(PIPELINE_STEP_ORDER))

    def test_silent_clip_still_reaches_render(self) -> None:
        """A clip with no speech usually still carries burned-in Chinese text."""
        self.assertEqual(
            next_pipeline_step(
                current_step=PIPELINE_STEP_ANALYZE_AUDIO,
                mode=PIPELINE_MODE_AUTO_TO_RENDER,
                skip_dubbing=True,
            ),
            PIPELINE_STEP_OCR,
        )

    def test_silent_clip_stops_when_mode_stops_at_tts(self) -> None:
        self.assertIsNone(
            next_pipeline_step(
                current_step=PIPELINE_STEP_ANALYZE_AUDIO,
                mode=PIPELINE_MODE_AUTO_TO_TTS,
                skip_dubbing=True,
            )
        )

    def test_stop_point_is_respected_after_tts(self) -> None:
        self.assertIsNone(
            next_pipeline_step(
                current_step=PIPELINE_STEP_TTS, mode=PIPELINE_MODE_AUTO_TO_TTS, skip_dubbing=False
            )
        )
        self.assertEqual(
            next_pipeline_step(
                current_step=PIPELINE_STEP_TTS, mode=PIPELINE_MODE_AUTO_TO_RENDER, skip_dubbing=False
            ),
            PIPELINE_STEP_OCR,
        )

    def test_render_is_the_end_of_the_plan(self) -> None:
        self.assertIsNone(
            next_pipeline_step(
                current_step=PIPELINE_STEP_RENDER, mode=PIPELINE_MODE_AUTO_TO_RENDER, skip_dubbing=False
            )
        )

    def test_manual_mode_never_advances(self) -> None:
        for step in (None, PIPELINE_STEP_DOWNLOAD, PIPELINE_STEP_ANALYZE_AUDIO, PIPELINE_STEP_TTS):
            self.assertIsNone(
                next_pipeline_step(current_step=step, mode=PIPELINE_MODE_MANUAL, skip_dubbing=False),
                f"manual item must not auto-advance from {step}",
            )

    def test_unknown_step_does_not_advance(self) -> None:
        self.assertIsNone(
            next_pipeline_step(
                current_step="ready_final", mode=PIPELINE_MODE_AUTO_TO_RENDER, skip_dubbing=False
            )
        )
        self.assertIsNone(
            next_pipeline_step(
                current_step="needs_attention", mode=PIPELINE_MODE_AUTO_TO_RENDER, skip_dubbing=False
            )
        )


if __name__ == "__main__":
    unittest.main()
