"""Refresh regression gate state without executing pipeline stages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_batch_regression import (
    PipelineBatchRegressionError,
    refresh_batch_gate_state,
)

API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.refresh_pipeline_regression_gates"
    )
    parser.add_argument("run_root")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        state = refresh_batch_gate_state(
            run_root=args.run_root, workspace_root=WORKSPACE_ROOT
        )
        print(
            json.dumps(
                {
                    "status": state["status"],
                    "failed_count": state["failed_count"],
                    "operator_touch_count": state["operator_touch_count"],
                    "run_sha256": state["run_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, PipelineBatchRegressionError) as exc:
        print(f"[REGRESSION-GATE-REFRESH][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
