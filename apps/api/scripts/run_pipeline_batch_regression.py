"""Run/resume the operator-gated local regression corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_batch_regression import (
    PipelineBatchRegressionError,
    PipelineBatchRegressionRunner,
)

API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.run_pipeline_batch_regression"
    )
    parser.add_argument("corpus_json")
    parser.add_argument("run_root")
    parser.add_argument("--phase2-provider", default="local")
    parser.add_argument(
        "--stop-after-phase2",
        action="store_true",
        help="Persist the current Phase 2 gate without executing Phase 3+.",
    )
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        result = PipelineBatchRegressionRunner(
            workspace_root=WORKSPACE_ROOT,
            api_root=API_ROOT,
            corpus_path=args.corpus_json,
            run_root=args.run_root,
            phase2_provider=args.phase2_provider,
            stop_after_phase2=args.stop_after_phase2,
        ).run()
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "case_count": result["case_count"],
                    "failed_count": result["failed_count"],
                    "operator_touch_count": result["operator_touch_count"],
                    "run_sha256": result["run_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0 if result["status"] != "FAILED" else 1
    except (OSError, ValueError, PipelineBatchRegressionError) as exc:
        print(f"[BATCH-REGRESSION][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
