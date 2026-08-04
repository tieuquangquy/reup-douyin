"""Prepare a read-only, hash-bound operator review pack for a regression run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_operator_review_pack import (
    PipelineOperatorReviewPackError,
    write_operator_review_pack,
)

API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.prepare_pipeline_operator_review"
    )
    parser.add_argument("run_root")
    parser.add_argument("--case-id", action="append", default=[])
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        pack = write_operator_review_pack(
            run_root=args.run_root,
            workspace_root=WORKSPACE_ROOT,
            selected_case_ids=args.case_id,
        )
        print(
            json.dumps(
                {
                    "status": pack["status"],
                    "counts": pack["counts"],
                    "review_pack_sha256": pack["review_pack_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, PipelineOperatorReviewPackError) as exc:
        print(f"[OPERATOR-REVIEW-PACK][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
