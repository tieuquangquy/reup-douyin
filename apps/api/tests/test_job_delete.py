from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from src.db.base import Base
from src.enums import JobStatus, JobStepStatus
from src.services.job_service import JobNotFound, JobService


class JobDeleteTests(unittest.TestCase):
    def test_delete_job_clears_references_and_removes_rows(self) -> None:
        job_id = uuid4()
        step = SimpleNamespace(id=uuid4())
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.RUNNING,
            steps=[step],
        )
        db = MagicMock()
        service = JobService(db)
        service.get_job = MagicMock(return_value=job)
        service._preserve_job_id_in_metadata = MagicMock()

        service.delete_job(job_id)

        service._preserve_job_id_in_metadata.assert_called_once_with(job_id)
        self.assertGreaterEqual(db.execute.call_count, 1)
        db.delete.assert_any_call(step)
        db.delete.assert_any_call(job)
        db.commit.assert_called_once()

    def test_delete_job_detaches_every_nullable_job_foreign_key(self) -> None:
        job_id = uuid4()
        db = MagicMock()
        service = JobService(db)

        expected = {
            (table.name, column.name)
            for table in Base.metadata.tables.values()
            if table.name not in {"jobs", "job_steps"}
            for column in table.columns
            if column.nullable
            and any(fk.target_fullname in {"jobs.id", "public.jobs.id"} for fk in column.foreign_keys)
        }

        service._clear_job_references(job_id)

        touched = {
            (call.args[0].table.name, str(next(iter(call.args[0]._values))))
            for call in db.execute.call_args_list
        }
        self.assertEqual(touched, expected)
        self.assertIn(("reup_queue_items", "job_id"), touched)
        self.assertIn(("content_classifications", "created_by_job_id"), touched)
        self.assertIn(("publication_metric_schedules", "last_collection_job_id"), touched)
        self.assertIn(("affiliate_comment_placements", "post_job_id"), touched)

    def test_delete_job_rolls_back_when_database_rejects_delete(self) -> None:
        job_id = uuid4()
        job = SimpleNamespace(id=job_id, status=JobStatus.COMPLETED, steps=[])
        db = MagicMock()
        db.commit.side_effect = IntegrityError("delete", {}, Exception("fk"))
        service = JobService(db)
        service.get_job = MagicMock(return_value=job)
        service._preserve_job_id_in_metadata = MagicMock()
        service._clear_job_references = MagicMock()

        with self.assertRaisesRegex(ValueError, "linked data"):
            service.delete_job(job_id)

        db.rollback.assert_called_once()

    def test_delete_running_job_with_worker_lock_is_rejected(self) -> None:
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.RUNNING,
            locked_by="local-worker-2",
            steps=[],
        )
        db = MagicMock()
        service = JobService(db)
        service.get_job = MagicMock(return_value=job)

        with self.assertRaisesRegex(ValueError, "cancel it"):
            service.delete_job(job_id)

        db.delete.assert_not_called()
        db.commit.assert_not_called()

    def test_preserve_job_id_stamps_render_metadata(self) -> None:
        job_id = uuid4()
        render = SimpleNamespace(
            metadata_json={"manifest": {"render_version": "RENDER_PIPELINE_V1_RUN_1"}},
        )
        db = MagicMock()
        db.scalars.return_value = [render]
        service = JobService(db)

        service._preserve_job_id_in_metadata(job_id)

        self.assertEqual(render.metadata_json["created_by_job_id"], str(job_id))
        self.assertEqual(render.metadata_json["manifest"]["job_id"], str(job_id))
        db.flush.assert_called_once()
        db.scalars.assert_called_once()

    def test_delete_job_not_found(self) -> None:
        db = MagicMock()
        service = JobService(db)
        service.get_job = MagicMock(side_effect=JobNotFound("missing"))

        with self.assertRaises(JobNotFound):
            service.delete_job(uuid4())

        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
