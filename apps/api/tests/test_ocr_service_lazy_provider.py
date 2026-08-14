"""OCR service must not eagerly init Paddle on API create/summary paths."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from types import SimpleNamespace

from src.ocr_pipeline.services.ocr_service import OcrPipelineService
from src.enums import JobStatus


class OcrServiceLazyProviderTests(unittest.TestCase):
    def test_phase2_persistence_uses_content_objects_not_empty_frame_objects(self) -> None:
        db = MagicMock()
        source = SimpleNamespace(id=uuid4(), workspace_id=uuid4())
        service = OcrPipelineService(db, storage=MagicMock(), ocr_provider=None)
        object_count, detection_count = service._persist_phase2_tracks(
            source,
            phase2_contract={
                "schema_version": "phase2_ocr_timeline_v2",
                "track_enrichments": [
                    {"text_id": "sub_01", "content_id": "ocr_content_001"},
                    {"text_id": "sub_02", "content_id": "ocr_content_001"},
                ],
                "content_objects": [
                    {
                        "content_id": "ocr_content_001",
                        "ocr_text_candidate": "需要把眼尾撑开抬高",
                        "ocr_text_raw_candidates": ["需要把眼尾撑开抬高"],
                        "review_status": "OCR_CANDIDATE",
                        "geometry_refs": ["sub_01", "sub_02"],
                        "review_assets": [
                            {"text_id": "sub_01", "start_frame": 10, "end_frame": 20},
                            {"text_id": "sub_02", "start_frame": 21, "end_frame": 30},
                        ],
                    },
                    {
                        "content_id": "ocr_content_002",
                        "ocr_text_candidate": "",
                        "review_status": "OCR_FAILED",
                        "geometry_refs": ["sub_03"],
                    },
                ],
                "protected_source_tracks": [],
            },
            payload={
                "fps": 30.0,
                "frames": [
                    {
                        "time_ms": 333,
                        "boxes": [
                            {"text_id": "sub_01", "x": 0.1, "y": 0.2, "w": 0.4, "h": 0.05, "confidence": 0.9},
                            {"text_id": "sub_02", "x": 0.1, "y": 0.2, "w": 0.4, "h": 0.05, "confidence": 0.8},
                            {"text_id": "sub_03", "x": 0.1, "y": 0.2, "w": 0.4, "h": 0.05, "confidence": 0.0},
                        ],
                    }
                ],
            },
        )

        self.assertEqual(object_count, 1)
        self.assertEqual(detection_count, 2)
        added_objects = [
            item
            for call in db.add_all.call_args_list
            for item in call.args[0]
            if item.__class__.__name__ == "OcrTextObject"
        ]
        self.assertEqual(len(added_objects), 1)
        self.assertEqual(added_objects[0].text, "需要把眼尾撑开抬高")
        self.assertEqual(added_objects[0].metadata_json["authority"], "phase2_content_object")

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

            created = service.create_ocr_job(
                OcrRequest(
                    source_video_id=source.id,
                    analysis_engine="audio_visual_temporal_v1",
                )
            )
            build.assert_not_called()
            self.assertEqual(created.id, job.id)
            payload = job_svc_cls.return_value.create_job.call_args.kwargs[
                "payload_json"
            ]
            self.assertEqual(
                payload["analysis_engine"], "audio_visual_temporal_v1"
            )

    def test_create_quality_ocr_reuses_equivalent_live_job(self) -> None:
        db = MagicMock()
        source = SimpleNamespace(id=uuid4(), workspace_id=uuid4())
        existing = SimpleNamespace(
            id=uuid4(),
            status=JobStatus.RUNNING,
            payload_json={
                "workflow_version": "QUALITY_LOCALIZATION_V24_1",
                "workflow_action": "resume_dialogue_translation",
                "force_refresh": False,
            },
        )
        db.scalars.return_value.all.return_value = [existing]
        with (
            patch.object(OcrPipelineService, "_load_source_video", return_value=source),
            patch("src.ocr_pipeline.services.ocr_service.JobService") as job_svc_cls,
        ):
            service = OcrPipelineService(db, storage=MagicMock(), ocr_provider=None)
            from src.ocr_pipeline.types import OcrRequest

            created = service.create_ocr_job(
                OcrRequest(
                    source_video_id=source.id,
                    workflow_version="QUALITY_LOCALIZATION_V24_1",
                    workflow_action="resume_dialogue_translation",
                    analysis_engine="audio_visual_temporal_v1",
                )
            )

        self.assertIs(created, existing)
        job_svc_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
