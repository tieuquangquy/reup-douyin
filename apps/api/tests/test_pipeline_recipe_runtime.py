from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.services.adaptive_final_db_handoff import LockedRecipeAuthority
from src.services.pipeline_recipe_runtime import (
    RECIPE_LOCK_REF_KEY,
    RuntimeRecipeError,
    assert_job_recipe_workflow_contract,
    bind_item_to_current_recipe,
    bind_job_to_item_recipe,
    ensure_item_recipe_binding,
)


def authority() -> LockedRecipeAuthority:
    return LockedRecipeAuthority(
        source_path=Path("pipeline_recipe_" + "a" * 64 + ".json"),
        schema_version="pipeline_recipe_lock_v3",
        release_label="V24",
        recipe_sha256="a" * 64,
        file_sha256="b" * 64,
        status="LOCKED_FOR_CONTROLLED_PILOT",
        validation_boundary="PHASE4_PREFLIGHT",
    )


class PipelineRecipeRuntimeTests(unittest.TestCase):
    def test_v24_quality_job_cannot_run_legacy_workflow(self) -> None:
        job = SimpleNamespace(
            job_type="ANALYZE_OCR",
            payload_json={
                "workflow_version": "legacy_media_e2e_v1",
                RECIPE_LOCK_REF_KEY: {
                    "release_label": "V24.1",
                    "artifact_name": "pipeline_recipe_" + "a" * 64 + ".json",
                },
            },
            context_json=None,
        )
        with patch(
            "src.services.pipeline_recipe_runtime.load_bound_recipe_authority",
            return_value=authority(),
        ), patch(
            "src.services.analyze_ocr_recipe.assert_job_analyze_ocr_recipe",
        ), self.assertRaises(RuntimeRecipeError):
            assert_job_recipe_workflow_contract(job)

    def test_v24_quality_job_accepts_quality_workflow(self) -> None:
        job = SimpleNamespace(
            job_type="ANALYZE_OCR",
            payload_json={
                "workflow_version": "QUALITY_LOCALIZATION_V24_1",
                RECIPE_LOCK_REF_KEY: {
                    "release_label": "V24.1",
                    "artifact_name": "pipeline_recipe_" + "a" * 64 + ".json",
                },
            },
            context_json=None,
        )
        with patch(
            "src.services.pipeline_recipe_runtime.load_bound_recipe_authority",
            return_value=authority(),
        ), patch(
            "src.services.analyze_ocr_recipe.assert_job_analyze_ocr_recipe",
        ):
            assert_job_recipe_workflow_contract(job)

    def test_bind_is_idempotent_and_writes_portable_reference(self) -> None:
        item = SimpleNamespace(id="item-1", metadata_json={})
        locked = authority()
        with patch(
            "src.services.pipeline_recipe_runtime.load_current_recipe_authority",
            return_value=locked,
        ) as load_current, patch(
            "src.services.pipeline_recipe_runtime.load_bound_recipe_authority",
            return_value=locked,
        ):
            first = bind_item_to_current_recipe(item)
            second = ensure_item_recipe_binding(item)

        self.assertEqual(first, second)
        self.assertEqual(load_current.call_count, 1)
        self.assertEqual(item.metadata_json[RECIPE_LOCK_REF_KEY]["release_label"], "V24")
        self.assertEqual(item.metadata_json[RECIPE_LOCK_REF_KEY]["recipe_sha256"], "a" * 64)

    def test_each_stage_job_receives_the_same_recipe_reference(self) -> None:
        item = SimpleNamespace(
            id="item-1",
            metadata_json={RECIPE_LOCK_REF_KEY: {
                "schema_version": "pipeline_recipe_lock_ref_v1",
                "artifact_name": "pipeline_recipe_" + "a" * 64 + ".json",
                "release_label": "V24",
                "recipe_sha256": "a" * 64,
                "file_sha256": "b" * 64,
                "status": "LOCKED_FOR_CONTROLLED_PILOT",
                "validation_boundary": "PHASE4_PREFLIGHT",
            }},
        )
        job = SimpleNamespace(context_json=None, payload_json={"source_video_id": "video-1"})
        with patch(
            "src.services.pipeline_recipe_runtime.load_bound_recipe_authority",
            return_value=authority(),
        ):
            reference = bind_job_to_item_recipe(job, item)

        self.assertEqual(job.context_json[RECIPE_LOCK_REF_KEY], reference)
        self.assertEqual(job.payload_json[RECIPE_LOCK_REF_KEY], reference)


if __name__ == "__main__":
    unittest.main()
