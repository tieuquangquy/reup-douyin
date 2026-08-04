"""Build hash-bound, non-authoritative input for a Phase-2 batch proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--output")
    args = parser.parse_args()
    run = Path(args.run_root).resolve()
    state_path = run / "batch_regression_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    cases: dict[str, dict] = {}
    for raw in list(state.get("cases") or []):
        if not isinstance(raw, dict):
            continue
        case_id = str(raw.get("case_id") or "")
        root = run / case_id
        queue = root / "phase2_review_queue.json"
        if case_id and queue.is_file():
            cases[case_id] = {
                "review_queue_sha256": _sha256_file(queue),
                "recommendations": {},
            }
    if not cases:
        raise ValueError("No Phase-2 review queues were found")
    payload = {
        "schema_version": "phase2_batch_review_recommendations_v1",
        "status": "NON_AUTHORITATIVE_REVIEW_INPUT",
        "batch_state_ref": {
            "path": state_path.name,
            "sha256": _sha256_file(state_path),
        },
        "review_policy": {
            "exact_text_required": True,
            "local_ocr_default": True,
            "llm_context_correction_is_proposal_only": True,
            "overwrite_master_timeline": False,
            "authority_v3_6_full_duration": False,
        },
        "cases": cases,
    }
    output = (
        Path(args.output).resolve()
        if args.output
        else run / "phase2_ocr_review_recommendations.json"
    )
    _write_json_atomic(output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "case_count": len(cases),
                "object_count": sum(
                    len(
                        list(
                            json.loads(
                                (run / case_id / "phase2_review_queue.json").read_text(
                                    encoding="utf-8"
                                )
                            ).get("content_objects")
                            or []
                        )
                    )
                    for case_id in cases
                ),
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
