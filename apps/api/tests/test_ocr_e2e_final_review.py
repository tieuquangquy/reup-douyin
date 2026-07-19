"""Final Review ANALYZE_OCR uses full Phase 1–4 hardsub E2E when clean_hardsub=True."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.media_pipeline.hardsub_e2e import CLEAN_METHOD_SINGLE_PASS, HardsubE2EResult
from src.ocr_pipeline.services.ocr_service import OcrPipelineService
from src.ocr_pipeline.types import OcrRequest


class OcrServiceFullE2ETests(unittest.TestCase):
    def test_clean_hardsub_uses_phases_1_to_4_and_persists_cleaned(self) -> None:
        source_id = uuid4()
        workspace_id = uuid4()
        source_video = SimpleNamespace(
            id=source_id,
            workspace_id=workspace_id,
            source_platform="douyin",
            normalized_profile_identifier="p",
            platform_video_id="v1",
        )
        raw_asset = SimpleNamespace(
            id=uuid4(),
            storage_key="raw/video.mp4",
            asset_type="SOURCE_VIDEO_RAW",
            is_current=True,
            status="AVAILABLE",
        )

        db = MagicMock()
        service = OcrPipelineService(db, storage=MagicMock(), ocr_provider=MagicMock())

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "in.mp4"
            video.write_bytes(b"fake")
            cleaned = Path(tmp) / "cleaned.mp4"
            cleaned.write_bytes(b"mp4-bytes")

            e2e = HardsubE2EResult(
                output_path=str(cleaned),
                sample_fps=1,
                frame_count=2,
                ocr_payload={
                    "provider": "rest_ocr",
                    "frames": [
                        {
                            "time_ms": 0,
                            "frame_width": 640,
                            "frame_height": 360,
                            "boxes": [
                                {
                                    "x": 0.1,
                                    "y": 0.8,
                                    "width": 0.7,
                                    "height": 0.1,
                                    "text": "你好",
                                    "confidence": 0.9,
                                }
                            ],
                        }
                    ],
                },
                vi_texts={"0": "Xin chao"},
                ocr_provider_name="retry(rest_ocr)",
                caption_ai_source="workspace_db",
            )

            persisted_meta: dict = {}

            def fake_persist_file(*args, **kwargs):
                persisted_meta.update(kwargs.get("metadata") or {})
                return SimpleNamespace(id=uuid4())

            with (
                patch.object(service, "_load_source_video", return_value=source_video),
                patch.object(service, "_storage_context", return_value=MagicMock()),
                patch.object(service, "_current_asset", return_value=raw_asset),
                patch.object(service, "_absolute_path_for_asset", return_value=video),
                patch.object(service, "_clear_previous_ocr_rows"),
                patch.object(service, "_mark_previous_ocr_assets_non_current"),
                patch.object(service, "_persist_detections", return_value=1),
                patch.object(service, "_persist_json_asset") as persist_json,
                patch.object(service, "_persist_file_asset", side_effect=fake_persist_file),
                patch(
                    "src.ocr_pipeline.services.ocr_service.run_hardsub_phases_1_to_4",
                    return_value=e2e,
                ) as run_e2e,
            ):
                result = service.run_pipeline(
                    OcrRequest(source_video_id=source_id, clean_hardsub=True, sample_fps=1.0),
                    job_id=uuid4(),
                )

            run_e2e.assert_called_once()
            self.assertIsNotNone(result.cleaned_video_asset_id)
            self.assertTrue(result.clean_produced)
            self.assertEqual(persisted_meta.get("clean_method"), CLEAN_METHOD_SINGLE_PASS)
            self.assertEqual(persisted_meta.get("caption_ai_source"), "workspace_db")
            events_call = persist_json.call_args
            payload = events_call.args[3] if len(events_call.args) > 3 else events_call.kwargs.get("payload")
            # _persist_json_asset(self, source_video, context, asset_type, payload, ...)
            self.assertIn("vi_texts", payload)
            self.assertEqual(payload["vi_texts"], {"0": "Xin chao"})

    def test_clean_skipped_restores_prior_cleaned_is_current(self) -> None:
        source_id = uuid4()
        workspace_id = uuid4()
        source_video = SimpleNamespace(
            id=source_id,
            workspace_id=workspace_id,
            source_platform="douyin",
            normalized_profile_identifier="p",
            platform_video_id="v1",
        )
        raw_asset = SimpleNamespace(id=uuid4(), storage_key="raw/video.mp4")
        prior_cleaned = SimpleNamespace(id=uuid4(), version=5, is_current=False)

        db = MagicMock()
        service = OcrPipelineService(db, storage=MagicMock(), ocr_provider=MagicMock())
        e2e = HardsubE2EResult(
            output_path="",
            sample_fps=1,
            frame_count=1,
            ocr_payload={"provider": "rest_ocr", "frames": [{"time_ms": 0, "boxes": []}]},
            vi_texts={},
            ocr_provider_name="rest_ocr",
            caption_ai_source="skipped",
        )

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "in.mp4"
            video.write_bytes(b"fake")
            with (
                patch.object(service, "_load_source_video", return_value=source_video),
                patch.object(service, "_storage_context", return_value=MagicMock()),
                patch.object(service, "_current_asset", return_value=raw_asset),
                patch.object(service, "_absolute_path_for_asset", return_value=video),
                patch.object(service, "_clear_previous_ocr_rows"),
                patch.object(service, "_mark_previous_ocr_assets_non_current") as mark_non_current,
                patch.object(service, "_persist_detections", return_value=0),
                patch.object(service, "_persist_json_asset"),
                patch.object(service, "_persist_file_asset") as persist_file,
                patch.object(service, "_restore_latest_cleaned_current", return_value=prior_cleaned) as restore,
                patch(
                    "src.ocr_pipeline.services.ocr_service.run_hardsub_phases_1_to_4",
                    return_value=e2e,
                ),
            ):
                result = service.run_pipeline(
                    OcrRequest(source_video_id=source_id, clean_hardsub=True, sample_fps=1.0),
                )

        mark_non_current.assert_called()
        # Must not wipe CLEANED_VIDEO currency before we know a new plate exists.
        kwargs = mark_non_current.call_args.kwargs
        self.assertFalse(kwargs.get("include_cleaned", True))
        persist_file.assert_not_called()
        restore.assert_called_once_with(source_id)
        self.assertEqual(result.cleaned_video_asset_id, str(prior_cleaned.id))
        self.assertIn("clean_skipped_no_hardsub", result.warnings)
        self.assertIn("no_hardsub_detected", result.warnings)
        self.assertFalse(result.clean_produced)


if __name__ == "__main__":
    unittest.main()
