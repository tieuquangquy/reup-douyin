"""Bind explicit non-E2E scopes to a persisted regression batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _sha256_json(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--visual-only", action="append", default=[])
    parser.add_argument("--rationale", required=True)
    args = parser.parse_args()
    run = Path(args.run_root).resolve()
    state_path = run / "batch_regression_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    case_by_id = {
        str(row.get("case_id") or ""): dict(row)
        for row in list(state.get("cases") or [])
        if isinstance(row, dict) and str(row.get("case_id") or "")
    }
    selected = sorted(set(str(value) for value in args.visual_only if str(value)))
    unknown = sorted(set(selected) - set(case_by_id))
    if not selected or unknown:
        raise ValueError(f"Invalid visual-only cases: {unknown}")
    payload = {
        "schema_version": "pipeline_regression_scope_manifest_v1",
        "status": "ACTIVE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus_sha256": dict(state.get("corpus_ref") or {}).get("corpus_sha256"),
        "base_gate_state_ref": {
            "path": state_path.name,
            "sha256": _sha256_file(state_path),
            "run_sha256": state.get("run_sha256"),
        },
        "scopes": {case_id: "VISUAL_LOCALIZATION_ONLY" for case_id in selected},
        "evidence": {
            case_id: {
                "source_video_sha256": case_by_id[case_id].get("source_video_sha256"),
                "current_status": case_by_id[case_id].get("status"),
                "db_source_authority_present": False,
                "external_use_authorized": False,
            }
            for case_id in selected
        },
        "rationale": str(args.rationale),
    }
    payload["scope_manifest_sha256"] = _sha256_json(payload)
    output = run / "regression_scope_manifest.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "visual_only_count": len(selected),
                "scope_manifest_sha256": payload["scope_manifest_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
