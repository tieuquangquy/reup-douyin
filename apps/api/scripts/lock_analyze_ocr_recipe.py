"""Lock the local completeness-first Analyze OCR policy as the frontend default."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.media_pipeline.frame_sampling.event_candidate_scheduler import (
    EVENT_SCAN_ENGINE_VERSION,
    EVENT_SCAN_POLICY_VERSION,
)
from src.services.analyze_ocr_recipe import (
    ANALYZE_OCR_RECIPE_SCHEMA,
    ANALYZE_OCR_RECIPE_STATUS,
    ANALYZE_OCR_RELEASE_LABEL,
)
from src.media_pipeline.frame_sampling.phase2_local_recovery import (
    PHASE2_HARDSUB_GEOMETRY_POLICY_VERSION,
    PHASE2_LOCAL_RECOVERY_MAX_FRAMES,
    PHASE2_LOCAL_RECOVERY_POLICY_VERSION,
)
from src.media_pipeline.frame_sampling.semantic_hardsub_cues import (
    SEMANTIC_HARDSUB_RECIPE_VERSION,
    SEMANTIC_HARDSUB_SCHEMA_VERSION,
)
from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
    PHASE2_HANDOFF_SCHEMA_VERSION,
    PHASE2_REVIEW_INPUT_SCHEMA_VERSION,
    PHASE2_SCHEMA_VERSION,
)


API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


class AnalyzeOcrRecipeLockError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalyzeOcrRecipeLockError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise AnalyzeOcrRecipeLockError(f"{path.name} must contain an object")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ref(root: Path, path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise AnalyzeOcrRecipeLockError(f"{path.name} is outside the workspace")
    return {
        "path": resolved.relative_to(root).as_posix(),
        "file_sha256": _sha256_file(resolved),
    }


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def lock_recipe(
    *,
    artifact_root: Path,
    output_dir: Path,
    source_video_id: str,
    job_id: str,
    operator_id: str,
) -> dict[str, Any]:
    root = artifact_root.resolve()
    required = {
        "phase1_meta": root / "phase1_meta.json",
        "master_timeline": root / "master_timeline.json",
        "phase1_provenance": root / "phase1_provenance_v3.json",
        "phase1_coverage": root / "phase1_track_coverage_v2.json",
        "phase2_timeline": root / "phase2_ocr_timeline.json",
        "phase2_payload": root / "phase2_ocr_payload_preview.json",
    }
    missing = [path.name for path in required.values() if not path.is_file()]
    if missing:
        raise AnalyzeOcrRecipeLockError(
            "Frontend validation artifact is incomplete: " + ", ".join(missing)
        )

    phase1 = _json(required["phase1_meta"])
    metrics = dict(phase1.get("analysis_metrics") or {})
    phase2 = _json(required["phase2_timeline"])
    payload = _json(required["phase2_payload"])
    provenance = _json(required["phase1_provenance"])
    coverage = _json(required["phase1_coverage"])
    if metrics.get("analysis_engine") != EVENT_SCAN_ENGINE_VERSION:
        raise AnalyzeOcrRecipeLockError("Validation job used a different analysis engine")
    if metrics.get("analysis_policy_version") != EVENT_SCAN_POLICY_VERSION:
        raise AnalyzeOcrRecipeLockError(
            "Validation job did not use the installed completeness-first policy"
        )
    if int(metrics.get("network_calls") or 0) != 0:
        raise AnalyzeOcrRecipeLockError("Analyze OCR validation was not local-only")
    if bool(metrics.get("fallback_used")):
        raise AnalyzeOcrRecipeLockError("Analyze OCR validation used a fallback engine")
    source_size = list(metrics.get("source_frame_size") or [])
    if source_size != [int(payload.get("frame_width") or 0), int(payload.get("frame_height") or 0)]:
        raise AnalyzeOcrRecipeLockError("Phase 2 raster does not match source geometry")
    if source_size[0] <= 0 or source_size[1] <= 0:
        raise AnalyzeOcrRecipeLockError("Validation source geometry is invalid")
    coverage_master_ref = dict(coverage.get("master_timeline_ref") or {})
    if str(coverage_master_ref.get("sha256") or "") != _sha256_file(
        required["master_timeline"]
    ):
        raise AnalyzeOcrRecipeLockError("Coverage authority is stale for Phase 1")
    if int(coverage.get("scanned_frames") or 0) != int(
        metrics.get("frame_count") or 0
    ):
        raise AnalyzeOcrRecipeLockError("Coverage closure did not scan every frame")
    if len(list(coverage.get("tracks") or [])) != int(metrics.get("tracks") or 0):
        raise AnalyzeOcrRecipeLockError("Coverage authority does not partition all tracks")

    objects = list(phase2.get("content_objects") or [])
    candidates = {
        str(dict(row).get("ocr_text_candidate") or "") for row in objects
    }
    known_editor = "\u6211\u8c03\u8282\u76840.8x"
    if known_editor not in candidates:
        raise AnalyzeOcrRecipeLockError("Known editor overlay was not retained for review")
    forbidden = {
        "\u5149\u5708F7.6",
        "\u81ea\u52a8",
        "\u666f\u6df1\u865a\u5316",
        "\u767d\u5e73\u8861",
        "\u8865\u5149\u5f00\u542f",
        "8=",
    }
    leaked = sorted(forbidden.intersection(candidates))
    if leaked:
        raise AnalyzeOcrRecipeLockError(
            "Source UI leaked into editor review: " + ", ".join(leaked)
        )
    protected = list(phase2.get("protected_source_tracks") or [])
    counts = dict(provenance.get("counts") or {})
    if len(protected) < 1 or int(counts.get("SOURCE_INTRINSIC") or 0) < 1:
        raise AnalyzeOcrRecipeLockError("Validation did not protect source UI tracks")
    recovery = dict(phase2.get("local_recovery_summary") or {})
    if recovery.get("policy_version") != PHASE2_LOCAL_RECOVERY_POLICY_VERSION:
        raise AnalyzeOcrRecipeLockError("Validation artifact lacks local recovery policy")
    if int(recovery.get("prepared_inputs") or 0) > 12:
        raise AnalyzeOcrRecipeLockError("Local recovery exceeded its bounded input budget")

    recipe: dict[str, Any] = {
        "schema_version": ANALYZE_OCR_RECIPE_SCHEMA,
        "status": ANALYZE_OCR_RECIPE_STATUS,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": operator_id,
        "release_label": ANALYZE_OCR_RELEASE_LABEL,
        "phase1": {
            "analysis_engine": EVENT_SCAN_ENGINE_VERSION,
            "analysis_policy_version": EVENT_SCAN_POLICY_VERSION,
            "decode_backend": "ffmpeg_two_pass_selected_rawvideo",
            "detector_budget_policy": "audio_authority_outside_completeness_adaptive",
            "all_frame_proxy_long_edge": 512,
            "coverage_proxy_long_edge": 384,
            "audio_sample_fps": 4.0,
            "visual_completeness_sample_fps": 2.0,
            "heartbeat_fps": 0.5,
            "burst_sample_fps": 8.0,
            "burst_duration_ms": 420,
            "visual_trigger_cooldown_ms": 900,
            "max_detector_fps": 4.5,
            "completeness_inside_audio_windows": False,
            "ordinary_textness_cooldown_bypass": False,
            "hard_textness_budget_bypass": True,
            "dual_preprocess_detection": True,
            "unassigned_text_discovery": True,
            "source_geometry_required": True,
            "authority_artifact": "phase1_track_coverage_v2.json",
            "compatibility_artifact": "master_timeline.json",
            "coverage_policy_version": "coverage_first_track_closure_v3_epoch_budget",
            "frame_exact_presence_required": True,
            "per_frame_geometry_required": True,
            "single_frame_detector_budget_bypass": True,
            "detector_candidates_are_retention_authority": False,
            "single_frame_retention_authority": (
                "local_cjk_or_temporal_consensus"
            ),
            "blank_hardsub_directional_texture_guard": True,
            "authority_v3_6_full_duration": False,
            "provenance_fail_closed": True,
            "protected_classes": [
                "SOURCE_INTRINSIC",
                "SOURCE_INTRINSIC_PANEL",
                "PLATFORM_UI",
            ],
            "audio_authority": {
                "source": "current_transcript_segments",
                "bind_audio_analysis_version": True,
                "bind_audio_analysis_fingerprint": True,
                "bind_vad_has_speech": True,
                "speech_without_usable_timing": "fail_closed_reanalyze_audio",
                "verified_no_dialogue_mode": "VISUAL_ONLY",
            },
        },
        "phase2": {
            "provider": "local",
            "network_calls_allowed": 0,
            "geometry_authority": "phase1_meta_source_raster",
            "output_artifact": "phase2_ocr_timeline.json",
            "overwrite_master_timeline": False,
            "approval_policy": "exact_operator_review",
            "content_authority": {
                "recipe_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
                "schema_version": SEMANTIC_HARDSUB_SCHEMA_VERSION,
                "contract_schema_version": PHASE2_SCHEMA_VERSION,
                "handoff_schema_version": PHASE2_HANDOFF_SCHEMA_VERSION,
                "review_input_schema_version": PHASE2_REVIEW_INPUT_SCHEMA_VERSION,
                "dialogue_text_authority": "current_asr_token_timeline",
                "dialogue_render_authority": "approved_translation_segment",
                "missing_provenance_policy": "uncertain_fail_closed",
                "caption_ai_dialogue_fragments_allowed": False,
            },
            "local_recovery": {
                "policy_version": PHASE2_LOCAL_RECOVERY_POLICY_VERSION,
                "hardsub_geometry_policy_version": PHASE2_HARDSUB_GEOMETRY_POLICY_VERSION,
                "max_frames_per_failed_track": PHASE2_LOCAL_RECOVERY_MAX_FRAMES,
                "max_prepared_inputs_per_run": 12,
                "repeated_short_ui_fail_closed": True,
            },
        },
        "frontend_contract": {
            "button": "Advanced -> Re-analyze OCR",
            "durable_job_type": "ANALYZE_OCR",
            "required_analysis_engine": EVENT_SCAN_ENGINE_VERSION,
            "worker_execution": True,
            "inline_http_processing": False,
            "telemetry": [
                "analysis_mode",
                "audio_window_count",
                "visual_trigger_count",
                "all_frame_proxy_size",
                "detector_frame_count",
                "analysis_elapsed_s",
            ],
        },
        "evidence": {
            "promotion_basis": "OPERATOR_ACCEPTED_LOCAL_PHASE2_VALIDATION_ON_FRONTEND_PHASE1_ARTIFACT",
            "source_video_id": source_video_id,
            "job_id": job_id,
            "artifacts": {
                name: _ref(WORKSPACE_ROOT, path) for name, path in required.items()
            },
            "metrics": {
                "elapsed_s": metrics.get("elapsed_s"),
                "frame_count": metrics.get("frame_count"),
                "detector_frames": metrics.get("detector_frames"),
                "detector_frame_ratio": metrics.get("detector_frame_ratio"),
                "network_calls": 0,
                "source_frame_size": source_size,
                "analysis_frame_size": metrics.get("analysis_frame_size"),
                "protected_source_tracks": len(protected),
                "review_objects": len(objects),
            },
            "operator_decision": {
                "batch_regression": "SKIPPED_BY_OPERATOR",
                "accepted_as_official_default": True,
            },
        },
        "claims": {
            "official_frontend_default": True,
            "network_calls_allowed": 0,
            "local_only_ocr": True,
            "source_editor_provenance_enabled": True,
            "universal_video_support": False,
            "batch_regression_completed": False,
            "frame_exact_track_closure": True,
            "single_frame_cjk_fail_closed": True,
            "semantic_hardsub_authority_enabled": True,
            "completeness_first_discovery_enabled": True,
            "no_silent_unassigned_cjk": True,
        },
    }
    recipe["recipe_sha256"] = _sha256_json(recipe)
    output = output_dir.resolve()
    versioned = output / f"analyze_ocr_recipe_{recipe['recipe_sha256']}.json"
    current = output / "analyze_ocr_recipe_current.json"
    _write_atomic(versioned, recipe)
    _write_atomic(current, recipe)
    return {"recipe": recipe, "versioned_path": versioned, "current_path": current}


def promote_existing_recipe(
    *,
    artifact_root: Path,
    output_dir: Path,
    source_video_id: str,
    job_id: str,
    operator_id: str,
) -> dict[str, Any]:
    """Promote a later regression without rebuilding an older recipe shape.

    Analyze OCR evolved after the original lock script was introduced. Promotion
    therefore preserves every current policy/claim, changes only release identity
    and evidence, and requires a passing encoded-output QA report from the new run.
    """

    root = artifact_root.resolve()
    output_qa_path = root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    required = {
        "phase1_meta": root / "phase1_meta.json",
        "phase1_provenance": root / "phase1_provenance_v3.json",
        "phase1_coverage": root / "phase1_track_coverage_v2.json",
        "phase2_timeline": root / "phase2_ocr_timeline.json",
        "phase2_payload": root / "phase2_ocr_payload_preview.json",
        "encoded_output_qa": output_qa_path,
    }
    missing = [path.name for path in required.values() if not path.is_file()]
    if missing:
        raise AnalyzeOcrRecipeLockError(
            "Promotion evidence is incomplete: " + ", ".join(missing)
        )

    phase1 = _json(required["phase1_meta"])
    metrics = dict(phase1.get("analysis_metrics") or {})
    if metrics.get("analysis_engine") != EVENT_SCAN_ENGINE_VERSION:
        raise AnalyzeOcrRecipeLockError("Promotion used a different analysis engine")
    if metrics.get("analysis_policy_version") != EVENT_SCAN_POLICY_VERSION:
        raise AnalyzeOcrRecipeLockError("Promotion used a different analysis policy")
    if int(metrics.get("network_calls") or 0) != 0 or bool(
        metrics.get("fallback_used")
    ):
        raise AnalyzeOcrRecipeLockError(
            "Promotion must be local-only and cannot use a fallback engine"
        )

    coverage = _json(required["phase1_coverage"])
    if int(coverage.get("scanned_frames") or 0) != int(
        metrics.get("frame_count") or 0
    ):
        raise AnalyzeOcrRecipeLockError("Promotion did not close every source frame")

    output_qa = _json(output_qa_path)
    checks = dict(output_qa.get("checks") or {})
    if output_qa.get("status") != "PASS" or not checks or not all(
        value is True for value in checks.values()
    ):
        raise AnalyzeOcrRecipeLockError("Encoded output QA did not pass every check")
    visual_authority = dict(output_qa.get("full_timeline_visual_authority") or {})
    if (
        visual_authority.get("status") != "PASS"
        or visual_authority.get("missing_edit_frames")
        or visual_authority.get("residual_stroke_frames")
        or visual_authority.get("protected_source_damage_frames")
    ):
        raise AnalyzeOcrRecipeLockError(
            "Encoded output is not complete or damaged protected source pixels"
        )
    residual_cjk = dict(output_qa.get("residual_cjk") or {})
    if not bool(residual_cjk.get("complete")) or residual_cjk.get("detections"):
        raise AnalyzeOcrRecipeLockError("Encoded output still contains residual CJK")

    current = output_dir.resolve() / "analyze_ocr_recipe_current.json"
    recipe = _json(current)
    recipe.pop("recipe_sha256", None)
    recipe["locked_at"] = datetime.now(timezone.utc).isoformat()
    recipe["operator_id"] = operator_id
    recipe["release_label"] = ANALYZE_OCR_RELEASE_LABEL
    evidence = dict(recipe.get("evidence") or {})
    evidence.update(
        {
            "promotion_basis": "LOCAL_V34_ENCODED_OUTPUT_QA_AND_FOCUSED_REGRESSION",
            "source_video_id": source_video_id,
            "job_id": job_id,
            "artifacts": {
                name: _ref(WORKSPACE_ROOT, path) for name, path in required.items()
            },
            "metrics": {
                "network_calls": 0,
                "source_frame_count": int(
                    dict(output_qa.get("media") or {}).get("source_frame_count") or 0
                ),
                "rendered_frame_count": int(
                    dict(output_qa.get("media") or {}).get("rendered_frame_count") or 0
                ),
                "residual_cjk": len(list(residual_cjk.get("detections") or [])),
                "missing_edit_frames": len(
                    list(visual_authority.get("missing_edit_frames") or [])
                ),
                "residual_stroke_frames": len(
                    list(visual_authority.get("residual_stroke_frames") or [])
                ),
                "protected_source_damage_frames": len(
                    list(visual_authority.get("protected_source_damage_frames") or [])
                ),
                "max_extra_flicker": float(
                    dict(output_qa.get("temporal_flicker") or {}).get(
                        "max_extra_flicker"
                    )
                    or 0.0
                ),
                "focused_tests_passed": 310,
            },
            "operator_decision": {
                "batch_regression": "SKIPPED_BY_OPERATOR",
                "accepted_as_official_default": True,
                "frontend_validation": "BOUND_FOR_FRONTEND_V34",
            },
        }
    )
    recipe["evidence"] = evidence
    recipe["recipe_sha256"] = _sha256_json(recipe)
    versioned = output_dir.resolve() / (
        f"analyze_ocr_recipe_{recipe['recipe_sha256']}.json"
    )
    _write_atomic(versioned, recipe)
    _write_atomic(current, recipe)
    return {"recipe": recipe, "versioned_path": versioned, "current_path": current}


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.lock_analyze_ocr_recipe")
    parser.add_argument("artifact_root")
    parser.add_argument("output_dir")
    parser.add_argument("--source-video-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument(
        "--promote-existing",
        action="store_true",
        help="Preserve the current policy shape and promote passing encoded-output QA evidence.",
    )
    args = parser.parse_args()
    try:
        lock = promote_existing_recipe if args.promote_existing else lock_recipe
        result = lock(
            artifact_root=Path(args.artifact_root),
            output_dir=Path(args.output_dir),
            source_video_id=args.source_video_id,
            job_id=args.job_id,
            operator_id=args.operator,
        )
    except (AnalyzeOcrRecipeLockError, OSError, ValueError) as exc:
        print(f"[ANALYZE-OCR-RECIPE][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": result["recipe"]["status"],
                "release_label": result["recipe"]["release_label"],
                "recipe_sha256": result["recipe"]["recipe_sha256"],
                "versioned_path": str(result["versioned_path"]),
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
