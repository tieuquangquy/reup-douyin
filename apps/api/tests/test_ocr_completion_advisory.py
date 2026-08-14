"""OCR completion advisory: empty hard-sub must not look like a fresh clean success."""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.enums import JobType
from src.ocr_pipeline.completion_advisory import (
    OCR_NO_HARDSUB_OUTPUT,
    ocr_completion_advisory,
    ocr_run_produced_cleaned_video,
)
from src.services import job_runner


class OcrCompletionAdvisoryTests(unittest.TestCase):
    def test_advisory_when_clean_skipped(self) -> None:
        code_message = ocr_completion_advisory(["no_hardsub_detected", "clean_skipped_no_hardsub"])
        self.assertIsNotNone(code_message)
        assert code_message is not None
        self.assertEqual(code_message[0], OCR_NO_HARDSUB_OUTPUT)
        self.assertIn("clean skipped", code_message[1].lower())

    def test_no_advisory_when_clean_ok(self) -> None:
        self.assertIsNone(ocr_completion_advisory([]))
        self.assertIsNone(ocr_completion_advisory(["hardsub_unstable"]))

    def test_clean_produced_flag(self) -> None:
        self.assertFalse(ocr_run_produced_cleaned_video(["clean_skipped_no_hardsub"], cleaned_asset_id="x"))
        self.assertTrue(ocr_run_produced_cleaned_video([], cleaned_asset_id="x"))
        self.assertFalse(ocr_run_produced_cleaned_video([], cleaned_asset_id=None))

    def test_job_runner_applies_ocr_advisory_on_completed(self) -> None:
        source = inspect.getsource(job_runner.JobRunner)
        self.assertIn("ocr_completion_advisory", source)
        self.assertIn("OCR_NO_HARDSUB_OUTPUT", source)
        self.assertIn("result_json", source)

        job = SimpleNamespace(
            job_type=JobType.ANALYZE_OCR,
            result_json=None,
            error_code=None,
            error_message=None,
            steps=[
                SimpleNamespace(
                    result_json={"warnings": ["clean_skipped_no_hardsub"]},
                    output_json=None,
                )
            ],
        )
        runner = job_runner.JobRunner(MagicMock())
        self.assertTrue(runner._apply_completion_advisory(job))
        self.assertEqual(job.error_code, OCR_NO_HARDSUB_OUTPUT)
        self.assertEqual(
            job.result_json["completion_advisory"]["code"],
            OCR_NO_HARDSUB_OUTPUT,
        )


if __name__ == "__main__":
    unittest.main()
