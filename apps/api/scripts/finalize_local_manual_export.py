"""Build the final hash-bound manual-upload ZIP without publishing."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    finalize_local_manual_export,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.finalize_local_manual_export"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("--operator", required=True)
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        result = finalize_local_manual_export(
            root_dir=args.artifact_root,
            operator_id=args.operator,
        )
        print(
            json.dumps(
                {
                    "status": result["manual_export_handoff"]["status"],
                    "archive": result["manual_export_handoff"]["archive"],
                    "manifest_sha256": result["package_manifest"][
                        "manifest_sha256"
                    ],
                    "next_action": result["manual_export_handoff"][
                        "next_action"
                    ],
                    "external_publish_triggered": result[
                        "manual_export_handoff"
                    ]["external_publish_triggered"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, LocalFinalHandoffError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[MANUAL-EXPORT][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
