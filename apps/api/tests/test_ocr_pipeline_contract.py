"""OCR route + job template contract tests."""

from __future__ import annotations

import inspect
import unittest

from src.api.routes import ocr as ocr_routes
from src.enums import JobType, MediaAssetType
from src.ocr_pipeline.services import ocr_service
from src.services import job_runner, job_templates
from src.storage import path_strategy


class OcrPipelineContractTests(unittest.TestCase):
    def test_analyze_ocr_template_has_persist_and_clean_steps(self) -> None:
        steps = job_templates.STEP_TEMPLATES[JobType.ANALYZE_OCR]
        keys = [step.key for step in steps]
        self.assertIn("sample_frames", keys)
        self.assertIn("remove_hardsub", keys)
        self.assertIn("persist_outputs", keys)

    def test_job_runner_wires_analyze_ocr(self) -> None:
        source = inspect.getsource(job_runner.JobRunner)
        self.assertIn('ANALYZE_OCR', source)
        self.assertIn("OcrPipelineService", source)
        self.assertIn('persist_outputs', source)
        self.assertIn("on_progress", source)
        self.assertIn("ocr_phase", source)

    def test_ocr_routes_expose_create_summary_approve(self) -> None:
        source = inspect.getsource(ocr_routes)
        self.assertIn('@router.post("/ocr"', source)
        self.assertIn("ocr-summary", source)
        self.assertIn("ocr-visual-approve", source)

    def test_cleaned_and_events_asset_types_mapped(self) -> None:
        self.assertEqual(MediaAssetType.CLEANED_VIDEO.value, "CLEANED_VIDEO")
        self.assertEqual(MediaAssetType.OCR_EVENTS.value, "OCR_EVENTS")
        self.assertEqual(path_strategy.ASSET_SUBDIRECTORIES[MediaAssetType.CLEANED_VIDEO], "cleaned")
        self.assertEqual(path_strategy.ASSET_SUBDIRECTORIES[MediaAssetType.OCR_EVENTS], "ocr")

    def test_ocr_service_persists_events_and_optional_clean(self) -> None:
        source = inspect.getsource(ocr_service.OcrPipelineService.run_pipeline)
        self.assertIn("clean_hardsub", source)
        self.assertIn("on_progress", source)
        e2e_source = inspect.getsource(ocr_service.OcrPipelineService._run_media_e2e_pipeline)
        self.assertIn("run_hardsub_phases_1_to_4", e2e_source)
        self.assertIn("OCR_EVENTS", e2e_source)
        self.assertIn("CLEANED_VIDEO", e2e_source)
        self.assertIn("self.db.commit()", e2e_source)
        detect_source = inspect.getsource(ocr_service.OcrPipelineService._run_detect_only_pipeline)
        self.assertIn("sample_video_frames", detect_source)
        self.assertIn("crop_bottom_band_image", detect_source)
        self.assertIn("group_hard_sub_events", detect_source)
        frame_sampler_source = inspect.getsource(
            __import__("src.ocr_pipeline.frame_sampler", fromlist=["sample_video_frames"]).sample_video_frames
        )
        self.assertIn("extract_video_frames_detailed", frame_sampler_source)
        self.assertIn("normalize_sample_fps", frame_sampler_source)
        clean_source = inspect.getsource(
            __import__("src.ocr_pipeline.clean_hardsub", fromlist=["blur_hard_sub_band"]).blur_hard_sub_band
        )
        self.assertIn("build_timed_cover_vf", clean_source)
        self.assertIn("0:v:0", clean_source)
        vf_source = inspect.getsource(
            __import__("src.ocr_pipeline.clean_hardsub", fromlist=["build_timed_cover_vf"]).build_timed_cover_vf
        )
        self.assertIn("drawbox=", vf_source)
        self.assertIn("enable=", vf_source)
        self.assertIn("between(t", vf_source)
        self.assertNotIn("boxblur=", vf_source)


if __name__ == "__main__":
    unittest.main()
