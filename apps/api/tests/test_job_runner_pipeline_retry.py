"""run_job must apply the pipeline retry policy to post-download stages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from src.enums import JobStatus, JobType
from src.services.job_runner import resolve_failure_outcome


class ResolveFailureOutcomeTests(unittest.TestCase):
    def test_transient_render_failure_is_rescheduled(self) -> None:
        outcome = resolve_failure_outcome(
            job_type=JobType.RENDER_FINAL,
            attempts=1,
            retryable=True,
            max_attempts=3,
            error_code="STEP_UNHANDLED_ERROR",
            error_message="TimeoutError: ffmpeg pipe timed out",
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )

        self.assertEqual(outcome.status, JobStatus.RETRYABLE)
        self.assertIsNotNone(outcome.scheduled_at, "Retry must back off, not re-claim instantly")
        self.assertIn("auto-retry", outcome.operator_message)
        self.assertEqual(outcome.metadata["pipeline_failure_class"], "transient")

    def test_terminal_pipeline_failure_stops_immediately(self) -> None:
        outcome = resolve_failure_outcome(
            job_type=JobType.ANALYZE_OCR,
            attempts=1,
            retryable=True,
            max_attempts=5,
            error_code="STEP_UNHANDLED_ERROR",
            error_message="KeyError: 'segments'",
        )

        self.assertEqual(outcome.status, JobStatus.FAILED)
        self.assertIsNone(outcome.scheduled_at)
        self.assertIn("terminal", outcome.operator_message)

    def test_provider_429_waits_for_full_rate_window(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        outcome = resolve_failure_outcome(
            job_type=JobType.BUILD_TRANSLATION_DRAFT,
            attempts=1,
            retryable=True,
            max_attempts=3,
            error_code="translation_failed",
            error_message="translation_provider_unavailable:gemini_http_429:quota",
            now=now,
        )

        self.assertEqual(outcome.status, JobStatus.RETRYABLE)
        self.assertEqual(outcome.scheduled_at, now + timedelta(seconds=60))
        self.assertTrue(outcome.metadata["pipeline_provider_rate_limited"])

    def test_transient_stops_after_cap(self) -> None:
        outcome = resolve_failure_outcome(
            job_type=JobType.SYNTHESIZE_TTS,
            attempts=3,
            retryable=True,
            max_attempts=3,
            error_code="tts_failed",
            error_message="HTTP 503 upstream unavailable",
        )

        self.assertEqual(outcome.status, JobStatus.FAILED)
        self.assertIn("retries exhausted", outcome.operator_message)

    def test_non_retryable_job_never_reschedules(self) -> None:
        outcome = resolve_failure_outcome(
            job_type=JobType.ANALYZE_AUDIO,
            attempts=1,
            retryable=False,
            max_attempts=3,
            error_code="asr_failed",
            error_message="connection reset by peer",
        )

        self.assertEqual(outcome.status, JobStatus.FAILED)

    def test_download_keeps_its_own_policy(self) -> None:
        outcome = resolve_failure_outcome(
            job_type=JobType.DOWNLOAD_VIDEO,
            attempts=1,
            retryable=True,
            max_attempts=3,
            error_code="download_failed",
            error_message="TargetClosed: browser context lost",
        )

        self.assertEqual(outcome.status, JobStatus.RETRYABLE)
        self.assertIn("download_failure_class", outcome.metadata)
        self.assertNotIn("pipeline_failure_class", outcome.metadata)

    def test_unmanaged_job_type_uses_plain_attempt_budget(self) -> None:
        outcome = resolve_failure_outcome(
            job_type=JobType.CRAWL_PROFILE,
            attempts=1,
            retryable=True,
            max_attempts=3,
            error_code="crawl_profile_failed",
            error_message="profile unreachable",
        )

        self.assertEqual(outcome.status, JobStatus.RETRYABLE)
        self.assertIsNone(outcome.scheduled_at)
        self.assertEqual(outcome.metadata, {})


if __name__ == "__main__":
    unittest.main()
