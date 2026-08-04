"""Build a hash-bound Phase-4-preflight regression closeout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_regression_closeout import (
    PipelineRegressionCloseoutError,
    write_pipeline_regression_closeout,
)


API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_pipeline_regression_closeout"
    )
    parser.add_argument("run_root")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        closeout = write_pipeline_regression_closeout(
            run_root=args.run_root, workspace_root=WORKSPACE_ROOT
        )
    except (OSError, ValueError, PipelineRegressionCloseoutError) as exc:
        print(f"[REGRESSION-CLOSEOUT][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": closeout["status"],
                "case_count": closeout["case_count"],
                "ready_for_phase4": closeout["counts"]["ready_for_phase4"],
                "closeout_sha256": closeout["closeout_sha256"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
