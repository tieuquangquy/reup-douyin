"""Running out of disk mid-render does not fail cleanly, it writes a broken mp4.

ffmpeg does not stop politely when the volume fills: the render "succeeds" with a truncated
file that then flows into QA and, if the checks miss it, into a published video. Refusing to
start a heavy job on a nearly full disk is far cheaper than detecting the damage later.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.enums import JobType
from src.services.disk_guard import (
    DISK_HEAVY_JOB_TYPES,
    DiskSpaceStatus,
    check_disk_headroom,
    min_free_bytes,
)

GB = 1024**3


class HeavyTypeTests(unittest.TestCase):
    def test_stages_that_write_video_are_guarded(self) -> None:
        for job_type in (
            JobType.DOWNLOAD_VIDEO,
            JobType.ANALYZE_AUDIO,
            JobType.ANALYZE_OCR,
            JobType.RENDER_FINAL,
            JobType.SYNTHESIZE_TTS,
        ):
            self.assertIn(job_type.value, DISK_HEAVY_JOB_TYPES)

    def test_bookkeeping_jobs_are_not_guarded(self) -> None:
        self.assertNotIn(JobType.CRAWL_PROFILE.value, DISK_HEAVY_JOB_TYPES)


class ThresholdTests(unittest.TestCase):
    def test_threshold_comes_from_settings_in_gigabytes(self) -> None:
        self.assertEqual(min_free_bytes(SimpleNamespace(min_free_disk_gb=10)), 10 * GB)

    def test_zero_disables_the_guard(self) -> None:
        self.assertEqual(min_free_bytes(SimpleNamespace(min_free_disk_gb=0)), 0)

    def test_garbage_falls_back_to_a_default(self) -> None:
        self.assertGreater(min_free_bytes(SimpleNamespace(min_free_disk_gb="plenty")), 0)


class HeadroomTests(unittest.TestCase):
    def _status(self, free_gb: float, *, required_gb: float = 10) -> DiskSpaceStatus:
        usage = SimpleNamespace(total=500 * GB, used=0, free=int(free_gb * GB))
        with patch("src.services.disk_guard.shutil.disk_usage", return_value=usage):
            return check_disk_headroom("./data/storage", required_bytes=int(required_gb * GB))

    def test_plenty_of_room_is_ok(self) -> None:
        status = self._status(120)

        self.assertTrue(status.ok)
        self.assertIsNone(status.message)

    def test_almost_full_is_refused_with_a_readable_reason(self) -> None:
        status = self._status(2)

        self.assertFalse(status.ok)
        self.assertIn("2", str(status.message))
        self.assertIn("GB", str(status.message))

    def test_exactly_at_the_threshold_is_allowed(self) -> None:
        self.assertTrue(self._status(10).ok)

    def test_a_disabled_guard_always_passes(self) -> None:
        self.assertTrue(self._status(0.1, required_gb=0).ok)

    def test_an_unreadable_path_never_blocks_work(self) -> None:
        with patch("src.services.disk_guard.shutil.disk_usage", side_effect=OSError("no such volume")):
            status = check_disk_headroom("./nowhere", required_bytes=10 * GB)

        self.assertTrue(status.ok, "A guard that cannot measure must not stop the pipeline")


class JobRunnerIntegrationTests(unittest.TestCase):
    def _run(self, status: DiskSpaceStatus, job_type: JobType):
        from src.services.job_runner import JobRunner, StepHandlerRegistry

        step = SimpleNamespace(
            step_key="prepare",
            status="PENDING",
            progress_percent=0,
            error_code=None,
            error_message=None,
        )
        job = SimpleNamespace(
            id="job-1",
            job_type=job_type,
            status="RUNNING",
            steps=[step],
            attempts=1,
            max_attempts=3,
            retryable=True,
            metadata_json=None,
        )
        runner = JobRunner(db=MagicMock(), handlers=StepHandlerRegistry())
        runner.service = MagicMock()
        runner.service.get_job.return_value = job
        with patch("src.services.disk_guard.check_disk_headroom", return_value=status):
            return runner, job

    def test_a_full_disk_stops_a_render_before_it_starts(self) -> None:
        from src.services.job_runner import JobRunner

        blocked = DiskSpaceStatus(ok=False, free_bytes=GB, required_bytes=10 * GB, message="Only 1.0 GB free")
        runner, job = self._run(blocked, JobType.RENDER_FINAL)

        with patch("src.services.job_runner.check_disk_headroom", return_value=blocked):
            reason = JobRunner._disk_block_reason(runner, job)

        self.assertIsNotNone(reason)
        self.assertIn("GB", str(reason))

    def test_a_healthy_disk_does_not_interfere(self) -> None:
        from src.services.job_runner import JobRunner

        fine = DiskSpaceStatus(ok=True, free_bytes=200 * GB, required_bytes=10 * GB, message=None)
        runner, job = self._run(fine, JobType.RENDER_FINAL)

        with patch("src.services.job_runner.check_disk_headroom", return_value=fine):
            self.assertIsNone(JobRunner._disk_block_reason(runner, job))

    def test_light_jobs_skip_the_check_entirely(self) -> None:
        from src.services.job_runner import JobRunner

        blocked = DiskSpaceStatus(ok=False, free_bytes=GB, required_bytes=10 * GB, message="Only 1.0 GB free")
        runner, job = self._run(blocked, JobType.CRAWL_PROFILE)

        with patch("src.services.job_runner.check_disk_headroom", return_value=blocked):
            self.assertIsNone(JobRunner._disk_block_reason(runner, job))


class RetryClassificationTests(unittest.TestCase):
    def test_low_disk_is_transient_so_the_job_waits_for_room(self) -> None:
        from src.services.pipeline_retry_policy import PipelineFailureClass, classify_pipeline_failure

        self.assertEqual(
            classify_pipeline_failure("DISK_SPACE_LOW", "Only 1.0 GB free on ./data/storage"),
            PipelineFailureClass.TRANSIENT,
        )


if __name__ == "__main__":
    unittest.main()
