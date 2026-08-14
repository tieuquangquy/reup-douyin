from __future__ import annotations

import pytest
from pydantic import ValidationError
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.api.routes.ocr import OcrCreateRequest
from src.ocr_pipeline.services.ocr_service import OcrPipelineService
from src.ocr_pipeline.types import OcrRequest
from src.services.quality_localization_service import QUALITY_ANALYSIS_ENGINE


def test_ocr_create_defaults_to_local_temporal_engine() -> None:
    request = OcrCreateRequest(source_video_id="00000000-0000-0000-0000-000000000001")
    assert request.analysis_engine == QUALITY_ANALYSIS_ENGINE


def test_ocr_create_rejects_unknown_engine() -> None:
    with pytest.raises(ValidationError):
        OcrCreateRequest(
            source_video_id="00000000-0000-0000-0000-000000000001",
            analysis_engine="cloud_magic",
        )


def test_quality_review_job_cannot_fall_back_to_legacy_v58_engine() -> None:
    db = MagicMock()
    service = OcrPipelineService(db)
    source_id = uuid4()
    source = SimpleNamespace(id=source_id, workspace_id=uuid4())
    job = SimpleNamespace(id=uuid4(), payload_json={}, context_json=None)
    authority = SimpleNamespace(analysis_engine=QUALITY_ANALYSIS_ENGINE)

    with (
        patch.object(service, "_load_source_video", return_value=source),
        patch(
            "src.ocr_pipeline.services.ocr_service.JobService.create_job",
            return_value=job,
        ) as create_job,
        patch(
            "src.services.analyze_ocr_recipe.load_current_analyze_ocr_recipe",
            return_value=authority,
        ),
        patch(
            "src.services.pipeline_recipe_runtime.bind_job_to_current_recipe",
            return_value={},
        ),
    ):
        service.create_ocr_job(
            OcrRequest(
                source_video_id=source_id,
                workflow_version="QUALITY_LOCALIZATION_V24_1",
                workflow_action="approve_ocr",
            )
        )

    payload = create_job.call_args.kwargs["payload_json"]
    assert payload["analysis_engine"] == QUALITY_ANALYSIS_ENGINE
    assert payload["workflow_action"] == "approve_ocr"
