"""Record operator approval of the V22.8 residual review pack only."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class OutputResidualReviewApprovalError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutputResidualReviewApprovalError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise OutputResidualReviewApprovalError(f"{path.name} must contain an object")
    return payload


def approve(
    *,
    run_root: str | Path,
    review_path: str | Path,
    review_token: str,
    operator_id: str,
    approved_at: str,
    output_name: str = "phase4_output_residual_review_approval_v22_8.json",
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    review_file = Path(review_path).resolve()
    review = _load_object(review_file)
    unsigned = dict(review)
    claimed_hash = str(unsigned.pop("review_sha256", "") or "")
    if (
        len(claimed_hash) != 64
        or claimed_hash != _sha256_json(unsigned)
        or str(review.get("status") or "") != "OUTPUT_RESIDUAL_REVIEW_REQUIRED"
        or bool(review.get("operator_approval_written"))
        or str(review.get("operator_review_token") or "") != str(review_token or "")
    ):
        raise OutputResidualReviewApprovalError("Residual review authority is invalid")
    if not review_file.is_relative_to(root):
        raise OutputResidualReviewApprovalError("Review file must be inside run root")
    operator = str(operator_id or "").strip()
    timestamp = str(approved_at or "").strip()
    if not operator or not timestamp:
        raise OutputResidualReviewApprovalError("operator_id and approved_at are required")
    payload: dict[str, Any] = {
        "schema_version": "phase4_output_residual_review_approval_v1",
        "status": "PHASE4_OUTPUT_RESIDUAL_REVIEW_APPROVED",
        "operator_id": operator,
        "approved_at": timestamp,
        "review_ref": {
            "path": review_file.name,
            "sha256": _sha256_file(review_file),
            "review_sha256": claimed_hash,
            "operator_review_token": review_token,
        },
        "decision_authority": "REVIEW_PACK_ONLY__CURATED_DECISIONS_REQUIRED",
        "translation_approval_written": False,
        "remediation_authority_written": False,
    }
    payload["approval_sha256"] = _sha256_json(payload)
    filename = str(output_name or "").strip()
    if (
        not filename
        or Path(filename).name != filename
        or not filename.endswith(".json")
    ):
        raise OutputResidualReviewApprovalError("Invalid approval output name")
    path = root / filename
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.approve_phase4_output_residual_review"
    )
    parser.add_argument("run_root")
    parser.add_argument("review_path")
    parser.add_argument("--review-token", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--approved-at")
    parser.add_argument(
        "--output-name",
        default="phase4_output_residual_review_approval_v22_8.json",
    )
    args = parser.parse_args()
    try:
        payload = approve(
            run_root=args.run_root,
            review_path=args.review_path,
            review_token=args.review_token,
            operator_id=args.operator_id,
            approved_at=args.approved_at or datetime.now(timezone.utc).isoformat(),
            output_name=args.output_name,
        )
    except (OSError, ValueError, OutputResidualReviewApprovalError) as exc:
        print(f"[PHASE4-OUTPUT-RESIDUAL-APPROVAL][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "approval_sha256": payload["approval_sha256"],
                "decision_authority": payload["decision_authority"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
