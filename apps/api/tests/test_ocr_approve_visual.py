"""Approve visual clean must persist (commit), not only flush."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import MediaAssetType
from src.ocr_pipeline.services.ocr_service import OcrPipelineService


class OcrApproveVisualTests(unittest.TestCase):
    def test_approve_visual_commits_metadata(self) -> None:
        source_id = uuid4()
        cleaned = SimpleNamespace(id=uuid4(), metadata_json={})
        events = SimpleNamespace(id=uuid4(), metadata_json={"hardsub_events": []})

        db = MagicMock()
        service = OcrPipelineService(db, storage=MagicMock(), ocr_provider=MagicMock())

        def current_asset(_sid, asset_type):
            if asset_type == MediaAssetType.CLEANED_VIDEO:
                return cleaned
            if asset_type == MediaAssetType.OCR_EVENTS:
                return events
            return None

        with patch.object(service, "_current_asset", side_effect=current_asset):
            with patch.object(
                service,
                "get_ocr_summary",
                return_value={
                    "source_video_id": str(source_id),
                    "visual_approved": True,
                    "clean_produced": True,
                    "hardsub_events": [],
                    "warnings": [],
                },
            ):
                summary = service.approve_visual(source_id)

        self.assertTrue(cleaned.metadata_json.get("visual_approved"))
        self.assertTrue(events.metadata_json.get("visual_approved"))
        db.commit.assert_called_once()
        self.assertTrue(summary["visual_approved"])

    def test_summary_visual_approved_from_events_when_no_cleaned(self) -> None:
        source_id = uuid4()
        events = SimpleNamespace(
            id=uuid4(),
            storage_key="ocr/events.json",
            metadata_json={"visual_approved": True, "hardsub_events": [], "warnings": []},
        )
        db = MagicMock()
        db.scalar.return_value = 0
        storage = MagicMock()
        storage.exists.return_value = False
        service = OcrPipelineService(db, storage=storage, ocr_provider=MagicMock())

        def current_asset(_sid, asset_type):
            if asset_type == MediaAssetType.OCR_EVENTS:
                return events
            return None

        with patch.object(service, "_current_asset", side_effect=current_asset):
            summary = service.get_ocr_summary(source_id)

        self.assertTrue(summary["visual_approved"])


if __name__ == "__main__":
    unittest.main()
