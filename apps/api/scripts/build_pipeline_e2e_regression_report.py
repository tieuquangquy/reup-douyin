"""Build hash-bound end-to-end evidence from completed controlled-pilot cases."""

from __future__ import annotations

import argparse
import json
import sys

from src.services.pipeline_e2e_regression_report import (
    PipelineE2eRegressionReportError,
    write_e2e_regression_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_pipeline_e2e_regression_report"
    )
    parser.add_argument("run_root")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        report = write_e2e_regression_report(args.run_root)
    except (OSError, ValueError, PipelineE2eRegressionReportError) as exc:
        print(f"[E2E-REGRESSION-REPORT][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "case_count": report["case_count"],
                "passed_count": report["passed_count"],
                "db_handoff_ready_count": report["db_handoff_ready_count"],
                "report_sha256": report["report_sha256"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
