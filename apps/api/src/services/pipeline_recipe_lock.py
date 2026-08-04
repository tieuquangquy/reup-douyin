"""Lock a controlled-pilot recipe to regression evidence and runtime settings."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.settings import get_settings
from src.media_pipeline.frame_sampling.phase1_policy import (
    FINAL_COVERAGE_FADE_TAIL_MAX_FRAMES,
    POST_REFINEMENT_SPARSE_COMPACT_MAX_HEIGHT_FRAC,
    POST_REFINEMENT_SPARSE_COMPACT_MAX_WIDTH_FRAC,
    POST_REFINEMENT_SPARSE_COMPACT_POLICY_VERSION,
    POST_REFINEMENT_TEXTURE_MAX_EDGE_DENSITY,
    POST_REFINEMENT_TEXTURE_MAX_LAPLACIAN_VARIANCE,
    POST_REFINEMENT_TEXTURE_MIN_SATURATION,
    POST_REFINEMENT_VISUAL_NORMALIZED_HEIGHT,
)
from src.media_pipeline.video_renderer.adaptive_output_qa import (
    RESIDUAL_CJK_POLICY_VERSION,
    SOURCE_INTRINSIC_TEXTURE_MAX_AREA,
    SOURCE_INTRINSIC_TEXTURE_MAX_MEAN_DELTA,
    SOURCE_INTRINSIC_TEXTURE_MAX_P95_DELTA,
    SOURCE_INTRINSIC_TEXTURE_MAX_PIXEL_ASPECT,
)
from src.media_pipeline.video_renderer.adaptive_typography import (
    DENSE_GROUP_LAYOUT_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.phase4_approvals import (
    NO_DIALOGUE_AUDIO_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.phase4_input_contract import (
    PHASE4_TIMING_NORMALIZATION_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.render_policy import RENDER_POLICY_VERSION
from src.media_pipeline.video_renderer.render_policy import (
    SEMANTIC_RENDER_DEDUP_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.source_text_provenance import (
    SOURCE_INTRINSIC_REGION_POLICY_VERSION,
)
from src.render_pipeline.audio_loudness import (
    TWO_PASS_ENCODE_TRUE_PEAK_DB,
    TWO_PASS_LOUDNESS_POLICY_VERSION,
)
from src.services.pipeline_tts_provenance import (
    PipelineTtsProvenanceError,
    verify_e2e_tts_provenance,
)


PIPELINE_RECIPE_LOCK_SCHEMA = "pipeline_recipe_lock_v3"
_RELEASE_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")


class PipelineRecipeLockError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_verified(path: Path, hash_field: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineRecipeLockError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise PipelineRecipeLockError(f"{path.name} must contain an object")
    claimed = str(payload.get(hash_field) or "")
    unsigned = dict(payload)
    unsigned.pop(hash_field, None)
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise PipelineRecipeLockError(f"{path.name} self-hash is invalid")
    return payload


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def lock_pipeline_recipe(
    *,
    workspace_root: str | Path,
    corpus_path: str | Path,
    report_path: str | Path,
    e2e_report_path: str | Path | None = None,
    closeout_path: str | Path | None = None,
    candidate_path: str | Path | None = None,
    output_dir: str | Path,
    operator_id: str,
    release_label: str | None = None,
    settings: object | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace_root).resolve()
    corpus_file = Path(corpus_path).resolve()
    report_file = Path(report_path).resolve()
    output = Path(output_dir).resolve()
    operator = str(operator_id or "").strip()
    release = str(release_label or "").strip() or None
    if not operator:
        raise PipelineRecipeLockError("Recipe lock requires an operator id")
    if release is not None and _RELEASE_LABEL_RE.fullmatch(release) is None:
        raise PipelineRecipeLockError("Recipe release label is invalid")
    corpus = _load_verified(corpus_file, "corpus_sha256")
    report = _load_verified(report_file, "report_sha256")
    e2e_report_file = (
        Path(e2e_report_path).resolve() if e2e_report_path is not None else None
    )
    e2e_report = (
        _load_verified(e2e_report_file, "report_sha256")
        if e2e_report_file is not None
        else None
    )
    closeout_file = (
        Path(closeout_path).resolve() if closeout_path is not None else None
    )
    closeout = (
        _load_verified(closeout_file, "closeout_sha256")
        if closeout_file is not None
        else None
    )
    candidate_file = (
        Path(candidate_path).resolve() if candidate_path is not None else None
    )
    candidate = (
        _load_verified(candidate_file, "candidate_sha256")
        if candidate_file is not None
        else None
    )
    case_count = int(report.get("case_count") or 0)
    phase1_accepted_count = int(
        report.get("phase1_accepted_count")
        if report.get("phase1_accepted_count") is not None
        else report.get("phase1_pass_count")
        or 0
    )
    phase2_execution_count = int(report.get("phase2_execution_pass_count") or 0)
    no_text_approved_count = int(report.get("no_text_approved_case_count") or 0)
    phase2_accepted_count = (
        phase2_execution_count
        if phase2_execution_count == case_count
        else phase2_execution_count + no_text_approved_count
    )
    if (
        str(report.get("status") or "") != "PASS_TO_OPERATOR_GATES"
        or phase1_accepted_count != case_count
        or phase2_accepted_count != case_count
        or int(report.get("operator_review_object_count") or 0) != 0
        or int(report.get("open_incident_count") or 0) != 0
    ):
        raise PipelineRecipeLockError(
            "Recipe can lock only after every case is accepted through Phase 2 "
            "execution or an operator-approved NO_TEXT bypass, with no open review "
            "objects or incidents"
        )
    if e2e_report is not None and (
        str(e2e_report.get("status") or "") != "PASS_CONTROLLED_E2E"
        or int(e2e_report.get("case_count") or 0) < 3
        or int(e2e_report.get("passed_count") or 0)
        != int(e2e_report.get("case_count") or 0)
        or int(e2e_report.get("db_handoff_ready_count") or 0)
        != int(e2e_report.get("case_count") or 0)
        or int(e2e_report.get("external_publish_triggered_count") or 0) != 0
    ):
        raise PipelineRecipeLockError(
            "End-to-end evidence requires at least three fully passing, retry-safe "
            "controlled-pilot cases with no external publish call"
        )
    runtime_tts: dict[str, Any] | None = None
    if e2e_report is not None and e2e_report_file is not None:
        try:
            runtime_tts = verify_e2e_tts_provenance(
                e2e_report=e2e_report,
                e2e_report_path=e2e_report_file,
                workspace_root=workspace,
            )
        except PipelineTtsProvenanceError as exc:
            raise PipelineRecipeLockError(
                f"End-to-end TTS runtime provenance is invalid: {exc}"
            ) from exc
    if candidate is not None:
        candidate_evidence = dict(candidate.get("evidence") or {})
        candidate_report = dict(candidate_evidence.get("batch_report") or {})
        candidate_e2e = dict(candidate_evidence.get("e2e_report") or {})
        candidate_render = dict(candidate.get("render") or {})
        candidate_layout = dict(candidate_render.get("layout_policies") or {})
        candidate_source = dict(
            candidate_render.get("source_text_provenance") or {}
        )
        candidate_tts = dict(candidate.get("tts") or {})
        if (
            str(candidate.get("schema_version") or "")
            != "pipeline_recipe_candidate_v1"
            or str(candidate.get("status") or "")
            != "VALIDATED_CANDIDATE_WITH_GAPS"
            or candidate.get("release_label") != release
            or list(candidate.get("blockers") or [])
            or dict(candidate.get("claims") or {}).get(
                "recipe_lock_recommended"
            )
            is not True
            or str(candidate_report.get("report_sha256") or "")
            != str(report.get("report_sha256") or "")
            or str(candidate_e2e.get("report_sha256") or "")
            != str((e2e_report or {}).get("report_sha256") or "")
            or str(candidate_render.get("role_policy_version") or "")
            != RENDER_POLICY_VERSION
            or float(candidate_render.get("background_mix_gain") or 0.0) != 1.0
            or str(candidate_layout.get("dense_group") or "")
            != DENSE_GROUP_LAYOUT_POLICY_VERSION
            or str(candidate_layout.get("semantic_dedup") or "")
            != SEMANTIC_RENDER_DEDUP_POLICY_VERSION
            or str(candidate_source.get("moving_object_region") or "")
            != SOURCE_INTRINSIC_REGION_POLICY_VERSION
            or runtime_tts is None
            or any(
                candidate_tts.get(key) != runtime_tts.get(key)
                for key in (
                    "provider",
                    "model_id",
                    "voice_id",
                    "language_code",
                    "speaking_rate",
                    "authority",
                    "runtime_config_sha256",
                    "verified_case_count",
                )
            )
        ):
            raise PipelineRecipeLockError(
                "Recipe candidate is stale, blocked, or does not match runtime policy"
            )
    if closeout is not None:
        closeout_counts = dict(closeout.get("counts") or {})
        closeout_claims = dict(closeout.get("claims") or {})
        closeout_evidence = dict(closeout.get("evidence") or {})
        closeout_report = dict(
            closeout_evidence.get("regression_report") or {}
        )
        closeout_corpus = dict(closeout_evidence.get("corpus") or {})
        closeout_preflight = dict(
            closeout_evidence.get("phase4_batch_preflight") or {}
        )
        closeout_state = dict(closeout_evidence.get("batch_state") or {})
        closeout_root = closeout_file.parent
        preflight_file = (
            closeout_root / str(closeout_preflight.get("path") or "")
        ).resolve()
        state_file = (
            closeout_root / str(closeout_state.get("path") or "")
        ).resolve()
        report_evidence_file = (
            closeout_root / str(closeout_report.get("path") or "")
        ).resolve()
        corpus_evidence_file = (
            workspace / str(closeout_corpus.get("path") or "")
        ).resolve()
        preflight_evidence_valid = (
            preflight_file.is_relative_to(closeout_root)
            and preflight_file.is_file()
            and _sha256_file(preflight_file)
            == str(closeout_preflight.get("sha256") or "")
            and str(
                _load_verified(
                    preflight_file, "batch_preflight_sha256"
                ).get("batch_preflight_sha256")
                or ""
            )
            == str(closeout_preflight.get("batch_preflight_sha256") or "")
        )
        state_evidence_valid = (
            state_file.is_relative_to(closeout_root)
            and state_file.is_file()
            and _sha256_file(state_file) == str(closeout_state.get("sha256") or "")
            and str(_load_verified(state_file, "run_sha256").get("run_sha256") or "")
            == str(closeout_state.get("run_sha256") or "")
        )
        corpus_evidence_valid = (
            corpus_evidence_file.is_relative_to(workspace)
            and corpus_evidence_file.is_file()
            and _sha256_file(corpus_evidence_file)
            == str(closeout_corpus.get("sha256") or "")
        )
        report_evidence_valid = (
            report_evidence_file == report_file
            and report_evidence_file.is_file()
            and _sha256_file(report_evidence_file)
            == str(closeout_report.get("sha256") or "")
        )
        if (
            str(closeout.get("status") or "")
            != "PASS_CONTROLLED_PHASE4_PREFLIGHT"
            or int(closeout.get("case_count") or 0) != case_count
            or int(closeout_counts.get("ready_for_phase4") or 0) != case_count
            or int(closeout_counts.get("blocked") or 0) != 0
            or int(closeout_counts.get("operator_touch_required") or 0) != 0
            or int(closeout_counts.get("operator_review_objects") or 0) != 0
            or int(closeout_counts.get("open_incidents") or 0) != 0
            or int(closeout_counts.get("residual_cjk_detections") or 0) != 0
            or int(closeout_counts.get("collision_events") or 0) != 0
            or not bool(
                closeout_claims.get(
                    "controlled_pilot_ready_through_phase4_preflight"
                )
            )
            or bool(closeout_claims.get("full_batch_end_to_end_pass"))
            or str(closeout_report.get("report_sha256") or "")
            != str(report.get("report_sha256") or "")
            or str(closeout_corpus.get("corpus_sha256") or "")
            != str(corpus.get("corpus_sha256") or "")
            or not preflight_evidence_valid
            or not state_evidence_valid
            or not corpus_evidence_valid
            or not report_evidence_valid
        ):
            raise PipelineRecipeLockError(
                "Phase 4 closeout is stale, incomplete, or over-claims its boundary"
            )
    full_batch_e2e_pass = bool(e2e_report) and bool(
        dict((e2e_report or {}).get("claims") or {}).get(
            "full_batch_end_to_end_pass"
        )
    )
    controlled_phase4_ready = bool(closeout) or full_batch_e2e_pass
    controlled_phase4_case_count = int(
        (closeout or {}).get("case_count")
        or (e2e_report or {}).get("case_count")
        or 0
    )
    current_path = output / "pipeline_recipe_current.json"
    if current_path.is_file():
        current = _load_verified(current_path, "recipe_sha256")
        evidence = dict(current.get("evidence") or {})
        current_corpus = dict(evidence.get("corpus") or {})
        current_report = dict(evidence.get("report") or {})
        current_e2e = dict(evidence.get("e2e_report") or {})
        current_closeout = dict(
            evidence.get("phase4_preflight_closeout") or {}
        )
        current_candidate = dict(evidence.get("recipe_candidate") or {})
        if (
            str(current.get("schema_version") or "")
            == PIPELINE_RECIPE_LOCK_SCHEMA
            and str(current.get("operator_id") or "") == operator
            and current.get("release_label") == release
            and current_corpus.get("corpus_sha256") == corpus.get("corpus_sha256")
            and current_report.get("report_sha256") == report.get("report_sha256")
            and current_e2e.get("report_sha256")
            == (e2e_report or {}).get("report_sha256")
            and current_closeout.get("closeout_sha256")
            == (closeout or {}).get("closeout_sha256")
            and current_candidate.get("candidate_sha256")
            == (candidate or {}).get("candidate_sha256")
            and bool(
                dict(current.get("claims") or {}).get(
                    "controlled_pilot_ready_through_phase4_preflight"
                )
            )
            == controlled_phase4_ready
            and int(
                dict(current.get("claims") or {}).get(
                    "phase4_preflight_case_count"
                )
                or 0
            )
            == controlled_phase4_case_count
            and int(
                dict(current.get("phase1") or {}).get(
                    "final_coverage_fade_tail_max_frames"
                )
                or 0
            )
            == FINAL_COVERAGE_FADE_TAIL_MAX_FRAMES
            and str(
                dict(
                    dict(current.get("phase1") or {}).get(
                        "post_refinement_sparse_compact_guard"
                    )
                    or {}
                ).get("policy_version")
                or ""
            )
            == POST_REFINEMENT_SPARSE_COMPACT_POLICY_VERSION
            and str(
                dict(
                    dict(current.get("render") or {}).get("residual_cjk_policy")
                    or {}
                ).get("policy_version")
                or ""
            )
            == RESIDUAL_CJK_POLICY_VERSION
            and str(
                dict(
                    dict(current.get("audio_authority") or {}).get(
                        "no_dialogue_source_audio"
                    )
                    or {}
                ).get("policy_version")
                or ""
            )
            == NO_DIALOGUE_AUDIO_POLICY_VERSION
            and (
                runtime_tts is None
                or str(dict(current.get("tts") or {}).get("runtime_config_sha256") or "")
                == str(runtime_tts.get("runtime_config_sha256") or "")
            )
        ):
            return {
                "recipe": current,
                "versioned_path": output
                / f"pipeline_recipe_{current['recipe_sha256']}.json",
            }
    cfg = settings or get_settings()
    locked_tts = (
        dict(runtime_tts)
        if runtime_tts is not None
        else {
            "provider": str(getattr(cfg, "audio_tts_provider", "auto") or "auto"),
            "model_id": str(getattr(cfg, "audio_tts_model_id", "") or ""),
            "voice_id": str(getattr(cfg, "audio_tts_voice_id", "") or ""),
            "language_code": "vi",
            "speaking_rate": float(
                getattr(cfg, "audio_tts_speaking_rate", 1.0) or 1.0
            ),
            "authority": "unverified_runtime_intent",
        }
    )
    models = sorted(
        {
            str(dict(case.get("phase2") or {}).get("model_version") or "")
            for case in list(report.get("cases") or [])
            if str(dict(case.get("phase2") or {}).get("model_version") or "")
        }
    )
    has_gaps = bool(corpus.get("real_video_gaps"))
    recipe = {
        "schema_version": PIPELINE_RECIPE_LOCK_SCHEMA,
        "status": (
            "LOCKED_FOR_CONTROLLED_PILOT_WITH_GAPS"
            if has_gaps
            else "LOCKED_FOR_CONTROLLED_PILOT"
        ),
        "locked_at": _now(),
        "operator_id": operator,
        "release_label": release,
        "phase1": {
            "extractor": "v58_candidate",
            "step": 1,
            "pad": 1,
            "authority": "master_timeline.json",
            "authority_v3_6_full_duration": False,
            "scorer": "score_phase1_pass",
            "final_coverage_fade_tail_max_frames": (
                FINAL_COVERAGE_FADE_TAIL_MAX_FRAMES
            ),
            "post_refinement_sparse_compact_guard": {
                "policy_version": POST_REFINEMENT_SPARSE_COMPACT_POLICY_VERSION,
                "max_width_frac": (
                    POST_REFINEMENT_SPARSE_COMPACT_MAX_WIDTH_FRAC
                ),
                "max_height_frac": (
                    POST_REFINEMENT_SPARSE_COMPACT_MAX_HEIGHT_FRAC
                ),
                "visual_normalized_height": (
                    POST_REFINEMENT_VISUAL_NORMALIZED_HEIGHT
                ),
                "texture_max_laplacian_variance": (
                    POST_REFINEMENT_TEXTURE_MAX_LAPLACIAN_VARIANCE
                ),
                "texture_max_edge_density": (
                    POST_REFINEMENT_TEXTURE_MAX_EDGE_DENSITY
                ),
                "texture_min_saturation": (
                    POST_REFINEMENT_TEXTURE_MIN_SATURATION
                ),
                "recognizer_failure_policy": "fail_soft_to_operator_review",
            },
        },
        "phase2": {
            "provider": "local",
            "model_versions": models,
            "geometry_authority": "master_timeline.json",
            "output_artifact": "phase2_ocr_timeline.json",
            "overwrite_master_timeline": False,
            "approval_policy": "exact_operator_review",
            "llm_context_correction_allowed": True,
            "llm_correction_is_approval_authority": False,
            "residual_remediation": {
                "active_pointer_schema": "phase2_residual_remediation_active_v1",
                "generation_policy": "cumulative_versioned_hash_bound",
                "ocr_probe_policy": "phase2_hash_bound_detector_probe_v1",
                "visual_override_policy": "phase2_operator_visual_override_v1",
            },
        },
        "phase3": {
            "scope": "title_labels_ingredients_units_endcard",
            "duplicate_transition_policy": "translate_once_cover_all_geometry_refs",
            "duration_policy": "meaning_preserving_compaction_then_measured_audio_fit",
            "approval_policy": "operator_locked_translation",
            "additive_approval_rebind_policy": (
                "exact_content_plus_hash_bound_geometry_v2"
            ),
        },
        "tts": {
            **locked_tts,
            "timing_policy": "measured_duration_segment_fit",
            "atempo_policy": "bounded_only_after_text_compaction",
        },
        "render": {
            "renderer": "phase4_adaptive_pts_preserving",
            "role_policy_version": RENDER_POLICY_VERSION,
            "timing_normalization_policy_version": (
                PHASE4_TIMING_NORMALIZATION_POLICY_VERSION
            ),
            "video_encoder_policy": str(
                getattr(cfg, "render_video_encoder", "auto") or "auto"
            ),
            "hardware_smoke_probe": bool(
                getattr(cfg, "render_hardware_encoder_smoke_probe", True)
            ),
            "hardware_fallback_enabled": bool(
                getattr(cfg, "render_hardware_encoder_fallback_enabled", True)
            ),
            "background_mix_gain": float(
                getattr(cfg, "render_background_mix_gain", 1.0) or 1.0
            ),
            "loudness_target_lufs": float(
                getattr(cfg, "render_loudness_target_lufs", -14.0) or -14.0
            ),
            "narration_only_loudness": {
                "policy_version": TWO_PASS_LOUDNESS_POLICY_VERSION,
                "measurement": "ffmpeg_loudnorm_two_pass",
                "encode_true_peak_db": TWO_PASS_ENCODE_TRUE_PEAK_DB,
                "aac_headroom_db": 1.2,
            },
            "residual_cjk_policy": {
                "policy_version": RESIDUAL_CJK_POLICY_VERSION,
                "source_intrinsic_edge_print_requires_source_ocr_match": True,
                "texture_false_positive": {
                    "max_area": SOURCE_INTRINSIC_TEXTURE_MAX_AREA,
                    "max_pixel_aspect": SOURCE_INTRINSIC_TEXTURE_MAX_PIXEL_ASPECT,
                    "max_mean_abs_delta": SOURCE_INTRINSIC_TEXTURE_MAX_MEAN_DELTA,
                    "max_p95_abs_delta": SOURCE_INTRINSIC_TEXTURE_MAX_P95_DELTA,
                    "active_cover_overlap_blocks_exclusion": True,
                },
            },
            "layout_policies": {
                "dense_group": DENSE_GROUP_LAYOUT_POLICY_VERSION,
                "semantic_dedup": SEMANTIC_RENDER_DEDUP_POLICY_VERSION,
            },
            "source_text_provenance": {
                "moving_object_region": SOURCE_INTRINSIC_REGION_POLICY_VERSION,
                "operator_approval_required": True,
                "source_pixels_preserved": True,
            },
            "invisible_perturbation": False,
            "mirror": False,
            "duplicate_detection_evasion": False,
        },
        "audio_authority": {
            "no_dialogue_source_audio": {
                "policy_version": NO_DIALOGUE_AUDIO_POLICY_VERSION,
                "vad_provider": "silero_vad",
                "requires_measured_execution": True,
                "requires_zero_speech_seconds": True,
                "requires_zero_speech_segments": True,
                "operator_audio_approval_required": True,
                "source_hash_binding_required": True,
            }
        },
        "operator_gates": [
            "OCR_APPROVED",
            "TRANSLATION_APPROVED",
            "VISUAL_APPROVED",
            "AUDIO_APPROVED",
            "FINAL_APPROVED",
            "METADATA_APPROVED",
            "SOURCE_RIGHTS_AND_MUSIC_APPROVED",
        ],
        "execution": {
            "resume": True,
            "idempotent_stage_checks": True,
            "transient_retry_policy": "pipeline_retry_policy",
            "external_publish": False,
        },
        "evidence": {
            "corpus": {
                "path": corpus_file.relative_to(workspace).as_posix(),
                "file_sha256": _sha256_file(corpus_file),
                "corpus_sha256": corpus["corpus_sha256"],
            },
            "report": {
                "path": report_file.relative_to(workspace).as_posix(),
                "file_sha256": _sha256_file(report_file),
                "report_sha256": report["report_sha256"],
            },
            "e2e_report": (
                {
                    "path": e2e_report_file.relative_to(workspace).as_posix(),
                    "file_sha256": _sha256_file(e2e_report_file),
                    "report_sha256": e2e_report["report_sha256"],
                    "case_count": int(e2e_report.get("case_count") or 0),
                }
                if e2e_report is not None and e2e_report_file is not None
                else None
            ),
            "phase4_preflight_closeout": (
                {
                    "path": closeout_file.relative_to(workspace).as_posix(),
                    "file_sha256": _sha256_file(closeout_file),
                    "closeout_sha256": closeout["closeout_sha256"],
                    "case_count": int(closeout.get("case_count") or 0),
                }
                if closeout is not None and closeout_file is not None
                else None
            ),
            "recipe_candidate": (
                {
                    "path": candidate_file.relative_to(workspace).as_posix(),
                    "file_sha256": _sha256_file(candidate_file),
                    "candidate_sha256": candidate["candidate_sha256"],
                    "release_label": candidate.get("release_label"),
                }
                if candidate is not None and candidate_file is not None
                else None
            ),
            "real_video_gaps": corpus.get("real_video_gaps"),
        },
        "claims": {
            "universal_video_support": False,
            "controlled_pilot_ready_through_phase2_execution": True,
            "controlled_pilot_ready_through_phase4_preflight": controlled_phase4_ready,
            "phase4_preflight_case_count": controlled_phase4_case_count,
            "approved_no_text_bypass_count": int(
                report.get("no_text_approved_case_count") or 0
            ),
            "full_batch_end_to_end_pass": bool(e2e_report)
            and bool(
                dict((e2e_report or {}).get("claims") or {}).get(
                    "full_batch_end_to_end_pass", True
                )
            ),
            "included_cases_end_to_end_pass": bool(e2e_report)
            and bool(
                dict((e2e_report or {}).get("claims") or {}).get(
                    "included_cases_end_to_end_pass", True
                )
            ),
            "end_to_end_case_count": int(
                (e2e_report or {}).get("case_count") or 0
            ),
            "visual_localization_scope_case_count": int(
                report.get("visual_localization_scope_case_count") or 0
            ),
        },
    }
    recipe["recipe_sha256"] = _sha256_json(recipe)
    versioned = output / f"pipeline_recipe_{recipe['recipe_sha256']}.json"
    if versioned.is_file():
        existing = _load_verified(versioned, "recipe_sha256")
        if existing != recipe:
            raise PipelineRecipeLockError("Versioned recipe conflicts with current lock")
    else:
        _write_json_atomic(versioned, recipe)
    _write_json_atomic(current_path, recipe)
    return {"recipe": recipe, "versioned_path": versioned}
