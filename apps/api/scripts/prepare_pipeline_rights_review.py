"""Prepare a read-only rights/music review pack for pending batch cases."""

from __future__ import annotations

import argparse
import json
import sys

from src.services.pipeline_rights_review_pack import (
    PipelineRightsReviewPackError,
    write_pipeline_rights_review_pack,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.prepare_pipeline_rights_review"
    )
    parser.add_argument("run_root")
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        pack = write_pipeline_rights_review_pack(
            args.run_root, case_ids=list(args.case_id or [])
        )
    except (OSError, ValueError, PipelineRightsReviewPackError) as exc:
        print(f"[PIPELINE-RIGHTS-REVIEW][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": pack["status"],
                "case_count": pack["case_count"],
                "all_evidence_valid": pack["all_evidence_valid"],
                "review_pack_sha256": pack["review_pack_sha256"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
