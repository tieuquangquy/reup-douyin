"""Create a local, hash-bound final approval and export handoff package."""

from __future__ import annotations

import argparse
import json
import sys

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    create_local_final_handoff,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.run_final_export_handoff"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("source_video_id")
    parser.add_argument("source_video_external_id")
    parser.add_argument("--operator", default="local_operator")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        result = create_local_final_handoff(
            root_dir=args.artifact_root,
            source_video_id=args.source_video_id,
            source_video_external_id=args.source_video_external_id,
            operator_id=args.operator,
        )
        print(
            json.dumps(
                {
                    "status": result["handoff"]["status"],
                    "package_root": str(result["package_root"]),
                    "final_approval_sha256": result["final_approval"][
                        "approval_sha256"
                    ],
                    "manifest_sha256": result["package_manifest"][
                        "manifest_sha256"
                    ],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except LocalFinalHandoffError as exc:
        print(f"[FINAL-HANDOFF][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
