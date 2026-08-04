"""Approve public-license evidence only for a local regression export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    approve_public_regression_source_rights,
)


API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.approve_public_regression_rights"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("public_source_manifest")
    parser.add_argument("--operator", required=True)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        result = approve_public_regression_source_rights(
            root_dir=args.artifact_root,
            operator_id=args.operator,
            public_source_manifest_path=args.public_source_manifest,
            workspace_root=WORKSPACE_ROOT,
        )
    except (OSError, ValueError, LocalFinalHandoffError) as exc:
        print(f"[PUBLIC-REGRESSION-RIGHTS][FAIL] {exc}", flush=True)
        return 1
    approval = result["rights_music_approval"]
    print(
        json.dumps(
            {
                "status": approval["status"],
                "verification_method": approval["verification_method"],
                "approval_sha256": approval["approval_sha256"],
                "external_publish_triggered": approval["external_publish_triggered"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
