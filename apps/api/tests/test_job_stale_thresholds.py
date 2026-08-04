"""A long render is not a hung download.

`locked_at` is stamped once at claim time, so a single wall-clock threshold derived from
download budgets kills healthy renders and requeues them forever. Each type gets its own
patience, and a running job refreshes its lock so "no heartbeat" is what stale means.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, JobType
from src.services.job_runner import (
    JobRunner,
    StepHandlerRegistry,
    job_type_stale_seconds,
)


class FakeSettings:
    download_video_stale_running_seconds = 600
    render_final_stale_running_seconds = 5400
    analyze_ocr_stale_running_seconds = 5400
    analyze_audio_stale_running_seconds = 2700
    synthesize_tts_stale_running_seconds = 2700
    build_translation_draft_stale_running_seconds = 1800
    job_stale_running_seconds_default = 1800


class StaleThresholdTests(unittest.TestCase):
    def test_render_gets_far_more_patience_than_download(self) -> None:
        settings = FakeSettings()
        download = job_type_stale_seconds(JobType.DOWNLOAD_VIDEO, settings=settings)
        render = job_type_stale_seconds(JobType.RENDER_FINAL, settings=settings)

        self.assertGreater(render, download * 2, "A 30-minute render must not look hung at the download budget")

    def test_unknown_type_uses_default(self) -> None:
        self.assertEqual(
            job_type_stale_seconds(JobType.CRAWL_PROFILE, settings=FakeSettings()),
            1800,
        )

    def test_threshold_never_drops_below_a_safe_floor(self) -> None:
        class Tiny(FakeSettings):
            render_final_stale_running_seconds = 5

        self.assertGreaterEqual(job_type_stale_seconds(JobType.RENDER_FINAL, settings=Tiny()), 120)


def _running_job(job_type: JobType, *, age_seconds: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        job_type=job_type,
        status=JobStatus.RUNNING,
        locked_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
        locked_by="worker-1",
        scheduled_at=None,
        steps=[],
        metadata_json=None,
    )


class ReleaseStaleRunningLocksTests(unittest.TestCase):
    def _run(self, jobs: list[SimpleNamespace]) -> MagicMock:
        db = MagicMock()
        db.scalars.return_value.all.return_value = jobs
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())
        runner.service = MagicMock()
        with patch("src.services.job_runner.get_settings", return_value=FakeSettings()):
            runner.release_stale_running_locks()
        return runner.service

    def test_young_render_is_left_alone(self) -> None:
        service = self._run([_running_job(JobType.RENDER_FINAL, age_seconds=1_500)])

        service.transition_job.assert_not_called()

    def test_old_render_is_requeued(self) -> None:
        service = self._run([_running_job(JobType.RENDER_FINAL, age_seconds=6_000)])

        service.transition_job.assert_called_once()
        self.assertEqual(service.transition_job.call_args.args[1], JobStatus.RETRYABLE)

    def test_download_older_than_its_own_budget_is_requeued(self) -> None:
        service = self._run([_running_job(JobType.DOWNLOAD_VIDEO, age_seconds=1_500)])

        service.transition_job.assert_called_once()

    def test_explicit_override_still_wins(self) -> None:
        db = MagicMock()
        db.scalars.return_value.all.return_value = [_running_job(JobType.RENDER_FINAL, age_seconds=300)]
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())
        runner.service = MagicMock()

        with patch("src.services.job_runner.get_settings", return_value=FakeSettings()):
            runner.release_stale_running_locks(max_age_seconds=120)

        runner.service.transition_job.assert_called_once()


class HeartbeatTests(unittest.TestCase):
    def test_touch_lock_refreshes_locked_at(self) -> None:
        from src.services.job_heartbeat import touch_job_lock

        job = _running_job(JobType.RENDER_FINAL, age_seconds=3_000)
        db = MagicMock()
        db.get.return_value = job

        self.assertTrue(touch_job_lock(db, job.id, worker_id="worker-1"))
        self.assertLess((datetime.now(UTC) - job.locked_at).total_seconds(), 5)
        db.commit.assert_called_once()

    def test_touch_lock_ignores_job_owned_by_another_worker(self) -> None:
        from src.services.job_heartbeat import touch_job_lock

        job = _running_job(JobType.RENDER_FINAL, age_seconds=3_000)
        before = job.locked_at
        db = MagicMock()
        db.get.return_value = job

        self.assertFalse(touch_job_lock(db, job.id, worker_id="other-worker"))
        self.assertEqual(job.locked_at, before)

    def test_touch_lock_ignores_finished_job(self) -> None:
        from src.services.job_heartbeat import touch_job_lock

        job = _running_job(JobType.RENDER_FINAL, age_seconds=10)
        job.status = JobStatus.COMPLETED
        db = MagicMock()
        db.get.return_value = job

        self.assertFalse(touch_job_lock(db, job.id, worker_id="worker-1"))

    def test_heartbeat_beats_while_the_job_runs(self) -> None:
        from src.services.job_heartbeat import JobHeartbeat

        beats: list[str] = []
        job_id = uuid4()

        def fake_touch(_db: object, _job_id: object, *, worker_id: str) -> bool:
            beats.append(worker_id)
            return True

        with patch("src.services.job_heartbeat.touch_job_lock", side_effect=fake_touch):
            with JobHeartbeat(
                session_factory=lambda: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: None),
                job_id=job_id,
                worker_id="worker-1",
                interval_seconds=0.01,
            ):
                import time

                time.sleep(0.1)

        self.assertGreater(len(beats), 0, "A long step must keep its lock warm")

    def test_heartbeat_failure_never_breaks_the_job(self) -> None:
        from src.services.job_heartbeat import JobHeartbeat

        with patch("src.services.job_heartbeat.touch_job_lock", side_effect=RuntimeError("db gone")):
            with JobHeartbeat(
                session_factory=lambda: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: None),
                job_id=uuid4(),
                worker_id="worker-1",
                interval_seconds=0.01,
            ):
                import time

                time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()
