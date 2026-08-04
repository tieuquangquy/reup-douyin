"""Build a versioned, non-locking pipeline recipe candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_recipe_candidate import (
    PipelineRecipeCandidateError,
    build_pipeline_recipe_candidate,
)


API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_pipeline_recipe_candidate"
    )
    parser.add_argument("base_recipe")
    parser.add_argument("report")
    parser.add_argument("fixture")
    parser.add_argument("fixture_report")
    parser.add_argument("output")
    parser.add_argument("--release-label", default="V24.1")
    parser.add_argument("--e2e-report")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        candidate = build_pipeline_recipe_candidate(
            workspace_root=WORKSPACE_ROOT,
            base_recipe_path=args.base_recipe,
            report_path=args.report,
            fixture_path=args.fixture,
            fixture_report_path=args.fixture_report,
            output_path=args.output,
            release_label=args.release_label,
            e2e_report_path=args.e2e_report,
        )
    except (OSError, ValueError, PipelineRecipeCandidateError) as exc:
        print(f"[PIPELINE-RECIPE-CANDIDATE][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": candidate["status"],
                "release_label": candidate["release_label"],
                "candidate_sha256": candidate["candidate_sha256"],
                "blockers": candidate["blockers"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
