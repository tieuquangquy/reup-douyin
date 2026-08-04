"""Lock the controlled-pilot recipe to corpus and regression evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.pipeline_recipe_lock import (
    PipelineRecipeLockError,
    lock_pipeline_recipe,
)

API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.lock_pipeline_recipe")
    parser.add_argument("corpus_json")
    parser.add_argument("report_json")
    parser.add_argument("output_dir")
    parser.add_argument("--e2e-report")
    parser.add_argument("--phase4-closeout")
    parser.add_argument("--candidate")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--release-label")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        result = lock_pipeline_recipe(
            workspace_root=WORKSPACE_ROOT,
            corpus_path=args.corpus_json,
            report_path=args.report_json,
            e2e_report_path=args.e2e_report,
            closeout_path=args.phase4_closeout,
            candidate_path=args.candidate,
            output_dir=args.output_dir,
            operator_id=args.operator,
            release_label=args.release_label,
        )
        recipe = result["recipe"]
        print(
            json.dumps(
                {
                    "status": recipe["status"],
                    "recipe_sha256": recipe["recipe_sha256"],
                    "versioned_path": str(result["versioned_path"]),
                    "universal_video_support": recipe["claims"][
                        "universal_video_support"
                    ],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, PipelineRecipeLockError) as exc:
        print(f"[PIPELINE-RECIPE-LOCK][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
