"""Transient pipeline failures must retry themselves before an operator is paged.

Full-auto only stays hands-off if a flaky provider call or a locked file recovers on its
own, while a deterministic bug stops immediately instead of burning render minutes.
"""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from src.services.pipeline_retry_policy import (
    PipelineFailureClass,
    classify_pipeline_failure,
    next_pipeline_retry_at,
    pipeline_failure_operator_message,
    should_auto_retry_pipeline_failure,
)


class ClassifyTests(unittest.TestCase):
    def test_phase4_contract_input_failure_is_terminal(self) -> None:
        self.assertEqual(
            classify_pipeline_failure(
                "PHASE4_INPUT_INVALID",
                "Phase 4 input invalid: Invalid timing/geometry for sub_71",
            ),
            PipelineFailureClass.TERMINAL,
        )

    def test_phase2_remediation_contract_failure_is_terminal(self) -> None:
        self.assertEqual(
            classify_pipeline_failure(
                "PHASE2_REMEDIATION_INVALID",
                "Phase 2 OCR delta failed: remediation authority is invalid",
            ),
            PipelineFailureClass.TERMINAL,
        )

    def test_residual_authority_conflicts_are_terminal(self) -> None:
        for message in (
            "Residual matches existing Phase-1 geometry: sub_01,sub_02",
            "Residual 教程 requires a translation suggestion",
            "Residual OCR authority changed after translation was queued",
            "Residual OCR candidate drift detected for p2r_01",
            "Residual visual override authority is stale for p2r_01",
            "Residual Phase 2 rerun is blocked before Phase 3: unapproved_content:ocr_content_013",
            "Residual 正饰分享 source confirmation failed: Residual anchor is not confirmed in source OCR",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    classify_pipeline_failure("QUALITY_LOCALIZATION_FAILED", message),
                    PipelineFailureClass.TERMINAL,
                )

    def test_network_and_timeout_are_transient(self) -> None:
        for message in (
            "TimeoutError: request timed out",
            "ConnectionError: connection reset by peer",
            "HTTP 503 Service Unavailable",
            "HTTP 429 rate limit exceeded",
            "temporarily unavailable, try again",
            "[WinError 32] The process cannot access the file because it is being used by another process",
            "CUDA out of memory",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    classify_pipeline_failure("STEP_UNHANDLED_ERROR", message),
                    PipelineFailureClass.TRANSIENT,
                )

    def test_deterministic_python_errors_are_terminal(self) -> None:
        for message in (
            "AttributeError: 'NoneType' object has no attribute 'path'",
            "KeyError: 'segments'",
            "TypeError: expected str, got None",
            "ValueError: invalid literal for int()",
            "ImportError: cannot import name 'foo'",
            "AssertionError: contract broken",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    classify_pipeline_failure("STEP_UNHANDLED_ERROR", message),
                    PipelineFailureClass.TERMINAL,
                )

    def test_missing_input_is_terminal(self) -> None:
        self.assertEqual(
            classify_pipeline_failure("missing_source_video", "Source video has no downloaded asset"),
            PipelineFailureClass.TERMINAL,
        )

    def test_output_qa_failure_is_terminal(self) -> None:
        self.assertEqual(
            classify_pipeline_failure(
                "QUALITY_OUTPUT_QA_FAILED",
                "Adaptive visual preview output QA failed (residual_cjk)",
            ),
            PipelineFailureClass.TERMINAL,
        )

    def test_timing_fit_and_expired_provider_are_terminal(self) -> None:
        self.assertEqual(
            classify_pipeline_failure(
                "timing_fit_blocked",
                "TTS segment cannot fit safely: ratio=1.860",
            ),
            PipelineFailureClass.TERMINAL,
        )
        self.assertEqual(
            classify_pipeline_failure(
                "tts_provider_failed",
                "HTTP connector synthesis failed (expressive_feature_not_applied). Missing provider bindings: pause_not_applied.",
            ),
            PipelineFailureClass.TERMINAL,
        )
        self.assertEqual(
            classify_pipeline_failure(
                "translation_failed",
                'translation_provider_auth_failed:openai_compatible_http_401:{"error":"API key đã hết hạn."}',
            ),
            PipelineFailureClass.TERMINAL,
        )

    def test_unknown_failure_defaults_to_transient_once(self) -> None:
        self.assertEqual(
            classify_pipeline_failure("weird_code", "something odd happened"),
            PipelineFailureClass.TRANSIENT,
        )


class RetryDecisionTests(unittest.TestCase):
    def test_terminal_never_retries(self) -> None:
        self.assertFalse(
            should_auto_retry_pipeline_failure(
                failure_class=PipelineFailureClass.TERMINAL,
                attempts=1,
                max_attempts=3,
            )
        )

    def test_transient_retries_until_cap(self) -> None:
        self.assertTrue(
            should_auto_retry_pipeline_failure(
                failure_class=PipelineFailureClass.TRANSIENT,
                attempts=1,
                max_attempts=3,
            )
        )
        self.assertFalse(
            should_auto_retry_pipeline_failure(
                failure_class=PipelineFailureClass.TRANSIENT,
                attempts=3,
                max_attempts=3,
            )
        )

    def test_backoff_grows_and_is_capped(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        first = next_pipeline_retry_at(attempts=1, now=now, base_seconds=10, max_seconds=60)
        second = next_pipeline_retry_at(attempts=2, now=now, base_seconds=10, max_seconds=60)
        far = next_pipeline_retry_at(attempts=9, now=now, base_seconds=10, max_seconds=60)

        self.assertEqual((first - now).total_seconds(), 10)
        self.assertEqual((second - now).total_seconds(), 20)
        self.assertEqual((far - now).total_seconds(), 60)

    def test_operator_message_states_next_move(self) -> None:
        retrying = pipeline_failure_operator_message(
            failure_class=PipelineFailureClass.TRANSIENT,
            error_message="HTTP 503",
            will_retry=True,
        )
        exhausted = pipeline_failure_operator_message(
            failure_class=PipelineFailureClass.TRANSIENT,
            error_message="HTTP 503",
            will_retry=False,
        )
        terminal = pipeline_failure_operator_message(
            failure_class=PipelineFailureClass.TERMINAL,
            error_message="KeyError: 'segments'",
            will_retry=False,
        )

        self.assertIn("auto-retry", retrying)
        self.assertIn("retries exhausted", exhausted)
        self.assertIn("terminal", terminal)


if __name__ == "__main__":
    unittest.main()
