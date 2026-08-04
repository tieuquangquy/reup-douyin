"""Record browser-verified manual-upload evidence and close only on exact match."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    record_local_manual_upload_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.record_local_manual_upload_evidence"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("evidence_json")
    parser.add_argument("--operator", required=True)
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        payload = json.loads(Path(args.evidence_json).read_text(encoding="utf-8"))
        result = record_local_manual_upload_evidence(
            root_dir=args.artifact_root,
            operator_id=args.operator,
            permalink=payload.get("permalink"),
            published_at=payload.get("published_at"),
            timezone_name=payload.get("timezone"),
            verification=dict(payload.get("verification") or {}),
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "evidence_sha256": result["evidence"]["evidence_sha256"],
                    "next_gate": result["handoff"]["next_gate"],
                    "system_external_publish_triggered": False,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, json.JSONDecodeError, LocalFinalHandoffError, ValueError) as exc:
        print(f"[MANUAL-UPLOAD-EVIDENCE][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
