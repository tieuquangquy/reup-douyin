"""Per-type slots do not protect a single GPU.

ANALYZE_AUDIO, SYNTHESIZE_TTS, ANALYZE_OCR and RENDER_FINAL each have their own slot, so
four different heavy stages can still land on one 4 GB card at the same time and OOM. The
shared resource group is what actually caps the machine.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.enums import JobType
from src.services.job_runner import (
    GPU_JOB_TYPES,
    JobRunner,
    StepHandlerRegistry,
    gpu_claim_allowed,
    gpu_max_concurrent_running,
)


class FakeSettings:
    gpu_max_concurrent_running = 1
    download_video_max_concurrent_running = 1
    analyze_audio_max_concurrent_running = 1
    synthesize_tts_max_concurrent_running = 2
    analyze_ocr_max_concurrent_running = 1
    render_final_max_concurrent_running = 1


class GpuGroupTests(unittest.TestCase):
    def test_every_heavy_media_stage_shares_the_gpu(self) -> None:
        for job_type in (
            JobType.ANALYZE_AUDIO,
            JobType.SYNTHESIZE_TTS,
            JobType.ANALYZE_OCR,
            JobType.RENDER_PREVIEW,
            JobType.RENDER_FINAL,
        ):
            self.assertIn(job_type.value, GPU_JOB_TYPES)

    def test_download_and_crawl_do_not_hold_the_gpu(self) -> None:
        self.assertNotIn(JobType.DOWNLOAD_VIDEO.value, GPU_JOB_TYPES)
        self.assertNotIn(JobType.CRAWL_PROFILE.value, GPU_JOB_TYPES)

    def test_limit_reads_settings_and_has_a_floor(self) -> None:
        self.assertEqual(gpu_max_concurrent_running(FakeSettings()), 1)

        class Zeroed(FakeSettings):
            gpu_max_concurrent_running = 0

        self.assertEqual(gpu_max_concurrent_running(Zeroed()), 1)

    def test_render_waits_while_ocr_holds_the_card(self) -> None:
        self.assertFalse(gpu_claim_allowed(JobType.RENDER_FINAL, running_in_group=1, limit=1))
        self.assertTrue(gpu_claim_allowed(JobType.RENDER_FINAL, running_in_group=0, limit=1))

    def test_download_never_waits_on_the_gpu(self) -> None:
        self.assertTrue(
            gpu_claim_allowed(JobType.DOWNLOAD_VIDEO, running_in_group=5, limit=1),
            "CPU/network work must keep flowing while the card is busy",
        )

    def test_bigger_card_allows_more(self) -> None:
        self.assertTrue(gpu_claim_allowed(JobType.RENDER_FINAL, running_in_group=1, limit=2))


class ClaimStatementTests(unittest.TestCase):
    def test_claim_filters_on_group_usage_as_well_as_type(self) -> None:
        db = MagicMock()
        db.scalar.return_value = None
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())

        with patch("src.services.job_runner.get_settings", return_value=FakeSettings()):
            self.assertIsNone(runner.claim_next_job("worker-1"))

        where_sql = str(db.scalar.call_args.args[0].whereclause).lower().replace(" ", "").replace("\n", "")
        self.assertIn("job_typein", where_sql, "Group usage must be counted across several types")
        self.assertGreaterEqual(where_sql.count("selectcount"), 2, "Type slot and group slot are separate counts")


if __name__ == "__main__":
    unittest.main()
