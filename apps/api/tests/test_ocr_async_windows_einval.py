"""Windows asyncio OCR batch must not die on ProactorEventLoop EINVAL teardown."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.media_pipeline.ocr_filtering.async_batch import process_all_frames_sync
from src.media_pipeline.ocr_filtering.types import FrameOcrDetection


class WindowsAsyncOcrLoopTests(unittest.TestCase):
    def test_sync_batch_uses_selector_policy_on_windows(self) -> None:
        """Proactor + aiohttp teardown on Win32 raises OSError Errno 22 after long OCR."""
        if sys.platform != "win32":
            self.skipTest("Windows-only event loop policy")

        seen: list[object] = []

        def _capture_policy(policy: object) -> None:
            seen.append(policy)

        fake_detection = FrameOcrDetection(frame_width=10, frame_height=10, boxes=[])

        with patch(
            "src.media_pipeline.ocr_filtering.async_batch.asyncio.set_event_loop_policy",
            side_effect=_capture_policy,
        ) as set_policy:
            with patch(
                "src.media_pipeline.ocr_filtering.async_batch.asyncio.run",
                return_value=[fake_detection],
            ) as run_mock:
                out = process_all_frames_sync(
                    [Path("frame.jpg")],
                    endpoint_url="https://example.test/predict",
                )

        self.assertEqual(out, [fake_detection])
        self.assertTrue(set_policy.called)
        self.assertTrue(
            any(isinstance(p, asyncio.WindowsSelectorEventLoopPolicy) for p in seen),
            f"expected WindowsSelectorEventLoopPolicy, got {seen!r}",
        )
        run_mock.assert_called_once()

    def test_sync_batch_maps_loop_einval_to_ocr_error(self) -> None:
        from src.media_pipeline.ocr_filtering.errors import (
            OcrFilteringError,
            OcrFilteringErrorCode,
        )

        with patch(
            "src.media_pipeline.ocr_filtering.async_batch.asyncio.run",
            side_effect=OSError(22, "Invalid argument"),
        ):
            with self.assertRaises(OcrFilteringError) as ctx:
                process_all_frames_sync(
                    [Path("frame.jpg")],
                    endpoint_url="https://example.test/predict",
                )
        self.assertEqual(ctx.exception.code, OcrFilteringErrorCode.OCR_PROVIDER_FAILED)
        self.assertIn("Invalid argument", ctx.exception.message)


class DeferOcrClearOnFailureTests(unittest.TestCase):
    def test_run_pipeline_does_not_clear_rows_before_e2e_success(self) -> None:
        """Fail mid-OCR must not wipe prior detections (force_refresh used to clear first)."""
        from uuid import uuid4
        from unittest.mock import MagicMock

        from src.ocr_pipeline.services.ocr_service import OcrPipelineService
        from src.ocr_pipeline.types import OcrRequest
        from src.media_pipeline.ocr_filtering.errors import (
            OcrFilteringError,
            OcrFilteringErrorCode,
        )

        db = MagicMock()
        service = OcrPipelineService(db)
        source_id = uuid4()
        source = MagicMock()
        source.id = source_id
        source.workspace_id = uuid4()
        asset = MagicMock()
        asset.metadata_json = {
            "absolute_path": r"C:\Users\PC\Desktop\reup_douyin\data\storage\x.mp4"
        }

        clear_calls: list[object] = []

        def _track_clear(vid: object) -> None:
            clear_calls.append(vid)

        with patch.object(service, "_load_source_video", return_value=source):
            with patch.object(service, "_storage_context", return_value=MagicMock()):
                with patch.object(service, "_current_asset", return_value=asset):
                    with patch.object(
                        service, "_absolute_path_for_asset", return_value=Path("x.mp4")
                    ):
                        with patch.object(
                            service, "_clear_previous_ocr_rows", side_effect=_track_clear
                        ):
                            with patch.object(service, "_mark_previous_ocr_assets_non_current"):
                                with patch(
                                    "src.ocr_pipeline.services.ocr_service.run_hardsub_phases_1_to_4",
                                    side_effect=OcrFilteringError(
                                        OcrFilteringErrorCode.OCR_PROVIDER_FAILED,
                                        "boom",
                                    ),
                                ):
                                    with patch(
                                        "src.ocr_pipeline.services.ocr_service.Path.is_file",
                                        return_value=True,
                                    ):
                                        with self.assertRaises(Exception):
                                            service.run_pipeline(
                                                OcrRequest(
                                                    source_video_id=source_id,
                                                    force_refresh=True,
                                                    clean_hardsub=True,
                                                )
                                            )

        self.assertEqual(
            clear_calls,
            [],
            "OCR rows must not be cleared when E2E fails before persist",
        )


if __name__ == "__main__":
    unittest.main()
