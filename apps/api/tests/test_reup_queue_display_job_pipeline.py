"""Worklist must surface the auto-pipeline job that is actually running.

After ANALYZE_AUDIO completes the orchestrator starts BUILD_TRANSLATION_DRAFT and
then SYNTHESIZE_TTS. If the API keeps returning the finished analyze job, the
Transcript tab shows "Transcript ready" while work is still in flight.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import UUID, uuid4

from src.enums import JobStatus, JobType, ReupQueueStatus
from src.services.reup_queue_service import ReupQueueService


class FakeJobDb:
    def __init__(self, jobs: dict[UUID, object]):
        self.jobs = jobs

    def get(self, _model, pk):
        return self.jobs.get(pk)


def _job(job_type: JobType, status: JobStatus) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), job_type=job_type, status=status, progress_percent=0)


def _item(*, linked, meta: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status=ReupQueueStatus.WAITING_FOR_METADATA,
        job=linked,
        job_id=getattr(linked, "id", None),
        metadata_json=meta,
    )


class DisplayJobPipelineTests(unittest.TestCase):
    def _service(self, jobs: list[SimpleNamespace]) -> ReupQueueService:
        return ReupQueueService(FakeJobDb({job.id: job for job in jobs}))

    def test_running_translation_draft_wins_over_completed_analyze(self) -> None:
        analyze = _job(JobType.ANALYZE_AUDIO, JobStatus.COMPLETED)
        translate = _job(JobType.BUILD_TRANSLATION_DRAFT, JobStatus.RUNNING)
        item = _item(
            linked=analyze,
            meta={
                "analyze_audio_job_id": str(analyze.id),
                "translation_job_id": str(translate.id),
                "pipeline_step": "translate",
            },
        )

        resolved = self._service([analyze, translate]).resolve_display_job(item)

        self.assertIs(resolved, translate)

    def test_queued_tts_wins_over_completed_earlier_steps(self) -> None:
        analyze = _job(JobType.ANALYZE_AUDIO, JobStatus.COMPLETED)
        translate = _job(JobType.BUILD_TRANSLATION_DRAFT, JobStatus.COMPLETED)
        tts = _job(JobType.SYNTHESIZE_TTS, JobStatus.QUEUED)
        item = _item(
            linked=analyze,
            meta={
                "analyze_audio_job_id": str(analyze.id),
                "translation_job_id": str(translate.id),
                "tts_job_id": str(tts.id),
                "pipeline_step": "tts",
            },
        )

        resolved = self._service([analyze, translate, tts]).resolve_display_job(item)

        self.assertIs(resolved, tts)

    def test_running_analyze_still_wins(self) -> None:
        analyze = _job(JobType.ANALYZE_AUDIO, JobStatus.RUNNING)
        item = _item(
            linked=None,
            meta={"analyze_audio_job_id": str(analyze.id), "pipeline_step": "analyze_audio"},
        )

        resolved = self._service([analyze]).resolve_display_job(item)

        self.assertIs(resolved, analyze)

    def test_falls_back_to_analyze_when_nothing_is_active(self) -> None:
        analyze = _job(JobType.ANALYZE_AUDIO, JobStatus.COMPLETED)
        item = _item(
            linked=None,
            meta={"analyze_audio_job_id": str(analyze.id), "pipeline_step": "ready_final"},
        )

        resolved = self._service([analyze]).resolve_display_job(item)

        self.assertIs(resolved, analyze, "Transcript unlock still needs the analyze outcome")

    def test_failed_pipeline_job_is_surfaced(self) -> None:
        analyze = _job(JobType.ANALYZE_AUDIO, JobStatus.COMPLETED)
        translate = _job(JobType.BUILD_TRANSLATION_DRAFT, JobStatus.FAILED)
        item = _item(
            linked=analyze,
            meta={
                "analyze_audio_job_id": str(analyze.id),
                "translation_job_id": str(translate.id),
                "pipeline_step": "translate",
            },
        )

        resolved = self._service([analyze, translate]).resolve_display_job(item)

        self.assertIs(resolved, translate, "Operators must see the failing step, not the old success")


if __name__ == "__main__":
    unittest.main()
