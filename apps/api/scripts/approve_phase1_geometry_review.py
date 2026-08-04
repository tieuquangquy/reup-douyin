"""Record a hash-bound Phase 1 geometry operator decision set."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from src.media_pipeline.frame_sampling.phase1_geometry_review import (
    Phase1GeometryReviewError,
    prepare_phase1_geometry_review,
    record_phase1_geometry_decisions,
)


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise Phase1GeometryReviewError("Decision file must contain an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("decisions", type=Path, nargs="?")
    parser.add_argument("--operator-id", default="")
    args = parser.parse_args(argv)
    try:
        candidate = prepare_phase1_geometry_review(args.root)
        if args.decisions is None:
            print(json.dumps(candidate, ensure_ascii=False, indent=2))
            return 0
        decision_set = _load(args.decisions)
        claimed = str(decision_set.get("decisions_sha256") or "")
        unsigned = dict(decision_set)
        unsigned.pop("decisions_sha256", None)
        if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
            raise Phase1GeometryReviewError("Decision-set self-hash is invalid")
        if str(decision_set.get("review_sha256") or "") != str(
            candidate.get("review_sha256") or ""
        ):
            raise Phase1GeometryReviewError("Decision set is stale for geometry review")
        operator_id = str(args.operator_id or decision_set.get("operator_id") or "")
        result = record_phase1_geometry_decisions(
            args.root,
            operator_id=operator_id,
            decisions=list(decision_set.get("decisions") or []),
            notes=str(decision_set.get("notes") or ""),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, Phase1GeometryReviewError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

