"""Record FINAL_APPROVED without creating an export package."""

from __future__ import annotations

import argparse
import json
import sys

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    record_local_final_approval,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.record_final_approval")
    parser.add_argument("artifact_root")
    parser.add_argument("source_video_id")
    parser.add_argument("source_video_external_id")
    parser.add_argument("--operator", required=True)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        approval = record_local_final_approval(
            root_dir=args.artifact_root,
            source_video_id=args.source_video_id,
            source_video_external_id=args.source_video_external_id,
            operator_id=args.operator,
        )
    except LocalFinalHandoffError as exc:
        print(json.dumps({"status": "FAIL", "message": str(exc)}))
        return 1
    print(
        json.dumps(
            {
                "status": approval["status"],
                "approval_sha256": approval["approval_sha256"],
                "external_publish_triggered": approval["external_publish_triggered"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
