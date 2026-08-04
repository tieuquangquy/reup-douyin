"""Full auto only works if a bad render is caught before it reaches review.

The gate is deliberately conservative: it never invents a verdict from data it does not
have, and only a hard defect (truncated video, missing dub, blocking risk) stops the item.
"""

from __future__ import annotations

import unittest

from src.services.render_qa_gate import (
    RenderQaMetrics,
    RenderQaStatus,
    evaluate_render_qa,
)


def _metrics(**overrides: object) -> RenderQaMetrics:
    base = {
        "source_duration_seconds": 30.0,
        "render_duration_seconds": 30.0,
        "render_width": 1080,
        "render_height": 1920,
        "audio_codec": "aac",
        "subtitle_burned": True,
        "dub_expected": True,
        "dub_audio_present": True,
        "risk_can_continue": True,
        "risk_highest_severity": "low",
        "render_warnings": [],
    }
    base.update(overrides)
    return RenderQaMetrics(**base)  # type: ignore[arg-type]


class EvaluateRenderQaTests(unittest.TestCase):
    def test_clean_render_passes(self) -> None:
        verdict = evaluate_render_qa(_metrics())

        self.assertEqual(verdict.status, RenderQaStatus.PASS)
        self.assertEqual(verdict.failed_checks, [])
        self.assertTrue(verdict.can_auto_finish)

    def test_truncated_render_fails(self) -> None:
        verdict = evaluate_render_qa(_metrics(render_duration_seconds=12.0))

        self.assertEqual(verdict.status, RenderQaStatus.FAIL)
        self.assertIn("duration_match", verdict.failed_checks)
        self.assertFalse(verdict.can_auto_finish)

    def test_small_duration_drift_only_warns(self) -> None:
        verdict = evaluate_render_qa(_metrics(render_duration_seconds=32.5))

        self.assertEqual(verdict.status, RenderQaStatus.WARN)
        self.assertTrue(verdict.can_auto_finish, "A warn still reaches review, flagged")

    def test_missing_dub_audio_fails_when_dubbing_expected(self) -> None:
        verdict = evaluate_render_qa(_metrics(audio_codec=None, dub_audio_present=False))

        self.assertEqual(verdict.status, RenderQaStatus.FAIL)
        self.assertIn("dub_audio", verdict.failed_checks)

    def test_silent_clip_without_dub_is_fine(self) -> None:
        verdict = evaluate_render_qa(
            _metrics(dub_expected=False, dub_audio_present=False, audio_codec=None)
        )

        self.assertEqual(verdict.status, RenderQaStatus.PASS)

    def test_blocking_risk_fails(self) -> None:
        verdict = evaluate_render_qa(_metrics(risk_can_continue=False, risk_highest_severity="high"))

        self.assertEqual(verdict.status, RenderQaStatus.FAIL)
        self.assertIn("risk_gate", verdict.failed_checks)

    def test_missing_subtitles_warn_only(self) -> None:
        verdict = evaluate_render_qa(_metrics(subtitle_burned=False))

        self.assertEqual(verdict.status, RenderQaStatus.WARN)
        self.assertIn("subtitle_burned", verdict.warned_checks)

    def test_render_warnings_warn(self) -> None:
        verdict = evaluate_render_qa(_metrics(render_warnings=["audio shorter than video"]))

        self.assertEqual(verdict.status, RenderQaStatus.WARN)
        self.assertIn("render_warnings", verdict.warned_checks)

    def test_unknown_metrics_are_skipped_not_failed(self) -> None:
        verdict = evaluate_render_qa(
            _metrics(
                source_duration_seconds=None,
                render_duration_seconds=None,
                render_width=None,
                render_height=None,
                risk_can_continue=None,
                risk_highest_severity=None,
                dub_audio_present=None,
            )
        )

        self.assertNotEqual(verdict.status, RenderQaStatus.FAIL)
        self.assertIn("duration_match", verdict.skipped_checks)

    def test_tiny_output_fails(self) -> None:
        verdict = evaluate_render_qa(_metrics(render_width=180, render_height=320))

        self.assertEqual(verdict.status, RenderQaStatus.FAIL)
        self.assertIn("resolution", verdict.failed_checks)

    def test_verdict_serialises_for_item_metadata(self) -> None:
        payload = evaluate_render_qa(_metrics(render_duration_seconds=12.0)).to_dict()

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(payload["summary"])
        self.assertTrue(any(check["key"] == "duration_match" for check in payload["checks"]))


if __name__ == "__main__":
    unittest.main()
