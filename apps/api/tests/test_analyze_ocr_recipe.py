from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.services.analyze_ocr_recipe import (
    ANALYZE_OCR_RELEASE_LABEL,
    ANALYZE_OCR_RECIPE_REF_KEY,
    AnalyzeOcrRecipeError,
    assert_job_analyze_ocr_recipe,
    bind_job_to_official_analyze_ocr_recipe,
    load_current_analyze_ocr_recipe,
)


def _sha(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _write_recipe(
    root: Path,
    *,
    policy: str = "audio_visual_temporal_policy_v12_epoch_complete_cover",
) -> Path:
    payload = {
        "schema_version": "analyze_ocr_recipe_lock_v1",
        "status": "LOCKED_AS_OFFICIAL_DEFAULT",
        "release_label": ANALYZE_OCR_RELEASE_LABEL,
        "phase1": {
            "analysis_engine": "audio_visual_temporal_v1",
            "analysis_policy_version": policy,
        },
        "phase2": {"provider": "local", "network_calls_allowed": 0},
        "claims": {"official_frontend_default": True, "network_calls_allowed": 0},
    }
    payload["recipe_sha256"] = _sha(payload)
    current = root / "analyze_ocr_recipe_current.json"
    versioned = root / f"analyze_ocr_recipe_{payload['recipe_sha256']}.json"
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    current.write_text(encoded, encoding="utf-8")
    versioned.write_text(encoded, encoding="utf-8")
    return current


class AnalyzeOcrRecipeTests(unittest.TestCase):
    def test_current_recipe_is_content_addressed_and_matches_installed_v12(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = _write_recipe(Path(tmp))
            with patch(
                "src.services.analyze_ocr_recipe.current_recipe_path",
                return_value=current,
            ):
                authority = load_current_analyze_ocr_recipe()
        self.assertEqual(authority.release_label, ANALYZE_OCR_RELEASE_LABEL)
        self.assertEqual(
            authority.analysis_policy_version,
            "audio_visual_temporal_policy_v12_epoch_complete_cover",
        )

    def test_recipe_fails_closed_when_installed_policy_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = _write_recipe(Path(tmp), policy="legacy_policy")
            with patch(
                "src.services.analyze_ocr_recipe.current_recipe_path",
                return_value=current,
            ), self.assertRaises(AnalyzeOcrRecipeError):
                load_current_analyze_ocr_recipe()

    def test_job_binding_and_runtime_contract_are_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = _write_recipe(Path(tmp))
            job = SimpleNamespace(
                job_type="ANALYZE_OCR",
                payload_json={
                    "analysis_engine": "audio_visual_temporal_v1",
                    "use_master_phase1": True,
                },
                context_json=None,
            )
            with patch(
                "src.services.analyze_ocr_recipe.current_recipe_path",
                return_value=current,
            ):
                reference = bind_job_to_official_analyze_ocr_recipe(job)
                assert_job_analyze_ocr_recipe(job)
        self.assertEqual(reference["release_label"], ANALYZE_OCR_RELEASE_LABEL)
        self.assertEqual(
            job.payload_json[ANALYZE_OCR_RECIPE_REF_KEY]["recipe_sha256"],
            reference["recipe_sha256"],
        )

    def test_job_with_wrong_engine_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = _write_recipe(Path(tmp))
            job = SimpleNamespace(
                job_type="ANALYZE_OCR",
                payload_json={"analysis_engine": "legacy", "use_master_phase1": True},
                context_json=None,
            )
            with patch(
                "src.services.analyze_ocr_recipe.current_recipe_path",
                return_value=current,
            ):
                bind_job_to_official_analyze_ocr_recipe(job)
                with self.assertRaises(AnalyzeOcrRecipeError):
                    assert_job_analyze_ocr_recipe(job)


if __name__ == "__main__":
    unittest.main()
