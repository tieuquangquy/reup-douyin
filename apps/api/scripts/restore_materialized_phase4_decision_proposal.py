"""Reconstruct a materialized Phase-4 decision proposal without guesswork.

This is a narrow recovery tool for a canonical proposal file that was
accidentally overwritten after its decisions had already been materialized.
It reconstructs the exact pre-materialization payload from hash-bound
projections/remediation authorities and writes only when both the proposal
self-hash and expected file hash match the materialization index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from scripts.build_phase4_residual_triage_decision_proposal import (
    render_markdown,
)


class MaterializedProposalRestoreError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializedProposalRestoreError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise MaterializedProposalRestoreError(f"{path.name} must be an object")
    return payload


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_self(payload: Mapping[str, Any], field: str, *, label: str) -> None:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or claimed != _sha_json(unsigned):
        raise MaterializedProposalRestoreError(f"{label} self-hash is invalid")


def _verify_ref(run: Path, ref: Mapping[str, Any], *, label: str) -> Path:
    path = (run / str(ref.get("path") or "")).resolve()
    if (
        not path.is_relative_to(run)
        or not path.is_file()
        or _sha_file(path) != str(ref.get("sha256") or "")
    ):
        raise MaterializedProposalRestoreError(f"{label} is stale")
    return path


def _write_text_atomic(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def reconstruct_materialized_proposal(
    *,
    run_root: str | Path,
    batch_visual_index_file_sha256: str,
) -> tuple[dict[str, Any], bytes]:
    run = Path(run_root).resolve()
    index_path = run / "phase4_residual_triage_materialization_index.json"
    index = _load(index_path)
    _verify_self(index, "materialization_sha256", label="Materialization index")
    proposal_ref = dict(index.get("decision_proposal_ref") or {})
    expected_proposal_sha = str(proposal_ref.get("proposal_sha256") or "")
    expected_file_sha = str(proposal_ref.get("sha256") or "")
    visual_index_sha = str(batch_visual_index_file_sha256 or "").lower()
    if any(len(value) != 64 for value in (
        expected_proposal_sha,
        expected_file_sha,
        visual_index_sha,
    )):
        raise MaterializedProposalRestoreError("Expected proposal hashes are invalid")

    curated_path = run / "phase4_residual_triage_curated_decisions_v22_1.json"
    curated = _load(curated_path)
    if (
        str(curated.get("status") or "") != "CURATED_PROPOSAL_INPUT"
        or bool(curated.get("operator_approval_written"))
    ):
        raise MaterializedProposalRestoreError("Curated proposal input is invalid")
    batch_triage_sha = str(curated.get("batch_triage_sha256") or "")
    if len(batch_triage_sha) != 64:
        raise MaterializedProposalRestoreError("Batch triage hash is invalid")

    cases: list[dict[str, Any]] = []
    totals = {
        "cases": 0,
        "decisions": 0,
        "add_occurrence": 0,
        "expand_geometry": 0,
        "false_positive": 0,
        "manual_tight_geometry": 0,
    }
    for raw_case in list(index.get("cases") or []):
        case_row = dict(raw_case)
        case_id = str(case_row.get("case_id") or "")
        root = (run / case_id).resolve()
        if not case_id or not root.is_relative_to(run) or not root.is_dir():
            raise MaterializedProposalRestoreError("Materialized case root is invalid")
        projection_path = _verify_ref(
            run,
            dict(case_row.get("projection_ref") or {}),
            label=f"{case_id} projection",
        )
        remediation_path = _verify_ref(
            run,
            dict(case_row.get("remediation_ref") or {}),
            label=f"{case_id} remediation",
        )
        projection = _load(projection_path)
        remediation = _load(remediation_path)
        _verify_self(projection, "projection_sha256", label=f"{case_id} projection")
        projected_ref = dict(projection.get("batch_proposal_ref") or {})
        if (
            str(projected_ref.get("proposal_sha256") or "")
            != expected_proposal_sha
            or str(projected_ref.get("sha256") or "") != expected_file_sha
        ):
            raise MaterializedProposalRestoreError(
                f"{case_id} projection targets another proposal"
            )
        authority = dict(remediation.get("authority_refs") or {})
        visual_ref = dict(authority.get("visual_triage") or {})
        master_ref = dict(authority.get("master_timeline") or {})
        phase2_ref = dict(authority.get("phase2_timeline_before_remediation") or {})
        phase3_ref = dict(authority.get("phase3_handoff_before_remediation") or {})
        if any(
            len(str(dict(ref).get("sha256") or "")) != 64
            for ref in (visual_ref, master_ref, phase2_ref, phase3_ref)
        ):
            raise MaterializedProposalRestoreError(
                f"{case_id} historical authority refs are incomplete"
            )

        decisions: list[dict[str, Any]] = []
        for raw_change in list(projection.get("changes") or []):
            decision = dict(raw_change)
            decision.pop("materialized_occurrence", None)
            decision.pop("materialized_geometry_override", None)
            decisions.append(decision)
            action = str(decision.get("proposed_action") or "")
            totals["decisions"] += 1
            totals["add_occurrence"] += int(action == "ADD_PHASE2_OCCURRENCE")
            totals["expand_geometry"] += int(
                action == "EXPAND_EXISTING_PHASE2_GEOMETRY"
            )
            totals["false_positive"] += int(
                action == "APPROVE_SOURCE_INTRINSIC_FALSE_POSITIVE"
            )
            totals["manual_tight_geometry"] += int(
                str(
                    dict(decision.get("proposed_occurrence") or {}).get("strategy")
                    or ""
                )
                == "MANUAL_TIGHT_GEOMETRY"
            )
        cases.append(
            {
                "case_id": case_id,
                "visual_triage_ref": visual_ref,
                "authority_refs": {
                    "master_timeline": master_ref,
                    "phase2_ocr_timeline": phase2_ref,
                    "phase3_render_handoff": phase3_ref,
                },
                "decisions": decisions,
            }
        )
        totals["cases"] += 1

    proposal: dict[str, Any] = {
        "schema_version": "phase4_residual_triage_decision_proposal_v1",
        "status": "RESIDUAL_TRIAGE_DECISION_PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "operator_approval_token": index.get("approval_token"),
        "operator_approval_written": False,
        "authority_mutation_written": False,
        "batch_visual_triage_ref": {
            "path": "phase4_residual_visual_triage_index.json",
            "sha256": visual_index_sha,
            "batch_triage_sha256": batch_triage_sha,
        },
        "curated_input_ref": {
            "path": curated_path.relative_to(run).as_posix(),
            "sha256": _sha_file(curated_path),
        },
        "counts": totals,
        "cases": cases,
    }
    proposal["proposal_sha256"] = _sha_json(proposal)
    if proposal["proposal_sha256"] != expected_proposal_sha:
        raise MaterializedProposalRestoreError(
            "Reconstructed proposal self-hash does not match materialization"
        )
    serialized = json.dumps(proposal, ensure_ascii=False, indent=2)
    encoded_candidates = (
        serialized.encode("utf-8"),
        serialized.replace("\n", "\r\n").encode("utf-8"),
    )
    encoded = next(
        (
            value
            for value in encoded_candidates
            if hashlib.sha256(value).hexdigest() == expected_file_sha
        ),
        None,
    )
    if encoded is None:
        raise MaterializedProposalRestoreError(
            "Reconstructed proposal file hash does not match materialization"
        )
    return proposal, encoded


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.restore_materialized_phase4_decision_proposal"
    )
    parser.add_argument("run_root")
    parser.add_argument("--batch-visual-index-file-sha256", required=True)
    parser.add_argument(
        "--output-stem",
        default="phase4_residual_triage_decision_proposal",
    )
    args = parser.parse_args()
    try:
        stem = str(args.output_stem or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", stem):
            raise MaterializedProposalRestoreError("Output stem is unsafe")
        run = Path(args.run_root).resolve()
        proposal, serialized = reconstruct_materialized_proposal(
            run_root=run,
            batch_visual_index_file_sha256=args.batch_visual_index_file_sha256,
        )
        json_path = run / f"{stem}.json"
        markdown_path = run / f"{stem}.md"
        _write_bytes_atomic(json_path, serialized)
        _write_text_atomic(markdown_path, render_markdown(proposal))
        print(
            json.dumps(
                {
                    "status": "MATERIALIZED_PROPOSAL_RESTORED",
                    "proposal_sha256": proposal["proposal_sha256"],
                    "file_sha256": _sha_file(json_path),
                    "json": str(json_path),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, MaterializedProposalRestoreError) as exc:
        print(f"[MATERIALIZED-PROPOSAL-RESTORE][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
