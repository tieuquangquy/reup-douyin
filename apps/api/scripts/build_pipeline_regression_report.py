"""Build JSON and Markdown metrics from a completed batch regression state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_regression_report import (
    PipelineRegressionReportError,
    write_regression_report,
)

API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_pipeline_regression_report"
    )
    parser.add_argument("run_root")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        report = write_regression_report(
            run_root=args.run_root,
            workspace_root=WORKSPACE_ROOT,
        )
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "phase1_pass_count": report["phase1_pass_count"],
                    "phase2_execution_pass_count": report[
                        "phase2_execution_pass_count"
                    ],
                    "operator_review_object_count": report[
                        "operator_review_object_count"
                    ],
                    "report_sha256": report["report_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, PipelineRegressionReportError) as exc:
        print(f"[REGRESSION-REPORT][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
