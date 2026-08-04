from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.services.render_service import RenderService
from src.render_pipeline.types import RenderRequest


def _service(source):
    service = object.__new__(RenderService)
    service.db = MagicMock()
    service.storage = SimpleNamespace()
    service._load_source_video = lambda _source_id: source
    return service


def test_quality_render_creation_fails_closed_before_visual_approval() -> None:
    source = SimpleNamespace(id=uuid4(), workspace_id=uuid4(), metadata_json={"quality_localization": {}})
    service = _service(source)
    with patch(
        "src.services.quality_localization_service.QualityLocalizationService.summary",
        return_value={"workflow_stage": "WAITING_VISUAL_REVIEW", "can_render_final": False},
    ), patch("src.render_pipeline.services.render_service.JobService.create_job") as create:
        with pytest.raises(RenderPipelineError) as raised:
            service.create_render_job(
                RenderRequest(
                    source_video_id=source.id,
                    workflow_version="QUALITY_LOCALIZATION_V24_1",
                )
            )

    assert raised.value.code == RenderPipelineErrorCode.QUALITY_REVIEW_REQUIRED
    create.assert_not_called()


def test_quality_render_creation_reuses_active_recipe_reference() -> None:
    reference = {
        "release_label": "V24.1",
        "recipe_sha256": "a" * 64,
        "file_sha256": "b" * 64,
        "artifact_name": "pipeline_recipe_" + "a" * 64 + ".json",
    }
    source = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        metadata_json={"quality_localization": {"pipeline_recipe_lock": reference}},
    )
    job = SimpleNamespace(id=uuid4(), payload_json={}, context_json={})
    service = _service(source)
    with patch(
        "src.services.quality_localization_service.QualityLocalizationService.summary",
        return_value={"workflow_stage": "VISUAL_APPROVED", "can_render_final": True},
    ), patch(
        "src.render_pipeline.services.render_service.JobService.create_job",
        return_value=job,
    ) as create, patch(
        "src.services.pipeline_recipe_runtime.bind_job_to_recipe_reference"
    ) as bind:
        created = service.create_render_job(RenderRequest(source_video_id=source.id))

    assert created is job
    assert create.call_args.kwargs["payload_json"]["workflow_version"] == "QUALITY_LOCALIZATION_V24_1"
    bind.assert_called_once_with(job, reference)
    service.db.commit.assert_called_once()
