"""Import an approved adaptive final into canonical DB and ExportPackage state."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from src.db.session import get_session_factory
from src.services.adaptive_final_db_handoff import (
    AdaptiveFinalDbHandoffError,
    build_default_adaptive_final_db_handoff_service,
)


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.import_adaptive_final_to_db")
    parser.add_argument("artifact_root")
    parser.add_argument("source_video_id")
    parser.add_argument("--queue-item-id")
    parser.add_argument("--without-export-package", action="store_true")
    parser.add_argument("--recipe-lock", required=True)
    parser.add_argument("--expected-recipe-release", default="V22.1")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        root = Path(args.artifact_root).resolve()
        with get_session_factory()() as db:
            result = build_default_adaptive_final_db_handoff_service(db).import_final(
                root_dir=root,
                source_video_id=UUID(str(args.source_video_id)),
                queue_item_id=(
                    UUID(str(args.queue_item_id)) if args.queue_item_id else None
                ),
                create_export_package=not bool(args.without_export_package),
                recipe_lock_path=Path(args.recipe_lock),
                expected_recipe_release=str(args.expected_recipe_release),
            )
        result["recorded_at"] = datetime.now(UTC).isoformat()
        _write_json_atomic(root / "phase5_db_handoff.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except (OSError, ValueError, AdaptiveFinalDbHandoffError) as exc:
        print(f"[ADAPTIVE-DB-HANDOFF][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
