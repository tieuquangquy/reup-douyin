"""Prepare or record hash-bound Phase 1 no-text operator reviews."""

from __future__ import annotations

import argparse
import json
import sys

from src.media_pipeline.frame_sampling.phase1_no_text_contract import (
    Phase1NoTextContractError,
    evaluate_no_text_operator_gate,
    prepare_no_text_review,
    record_no_text_decision,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.review_phase1_no_text")
    parser.add_argument("artifact_root")
    parser.add_argument(
        "--decision", choices=("NO_TEXT_CONFIRMED", "TEXT_PRESENT_REJECTED")
    )
    parser.add_argument("--operator")
    parser.add_argument("--notes", default="")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        if args.decision:
            if not args.operator:
                raise Phase1NoTextContractError("--operator is required with --decision")
            result = record_no_text_decision(
                args.artifact_root,
                operator_id=args.operator,
                decision=args.decision,
                notes=args.notes,
            )
        else:
            prepare_no_text_review(args.artifact_root)
            result = evaluate_no_text_operator_gate(args.artifact_root)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except (OSError, ValueError, Phase1NoTextContractError) as exc:
        print(f"[PHASE1-NO-TEXT][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
