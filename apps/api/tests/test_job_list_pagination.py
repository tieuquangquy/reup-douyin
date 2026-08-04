from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.api.routes.jobs import list_jobs as list_jobs_route
from src.enums import JobStatus, JobType
from src.schemas.jobs import JobListResponse
from src.services.job_service import JobService


def _fake_job():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        job_type=JobType.DOWNLOAD_VIDEO,
        status=JobStatus.QUEUED,
        source_video_id=None,
        crawl_session_id=None,
        render_output_id=None,
        reference_type=None,
        reference_id=None,
        current_step_key=None,
        current_step_index=0,
        progress_percent=0,
        total_steps=0,
        completed_steps=0,
        failed_steps=0,
        priority=0,
        attempts=0,
        max_attempts=3,
        retryable=True,
        locked_by=None,
        locked_at=None,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        created_at=now,
        updated_at=now,
        steps=[],
    )


class JobListPaginationContractTests(unittest.TestCase):
    def test_job_list_response_includes_total_count_limit_offset(self) -> None:
        payload = JobListResponse(jobs=[], total_count=12, limit=5, offset=5)
        self.assertEqual(payload.total_count, 12)
        self.assertEqual(payload.limit, 5)
        self.assertEqual(payload.offset, 5)

    def test_list_jobs_service_returns_total_and_page(self) -> None:
        db = MagicMock()
        db.scalars.return_value.unique.return_value = [_fake_job(), _fake_job()]
        db.scalar.return_value = 7
        service = JobService(db)
        items, total = service.list_jobs(status=JobStatus.FAILED, limit=2, offset=0)
        self.assertEqual(total, 7)
        self.assertEqual(len(items), 2)

    def test_list_jobs_route_echoes_pagination_fields(self) -> None:
        service = MagicMock()
        service.list_jobs.return_value = ([_fake_job()], 42)
        response = list_jobs_route(
            status_filter=None,
            job_type=None,
            source_video_id=None,
            q=None,
            limit=10,
            offset=20,
            service=service,
        )
        self.assertEqual(response.total_count, 42)
        self.assertEqual(response.limit, 10)
        self.assertEqual(response.offset, 20)
        self.assertEqual(len(response.jobs), 1)


if __name__ == "__main__":
    unittest.main()
