from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from scripts.materialize_phase2_residual_remediation import verify_remediation
from scripts.materialize_phase4_residual_triage_decisions import (
    ResidualTriageMaterializationError,
    _merge_cumulative_remediation,
    materialize_batch,
)


def _hash_json(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _fixture(run: Path) -> tuple[Path, Path, str]:
    case_id = "case_01"
    root = run / case_id
    root.mkdir(parents=True)
    master_path = root / "master_timeline.json"
    phase2_path = root / "phase2_ocr_timeline.json"
    phase3_path = root / "phase3_render_handoff.json"
    _write(
        master_path,
        [
            {
                "text_id": "sub_ref",
                "start_frame": 0,
                "end_frame": 5,
                "box_coords": [10, 10, 50, 30],
            }
        ],
    )
    _write(phase2_path, {})
    _write(phase3_path, {})
    frame_path = root / "evidence" / "source.jpg"
    crop_path = root / "evidence" / "crop.jpg"
    frame_path.parent.mkdir(parents=True)
    frame = np.full((60, 100, 3), 120, dtype=np.uint8)
    assert cv2.imwrite(str(frame_path), frame)
    assert cv2.imwrite(str(crop_path), frame[5:30, 5:60])

    def ref(path: Path) -> dict[str, str]:
        return {
            "path": path.relative_to(root).as_posix(),
            "sha256": _hash_file(path),
        }

    add_cluster = {
        "cluster_id": "cluster_add",
        "signature": "午餐",
        "representative_frame_index": 2,
        "detections": [
            {
                "frame_index": 2,
                "text": "午餐",
                "confidence": 0.99,
                "geometry": {"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.2},
            }
        ],
        "evidence_frames": [
            {
                "frame_index": 2,
                "source_frame_ref": ref(frame_path),
                "source_crop_ref": ref(crop_path),
            }
        ],
    }
    false_cluster = {
        "cluster_id": "cluster_false",
        "signature": "福",
        "representative_frame_index": 20,
        "detections": [
            {
                "frame_index": 20,
                "text": "福",
                "confidence": 0.80,
                "geometry": {"x": 0.7, "y": 0.7, "width": 0.05, "height": 0.05},
            }
        ],
        "evidence_frames": [],
    }
    visual = {
        "operator_approval_written": False,
        "video": {
            "frame_width": 100,
            "frame_height": 60,
            "frame_count": 30,
            "fps": 30.0,
        },
        "clusters": [add_cluster, false_cluster],
    }
    visual["triage_sha256"] = _hash_json(visual)
    visual_path = root / "phase4_residual_visual_triage.json"
    _write(visual_path, visual)
    batch_visual_path = run / "phase4_residual_visual_triage_index.json"
    curated_path = run / "curated.json"
    _write(batch_visual_path, {"locked": True})
    _write(curated_path, {"locked": True})
    token = "RESIDUAL_TRIAGE_DECISION_PROPOSALS_APPROVED_V22_1_TEST"
    proposal = {
        "status": "RESIDUAL_TRIAGE_DECISION_PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "operator_approval_token": token,
        "operator_approval_written": False,
        "batch_visual_triage_ref": {
            "path": batch_visual_path.name,
            "sha256": _hash_file(batch_visual_path),
        },
        "curated_input_ref": {
            "path": curated_path.name,
            "sha256": _hash_file(curated_path),
        },
        "cases": [
            {
                "case_id": case_id,
                "visual_triage_ref": {
                    "path": visual_path.relative_to(run).as_posix(),
                    "sha256": _hash_file(visual_path),
                },
                "authority_refs": {
                    "master_timeline": {
                        "path": master_path.name,
                        "sha256": _hash_file(master_path),
                    },
                    "phase2_ocr_timeline": {
                        "path": phase2_path.name,
                        "sha256": _hash_file(phase2_path),
                    },
                    "phase3_render_handoff": {
                        "path": phase3_path.name,
                        "sha256": _hash_file(phase3_path),
                    },
                },
                "decisions": [
                    {
                        "cluster_id": "cluster_add",
                        "proposal_status": "OPERATOR_REVIEW_REQUIRED",
                        "proposed_action": "ADD_PHASE2_OCCURRENCE",
                        "source_text_suggested": "午餐",
                        "vi_text_suggested": "Bữa trưa",
                        "cluster_evidence_sha256": _hash_json(add_cluster),
                        "proposed_occurrence": {
                            "strategy": "CLUSTER_GEOMETRY",
                            "geometry": {
                                "x": 0.1,
                                "y": 0.1,
                                "width": 0.4,
                                "height": 0.2,
                            },
                            "representative_frame_index": 2,
                            "temporal": {
                                "strategy": "ALIGN_AND_RESCAN_FROM_PHASE1_WINDOW",
                                "reference_text_id": "sub_ref",
                                "reference_window": [0, 5],
                            },
                        },
                    },
                    {
                        "cluster_id": "cluster_false",
                        "proposal_status": "OPERATOR_REVIEW_REQUIRED",
                        "proposed_action": "APPROVE_SOURCE_INTRINSIC_FALSE_POSITIVE",
                        "source_text_suggested": "福",
                        "false_positive_scope": "SOURCE_INTRINSIC_PHYSICAL_TEXT",
                        "cluster_evidence_sha256": _hash_json(false_cluster),
                        "visual_evidence_ref": None,
                    },
                ],
            }
        ],
    }
    proposal["proposal_sha256"] = _hash_json(proposal)
    proposal_path = run / "phase4_residual_triage_decision_proposal.json"
    _write(proposal_path, proposal)
    return root, proposal_path, token


def _carry() -> dict:
    return {
        "source_refs": {},
        "rows": [
            {
                "content_id": "content_old",
                "decision": "APPROVE",
                "zh_approved": "旧",
                "vi_text_candidate": "Cũ",
                "vi_text_approved": "Cũ",
                "reviewer": "operator",
                "reviewed_at": "2026-07-29T00:00:00+00:00",
                "previous_review_input_sha256": "a" * 64,
            }
        ],
    }


def test_materializes_only_exact_approved_batch_token() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, proposal_path, token = _fixture(run)
        master_before = _hash_file(root / "master_timeline.json")
        with patch(
            "scripts.materialize_phase4_residual_triage_decisions._capture_translation_authority",
            return_value=_carry(),
        ):
            result = materialize_batch(
                run_root=run,
                proposal_path=proposal_path,
                approval_token=token,
                operator_id="operator",
                approved_at="2026-07-29T12:00:00+00:00",
            )

        assert result["counts"] == {
            "cases": 1,
            "occurrences": 1,
            "geometry_overrides": 0,
            "false_positive_deferred": 1,
        }
        remediation = json.loads(
            (root / "phase2_residual_remediation.json").read_text(
                encoding="utf-8"
            )
        )
        assert verify_remediation(remediation)
        occurrence = remediation["approved_occurrences"][0]["occurrence"]
        assert occurrence["start_frame"] == 0
        assert occurrence["end_frame"] == 5
        assert (root / occurrence["crop_path"]).is_file()
        assert remediation["false_positive_decisions_deferred_to_phase4"][0][
            "source_text"
        ] == "福"
        assert _hash_file(root / "master_timeline.json") == master_before


def test_wrong_token_writes_no_authority() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, proposal_path, _token = _fixture(run)
        with pytest.raises(
            ResidualTriageMaterializationError, match="approval token"
        ):
            materialize_batch(
                run_root=run,
                proposal_path=proposal_path,
                approval_token="WRONG",
                operator_id="operator",
                approved_at="2026-07-29T12:00:00+00:00",
            )

        assert not (root / "phase2_residual_remediation.json").exists()
        assert not (
            root / "phase2_residual_remediation_decision_projection.json"
        ).exists()


def test_materializes_linked_fragment_without_duplicate_occurrence() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, proposal_path, token = _fixture(run)
        visual_path = root / "phase4_residual_visual_triage.json"
        visual = json.loads(visual_path.read_text(encoding="utf-8"))
        visual.pop("triage_sha256")
        linked_cluster = {
            "cluster_id": "cluster_link",
            "signature": "体",
            "representative_frame_index": 2,
            "detections": [
                {
                    "frame_index": 2,
                    "text": "体Bữa trưa",
                    "confidence": 0.75,
                    "geometry": {
                        "x": 0.15,
                        "y": 0.12,
                        "width": 0.5,
                        "height": 0.2,
                    },
                }
            ],
            "evidence_frames": [],
        }
        visual["clusters"].append(linked_cluster)
        visual["triage_sha256"] = _hash_json(visual)
        _write(visual_path, visual)
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        proposal.pop("proposal_sha256")
        case = proposal["cases"][0]
        case["visual_triage_ref"]["sha256"] = _hash_file(visual_path)
        case["decisions"].append(
            {
                "cluster_id": "cluster_link",
                "proposal_status": "OPERATOR_REVIEW_REQUIRED",
                "proposed_action": "COVERED_BY_PROPOSED_OCCURRENCE",
                "linked_cluster_id": "cluster_add",
                "source_text_suggested": "午餐",
                "vi_text_suggested": "Bữa trưa",
                "cluster_evidence_sha256": _hash_json(linked_cluster),
                "visual_evidence_ref": None,
            }
        )
        proposal["proposal_sha256"] = _hash_json(proposal)
        _write(proposal_path, proposal)

        with patch(
            "scripts.materialize_phase4_residual_triage_decisions._capture_translation_authority",
            return_value=_carry(),
        ):
            materialize_batch(
                run_root=run,
                proposal_path=proposal_path,
                approval_token=token,
                operator_id="operator",
                approved_at="2026-07-29T12:00:00+00:00",
            )

        remediation = json.loads(
            (root / "phase2_residual_remediation.json").read_text(encoding="utf-8")
        )
        projection = json.loads(
            (root / "phase2_residual_remediation_decision_projection.json").read_text(
                encoding="utf-8"
            )
        )
        assert len(remediation["approved_occurrences"]) == 1
        assert projection["linked_coverage_decisions"][0][
            "linked_cluster_id"
        ] == "cluster_add"


def test_versioned_proposal_path_is_preserved_in_materialized_refs() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, proposal_path, token = _fixture(run)
        versioned = run / "phase4_residual_triage_decision_proposal_v2.json"
        proposal_path.replace(versioned)
        with patch(
            "scripts.materialize_phase4_residual_triage_decisions._capture_translation_authority",
            return_value=_carry(),
        ):
            result = materialize_batch(
                run_root=run,
                proposal_path=versioned,
                approval_token=token,
                operator_id="operator",
                approved_at="2026-07-29T12:00:00+00:00",
            )

        case_row = result["cases"][0]
        projection_path = run / case_row["projection_ref"]["path"]
        remediation_path = run / case_row["remediation_ref"]["path"]
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        assert projection["batch_proposal_ref"]["path"] == f"../{versioned.name}"
        assert projection["batch_proposal_ref"]["sha256"] == _hash_file(versioned)
        remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
        assert remediation["approved_occurrences"][0]["localization"][
            "suggestion_source"
        ] == versioned.name
        assert (root / "phase2_residual_remediation_active.json").is_file()


def test_cumulative_remediation_preserves_parent_occurrences() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        parent_path = root / "phase2_residual_remediation.json"
        parent = {
            "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
            "authority_refs": {"master_timeline": {"sha256": "a" * 64}},
            "approved_occurrences": [
                {"occurrence": {"text_id": "old"}, "ocr_text_approved": "æ—§"}
            ],
            "approved_geometry_overrides": [],
            "false_positive_decisions_deferred_to_phase4": [],
            "translation_carry_forward": {"rows": []},
        }
        parent["remediation_sha256"] = _hash_json(parent)
        _write(parent_path, parent)
        delta = {
            "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
            "authority_refs": {"master_timeline": {"sha256": "a" * 64}},
            "approved_occurrences": [
                {"occurrence": {"text_id": "new"}, "ocr_text_approved": "æ–°"}
            ],
            "approved_geometry_overrides": [],
            "false_positive_decisions_deferred_to_phase4": [],
            "translation_carry_forward": {"rows": []},
        }

        merged = _merge_cumulative_remediation(
            root=root,
            parent_path=parent_path,
            delta=delta,
        )

        assert [
            row["occurrence"]["text_id"]
            for row in merged["approved_occurrences"]
        ] == ["old", "new"]
        assert merged["generation"] == 2
        assert merged["delta_counts"]["occurrences"] == 1
        assert merged["authority_refs"]["parent_remediation"]["sha256"] == _hash_file(
            parent_path
        )
