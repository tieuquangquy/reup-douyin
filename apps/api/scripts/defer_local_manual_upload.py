"""Defer manual upload without deleting its export or evidence history."""

from __future__ import annotations

import argparse
import json
import sys

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    defer_local_manual_upload,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.defer_local_manual_upload"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", default="operator_will_publish_later")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        result = defer_local_manual_upload(
            root_dir=args.artifact_root,
            operator_id=args.operator,
            reason=args.reason,
        )
        print(
            json.dumps(
                {
                    "status": result["deferral"]["status"],
                    "deferral_sha256": result["deferral"]["deferral_sha256"],
                    "next_gate": result["handoff"]["next_gate"],
                    "archive_preserved": result["deferral"]["archive_preserved"],
                    "evidence_audit_preserved": result["deferral"][
                        "evidence_audit_preserved"
                    ],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, LocalFinalHandoffError, ValueError) as exc:
        print(f"[MANUAL-UPLOAD-DEFER][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
