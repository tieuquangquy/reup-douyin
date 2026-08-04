"""Record source and retained-music rights attestation without publishing."""

from __future__ import annotations

import argparse
import json
import sys

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    approve_local_source_rights_and_music,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.approve_local_source_rights_and_music"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("--operator", required=True)
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        result = approve_local_source_rights_and_music(
            root_dir=args.artifact_root,
            operator_id=args.operator,
        )
        print(
            json.dumps(
                {
                    "status": result["rights_music_approval"]["status"],
                    "approval_sha256": result["rights_music_approval"][
                        "approval_sha256"
                    ],
                    "manifest_sha256": result["package_manifest"][
                        "manifest_sha256"
                    ],
                    "next_gate": result["handoff"]["next_gate"],
                    "external_publish_triggered": result["handoff"][
                        "external_publish_triggered"
                    ],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, LocalFinalHandoffError, ValueError) as exc:
        print(f"[RIGHTS-MUSIC-APPROVAL][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
