"""Heavy pipeline stages need their own running slots, not just download.

Render and OCR each pin CPU/GPU for minutes; letting a Start-auto batch run several at
once starves everything else and can push the box into swap.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.enums import JobType
from src.services.job_runner import (
    JobRunner,
    StepHandlerRegistry,
    job_type_claim_allowed,
    job_type_concurrency_limits,
)


class FakeSettings:
    download_video_max_concurrent_running = 1
    render_final_max_concurrent_running = 1
    analyze_ocr_max_concurrent_running = 1
    analyze_audio_max_concurrent_running = 1
    synthesize_tts_max_concurrent_running = 2


class JobTypeConcurrencyLimitTests(unittest.TestCase):
    def test_limits_cover_every_heavy_stage(self) -> None:
        limits = job_type_concurrency_limits(FakeSettings())

        self.assertEqual(limits[JobType.DOWNLOAD_VIDEO.value], 1)
        self.assertEqual(limits[JobType.RENDER_FINAL.value], 1)
        self.assertEqual(limits[JobType.ANALYZE_OCR.value], 1)
        self.assertEqual(limits[JobType.ANALYZE_AUDIO.value], 1)
        self.assertEqual(limits[JobType.SYNTHESIZE_TTS.value], 2)

    def test_limits_are_at_least_one(self) -> None:
        class Zeroed(FakeSettings):
            render_final_max_concurrent_running = 0

        self.assertEqual(job_type_concurrency_limits(Zeroed())[JobType.RENDER_FINAL.value], 1)

    def test_unlisted_type_is_unlimited(self) -> None:
        self.assertNotIn(JobType.CRAWL_PROFILE.value, job_type_concurrency_limits(FakeSettings()))

    def test_claim_allowed_compares_against_own_type(self) -> None:
        limits = job_type_concurrency_limits(FakeSettings())

        self.assertTrue(job_type_claim_allowed(JobType.DOWNLOAD_VIDEO, running_same_type=0, limits=limits))
        self.assertFalse(
            job_type_claim_allowed(JobType.DOWNLOAD_VIDEO, running_same_type=1, limits=limits),
            "Start-auto batches must not storm Playwright downloads",
        )
        self.assertTrue(job_type_claim_allowed(JobType.RENDER_FINAL, running_same_type=0, limits=limits))
        self.assertFalse(job_type_claim_allowed(JobType.RENDER_FINAL, running_same_type=1, limits=limits))
        self.assertTrue(
            job_type_claim_allowed(JobType.SYNTHESIZE_TTS, running_same_type=1, limits=limits),
            "TTS allows two in flight",
        )
        self.assertTrue(
            job_type_claim_allowed(JobType.CRAWL_PROFILE, running_same_type=9, limits=limits),
            "Types without a cap must never wait",
        )

    def test_render_does_not_wait_on_download_slots(self) -> None:
        limits = job_type_concurrency_limits(FakeSettings())
        self.assertTrue(
            job_type_claim_allowed(JobType.RENDER_FINAL, running_same_type=0, limits=limits),
            "Slots are per type; a busy download must not block render",
        )


class ClaimStatementTests(unittest.TestCase):
    def test_claim_filters_on_same_type_running_count(self) -> None:
        db = MagicMock()
        db.scalar.return_value = None
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())

        with patch("src.services.job_runner.get_settings", return_value=FakeSettings()):
            self.assertIsNone(runner.claim_next_job("worker-1"))

        stmt = db.scalar.call_args.args[0]
        where_sql = str(stmt.whereclause).lower().replace(" ", "").replace("\n", "")
        self.assertIn("selectcount", where_sql)
        self.assertIn("workspace_id", where_sql)
        self.assertIn("case", where_sql, "Per-type limit must be resolved in SQL")
        self.assertIn("job_type=", where_sql, "Running count must be scoped to the same job type")


if __name__ == "__main__":
    unittest.main()
