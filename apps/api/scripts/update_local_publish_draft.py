"""Validate and apply operator-assisted metadata to a local export package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    update_local_publish_metadata,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.update_local_publish_draft"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("metadata_json")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        payload = json.loads(Path(args.metadata_json).read_text(encoding="utf-8"))
        result = update_local_publish_metadata(
            root_dir=args.artifact_root,
            target_platform=payload.get("target_platform"),
            title=payload.get("title"),
            caption=payload.get("caption"),
            cta_text=payload.get("cta_text"),
            hashtags=list(payload.get("hashtags") or []),
            generation_source=str(
                payload.get("generation_source") or "operator_assisted_local_v1"
            ),
        )
        print(
            json.dumps(
                {
                    "status": result["publish_draft"]["status"],
                    "platform": result["publish_draft"]["target_platform"],
                    "manifest_sha256": result["package_manifest"][
                        "manifest_sha256"
                    ],
                    "risk_findings": len(
                        result["publish_draft"]["risk_findings"]
                    ),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, json.JSONDecodeError, LocalFinalHandoffError, ValueError) as exc:
        print(f"[PUBLISH-DRAFT][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
