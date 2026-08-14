"""run_job must apply the pipeline retry policy to post-download stages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest

from src.enums import JobStatus, JobStepStatus, JobType
from src.services.job_runner import JobRunner, resolve_failure_outcome
from src.services.job_state_machine import validate_job_transition, validate_step_transition


class ResolveFailureOutcomeTests(unittest.TestCase):
    def test_precondition_failure_moves_pending_step_through_running(self) -> None:
        transitions: list[tuple[JobStepStatus, JobStepStatus]] = []
        step = SimpleNamespace(status=JobStepStatus.PENDING)
        job = SimpleNamespace(
            id="job-1",
            job_type=JobType.SYNTHESIZE_TTS,
            status=JobStatus.RUNNING,
            steps=[step],
            attempts=1,
            retryable=True,
            max_attempts=3,
            scheduled_at=None,
            locked_by="worker-1",
            locked_at=datetime.now(UTC),
        )

        class Service:
            def transition_step(self, target, status, **_kwargs):
                validate_step_transition(target.status, status)
                transitions.append((target.status, status))
                target.status = status

            def transition_job(self, target, status, **_kwargs):
                validate_job_transition(target.status, status)
                target.status = status

            def refresh_progress(self, target):
                return target

            def get_job(self, _job_id):
                return job

        runner = JobRunner.__new__(JobRunner)
        runner.service = Service()
        runner.db = SimpleNamespace(commit=lambda: None)

        result = runner._fail_job_before_start(
            job,
            error_code="INVALID_FRONTEND_RUNTIME_BINDING",
            error_message="stale runtime",
        )

        self.assertEqual(
            transitions,
            [
                (JobStepStatus.PENDING, JobStepStatus.RUNNING),
                (JobStepStatus.RUNNING, JobStepStatus.FAILED),
            ],
        )
        self.assertEqual(result.status, JobStatus.FAILED)

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

    def test_stale_frontend_runtime_never_retries_even_for_download(self) -> None:
        outcome = resolve_failure_outcome(
            job_type=JobType.DOWNLOAD_VIDEO,
            attempts=1,
            retryable=True,
            max_attempts=8,
            error_code="INVALID_FRONTEND_RUNTIME_BINDING",
            error_message="DOWNLOAD_VIDEO job is bound to a stale runtime",
        )

        self.assertEqual(outcome.status, JobStatus.FAILED)
        self.assertIsNone(outcome.scheduled_at)
        self.assertTrue(outcome.metadata["runtime_binding_invalid"])

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

    def test_provider_402_is_terminal_without_wasteful_retry(self) -> None:
        outcome = resolve_failure_outcome(
            job_type=JobType.SYNTHESIZE_TTS,
            attempts=1,
            retryable=True,
            max_attempts=3,
            error_code="tts_provider_failed",
            error_message="HTTP connector synthesis failed (http_402, HTTP 402).",
        )

        self.assertEqual(outcome.status, JobStatus.FAILED)
        self.assertIsNone(outcome.scheduled_at)
        self.assertIn("billing/credit required", outcome.operator_message)
        self.assertTrue(outcome.metadata["pipeline_provider_billing_required"])

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
