from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
import pytest

from scripts.build_phase4_residual_triage_decision_proposal import (
    ResidualTriageDecisionProposalError,
    _geometry_for_decision,
    build_decision_proposal,
)


def _hash_json(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _image(path: Path, value: int = 90) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = np.full((60, 100, 3), value, dtype=np.uint8)
    assert cv2.imwrite(str(path), frame)
    return {"path": path.name, "sha256": _hash_file(path)}


def _cluster(
    root: Path,
    cluster_id: str,
    *,
    frame_index: int,
    signature: str,
    geometry: dict,
    intersections: list[dict] | None = None,
) -> dict:
    evidence_dir = root / "evidence" / cluster_id
    source = evidence_dir / "source.jpg"
    rendered = evidence_dir / "rendered.jpg"
    source_crop = evidence_dir / "source_crop.jpg"
    rendered_crop = evidence_dir / "rendered_crop.jpg"
    contact = evidence_dir / "contact.jpg"
    for path in (source, rendered, source_crop, rendered_crop, contact):
        _image(path)

    def ref(path: Path) -> dict[str, str]:
        return {
            "path": path.relative_to(root).as_posix(),
            "sha256": _hash_file(path),
        }

    return {
        "cluster_id": cluster_id,
        "signature": signature,
        "detections": [
            {
                "frame_index": frame_index,
                "text": signature,
                "confidence": 0.99,
                "geometry": geometry,
            }
        ],
        "phase1_geometry_intersections": intersections or [],
        "source_render_adjacent_complete": True,
        "contact_sheet_ref": ref(contact),
        "evidence_frames": [
            {
                "frame_index": frame_index,
                "source_frame_ref": ref(source),
                "rendered_frame_ref": ref(rendered),
                "source_crop_ref": ref(source_crop),
                "rendered_crop_ref": ref(rendered_crop),
            }
        ],
    }


def _fixture(run: Path) -> tuple[Path, Path]:
    case_id = "case_01"
    root = run / case_id
    root.mkdir(parents=True)
    master = [
        {
            "text_id": "sub_ref",
            "start_frame": 0,
            "end_frame": 5,
            "box_coords": [10, 10, 50, 30],
        },
        {
            "text_id": "sub_expand",
            "start_frame": 10,
            "end_frame": 15,
            "box_coords": [20, 20, 60, 40],
        },
    ]
    master_path = root / "master_timeline.json"
    phase2_path = root / "phase2_ocr_timeline.json"
    phase3_path = root / "phase3_render_handoff.json"
    _write_json(master_path, master)
    _write_json(
        phase2_path,
        {
            "content_objects": [
                {
                    "content_id": "content_expand",
                    "geometry_refs": ["sub_expand"],
                    "ocr_text_approved": "完整句",
                }
            ]
        },
    )
    _write_json(
        phase3_path,
        {
            "geometry_map": {
                "sub_expand": {
                    "text_vi": "Câu đầy đủ",
                    "translation_status": "TRANSLATION_APPROVED",
                }
            }
        },
    )
    clusters = [
        _cluster(
            root,
            "cluster_add",
            frame_index=2,
            signature="午餐",
            geometry={"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.2},
        ),
        _cluster(
            root,
            "cluster_expand",
            frame_index=12,
            signature="完整句",
            geometry={"x": 0.2, "y": 0.2, "width": 0.4, "height": 0.2},
            intersections=[{"text_id": "sub_expand"}],
        ),
        _cluster(
            root,
            "cluster_false",
            frame_index=20,
            signature="福",
            geometry={"x": 0.7, "y": 0.7, "width": 0.05, "height": 0.05},
        ),
    ]
    triage = {
        "status": "RESIDUAL_VISUAL_TRIAGE_OPERATOR_REVIEW_REQUIRED",
        "operator_approval_written": False,
        "clusters": clusters,
    }
    triage["triage_sha256"] = _hash_json(triage)
    triage_path = root / "phase4_residual_visual_triage.json"
    _write_json(triage_path, triage)
    index = {
        "status": "PHASE4_RESIDUAL_VISUAL_TRIAGE_REVIEW_REQUIRED",
        "cases": [
            {
                "case_id": case_id,
                "triage_ref": {
                    "path": triage_path.relative_to(run).as_posix(),
                    "sha256": _hash_file(triage_path),
                },
            }
        ],
    }
    index["batch_triage_sha256"] = _hash_json(index)
    _write_json(run / "phase4_residual_visual_triage_index.json", index)
    decisions = {
        "status": "CURATED_PROPOSAL_INPUT",
        "operator_approval_written": False,
        "batch_triage_sha256": index["batch_triage_sha256"],
        "decisions": [
            {
                "case_id": case_id,
                "cluster_id": "cluster_add",
                "proposed_action": "ADD_PHASE2_OCCURRENCE",
                "source_text_suggested": "午餐",
                "vi_text_suggested": "Bữa trưa",
                "source_text_basis": "VISUAL_EXACT_MATCH",
                "geometry_strategy": "MANUAL_TIGHT_GEOMETRY",
                "geometry": {
                    "x": 0.15,
                    "y": 0.12,
                    "width": 0.1,
                    "height": 0.1,
                },
                "temporal_strategy": "ALIGN_AND_RESCAN_FROM_PHASE1_WINDOW",
                "temporal_reference_text_id": "sub_ref",
                "rationale": "Missing UI label.",
            },
            {
                "case_id": case_id,
                "cluster_id": "cluster_expand",
                "proposed_action": "EXPAND_EXISTING_PHASE2_GEOMETRY",
                "target_text_id": "sub_expand",
                "source_text_suggested": "完整句",
                "vi_text_suggested": "Câu đầy đủ",
                "source_text_basis": "APPROVED_PHASE2_CONTENT",
                "rationale": "Approved content is clipped.",
            },
            {
                "case_id": case_id,
                "cluster_id": "cluster_false",
                "proposed_action": "APPROVE_SOURCE_INTRINSIC_FALSE_POSITIVE",
                "source_text_suggested": "福",
                "vi_text_suggested": None,
                "source_text_basis": "SOURCE_INTRINSIC",
                "false_positive_scope": "SOURCE_INTRINSIC_PHYSICAL_TEXT",
                "rationale": "Physical bottle label is unchanged.",
            },
        ],
    }
    decisions_path = run / "decisions.json"
    _write_json(decisions_path, decisions)
    return root, decisions_path


def test_builds_complete_proposal_without_mutating_authority() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, decisions_path = _fixture(run)
        protected = {
            path.name: _hash_file(path)
            for path in (
                root / "master_timeline.json",
                root / "phase2_ocr_timeline.json",
                root / "phase3_render_handoff.json",
            )
        }

        proposal = build_decision_proposal(
            run_root=run, decisions_path=decisions_path
        )

        assert proposal["counts"] == {
            "cases": 1,
            "decisions": 3,
            "add_occurrence": 1,
            "expand_geometry": 1,
            "false_positive": 1,
            "linked_coverage": 0,
            "manual_tight_geometry": 1,
            "manual_evidence_geometry": 0,
        }
        assert proposal["operator_approval_written"] is False
        assert proposal["authority_mutation_written"] is False
        false_positive = proposal["cases"][0]["decisions"][2]
        assert false_positive["source_render_crop_max_mean_abs_delta"] == 0.0
        unsigned = dict(proposal)
        claimed = unsigned.pop("proposal_sha256")
        assert claimed == _hash_json(unsigned)
        for path in (
            root / "master_timeline.json",
            root / "phase2_ocr_timeline.json",
            root / "phase3_render_handoff.json",
        ):
            assert _hash_file(path) == protected[path.name]
        assert not (root / "phase2_residual_remediation.json").exists()
        assert not (root / "phase4_visual_approval.json").exists()


def test_links_mixed_detector_fragment_to_one_additive_occurrence() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, decisions_path = _fixture(run)
        triage_path = root / "phase4_residual_visual_triage.json"
        triage = json.loads(triage_path.read_text(encoding="utf-8"))
        triage.pop("triage_sha256")
        triage["clusters"].append(
            _cluster(
                root,
                "cluster_link",
                frame_index=2,
                signature="体",
                geometry={"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.1},
            )
        )
        triage["triage_sha256"] = _hash_json(triage)
        _write_json(triage_path, triage)
        index_path = run / "phase4_residual_visual_triage_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index.pop("batch_triage_sha256")
        index["cases"][0]["triage_ref"]["sha256"] = _hash_file(triage_path)
        index["batch_triage_sha256"] = _hash_json(index)
        _write_json(index_path, index)
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
        decisions["batch_triage_sha256"] = index["batch_triage_sha256"]
        decisions["decisions"].append(
            {
                "case_id": "case_01",
                "cluster_id": "cluster_link",
                "proposed_action": "COVERED_BY_PROPOSED_OCCURRENCE",
                "linked_cluster_id": "cluster_add",
                "source_text_suggested": "午餐",
                "vi_text_suggested": "Bữa trưa",
                "source_text_basis": "MIXED_DETECTOR_FRAGMENT_OF_LINKED_LABEL",
                "rationale": "The broad detector box includes the linked label.",
            }
        )
        _write_json(decisions_path, decisions)

        proposal = build_decision_proposal(
            run_root=run, decisions_path=decisions_path
        )

        assert proposal["counts"]["linked_coverage"] == 1
        linked = proposal["cases"][0]["decisions"][-1]
        assert linked["linked_cluster_id"] == "cluster_add"
        assert linked["materialization_gate"].startswith("LINKED_PHASE2")


def test_manual_evidence_geometry_can_expand_partial_residual_safely() -> None:
    cluster = {
        "detections": [
            {
                "frame_index": 39,
                "confidence": 0.8,
                "geometry": {
                    "x": 0.256,
                    "y": 0.511,
                    "width": 0.015,
                    "height": 0.021,
                },
            }
        ]
    }

    result = _geometry_for_decision(
        {
            "geometry_strategy": "MANUAL_EVIDENCE_GEOMETRY",
            "geometry": {
                "x": 0.238,
                "y": 0.495,
                "width": 0.055,
                "height": 0.055,
            },
        },
        cluster,
    )

    assert result["strategy"] == "MANUAL_EVIDENCE_GEOMETRY"


def test_manual_evidence_geometry_rejects_unbounded_expansion() -> None:
    cluster = {
        "detections": [
            {
                "frame_index": 39,
                "confidence": 0.8,
                "geometry": {
                    "x": 0.25,
                    "y": 0.50,
                    "width": 0.02,
                    "height": 0.02,
                },
            }
        ]
    }

    with pytest.raises(
        ResidualTriageDecisionProposalError,
        match="expansion exceeds safety limits",
    ):
        _geometry_for_decision(
            {
                "geometry_strategy": "MANUAL_EVIDENCE_GEOMETRY",
                "geometry": {
                    "x": 0.05,
                    "y": 0.05,
                    "width": 0.80,
                    "height": 0.80,
                },
            },
            cluster,
        )


def test_rejects_stale_visual_triage() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, decisions_path = _fixture(run)
        triage_path = root / "phase4_residual_visual_triage.json"
        triage = json.loads(triage_path.read_text(encoding="utf-8"))
        triage["tampered"] = True
        _write_json(triage_path, triage)

        with pytest.raises(
            ResidualTriageDecisionProposalError,
            match="Stale .*visual triage",
        ):
            build_decision_proposal(run_root=run, decisions_path=decisions_path)


def test_requires_one_decision_for_every_cluster() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        _root, decisions_path = _fixture(run)
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
        decisions["decisions"].pop()
        _write_json(decisions_path, decisions)

        with pytest.raises(
            ResidualTriageDecisionProposalError,
            match="Missing curated decision.*cluster_false",
        ):
            build_decision_proposal(run_root=run, decisions_path=decisions_path)
