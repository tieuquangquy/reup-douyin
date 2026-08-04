"""Index per-case exact-crop/reference OCR proposals without approving them."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256_json(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    args = parser.parse_args()
    run = Path(args.run_root).resolve()
    rows = []
    totals = {
        "cases": 0,
        "objects": 0,
        "carry_forward_eligible": 0,
        "operator_review_required": 0,
        "proposed_approve": 0,
        "proposed_edit": 0,
        "proposed_reject_ui": 0,
    }
    for path in sorted(run.glob("local_*/phase2_review_proposal_reference_v21.json")):
        proposal = json.loads(path.read_text(encoding="utf-8"))
        unsigned = dict(proposal)
        claimed = str(unsigned.pop("proposal_sha256") or "")
        if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
            raise ValueError(f"Invalid proposal hash: {path}")
        counts = dict(proposal.get("counts") or {})
        row = {
            "case_id": path.parent.name,
            "path": path.relative_to(run).as_posix(),
            "file_sha256": _sha256_file(path),
            "proposal_sha256": claimed,
            "counts": counts,
        }
        rows.append(row)
        totals["cases"] += 1
        for key in totals:
            if key != "cases":
                totals[key] += int(counts.get(key) or 0)
    if not rows:
        raise ValueError("No reference proposals found")
    payload = {
        "schema_version": "phase2_reference_proposal_index_v1",
        "status": "OPERATOR_APPROVAL_REQUIRED",
        "non_authoritative": True,
        "run_id": run.name,
        "counts": totals,
        "cases": rows,
        "operator_decision": None,
    }
    payload["index_sha256"] = _sha256_json(payload)
    output = run / "phase2_reference_proposal_index_v24.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Phase 2 Reference Proposal Index V24",
        "",
        f"- Status: `{payload['status']}`",
        f"- Cases: `{totals['cases']}`",
        f"- Objects: `{totals['objects']}`",
        f"- Exact-crop carry-forward eligible: `{totals['carry_forward_eligible']}`",
        f"- Operator review required: `{totals['operator_review_required']}`",
        f"- Proposed approve/edit: `{totals['proposed_approve']}/{totals['proposed_edit']}`",
        f"- Index SHA-256: `{payload['index_sha256']}`",
        "",
        "| Case | Carry | Review | Approve | Edit | Proposal SHA |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        c = dict(row["counts"])
        lines.append(
            f"| `{row['case_id']}` | {c.get('carry_forward_eligible', 0)} | "
            f"{c.get('operator_review_required', 0)} | {c.get('proposed_approve', 0)} | "
            f"{c.get('proposed_edit', 0)} | `{row['proposal_sha256']}` |"
        )
    (run / "PHASE2_REFERENCE_PROPOSAL_INDEX_V24.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": payload["status"], "counts": totals, "index_sha256": payload["index_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
