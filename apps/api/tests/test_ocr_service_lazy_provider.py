"""OCR service must not eagerly init Paddle on API create/summary paths."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.ocr_pipeline.services.ocr_service import OcrPipelineService


class OcrServiceLazyProviderTests(unittest.TestCase):
    def test_init_does_not_call_build_default_ocr_provider(self) -> None:
        db = MagicMock()
        with patch(
            "src.ocr_pipeline.services.ocr_service.build_default_ocr_provider"
        ) as build:
            service = OcrPipelineService(db, storage=MagicMock(), ocr_provider=None)
            build.assert_not_called()
            # Accessing provider builds once.
            _ = service.ocr_provider
            build.assert_called_once()
            _ = service.ocr_provider
            build.assert_called_once()

    def test_create_ocr_job_does_not_touch_provider(self) -> None:
        db = MagicMock()
        source = MagicMock()
        source.id = uuid4()
        source.workspace_id = uuid4()
        with (
            patch(
                "src.ocr_pipeline.services.ocr_service.build_default_ocr_provider"
            ) as build,
            patch.object(OcrPipelineService, "_load_source_video", return_value=source),
            patch("src.ocr_pipeline.services.ocr_service.JobService") as job_svc_cls,
        ):
            job = MagicMock()
            job.id = uuid4()
            job.status = "QUEUED"
            job_svc_cls.return_value.create_job.return_value = job
            service = OcrPipelineService(db, storage=MagicMock(), ocr_provider=None)
            from src.ocr_pipeline.types import OcrRequest

            created = service.create_ocr_job(OcrRequest(source_video_id=source.id))
            build.assert_not_called()
            self.assertEqual(created.id, job.id)


if __name__ == "__main__":
    unittest.main()
