"""Apply a complete hash-bound Phase 2 OCR decision set."""

from __future__ import annotations

import argparse
import json
import sys

from src.services.phase2_operator_review import (
    Phase2OperatorReviewError,
    apply_phase2_operator_review,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.apply_phase2_operator_review"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("decisions_json")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        audit = apply_phase2_operator_review(
            root_dir=args.artifact_root, decisions_path=args.decisions_json
        )
        print(
            json.dumps(
                {
                    "status": audit["status"],
                    "counts": audit["counts"],
                    "audit_sha256": audit["audit_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, Phase2OperatorReviewError) as exc:
        print(f"[PHASE2-OPERATOR-REVIEW][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
