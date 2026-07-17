from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.session import get_session_factory
from src.models.capture_inbox import CaptureSession, CapturedItem


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit duplicate modal metric signatures in captured item metadata for one capture session."
    )
    parser.add_argument("--session-id", type=str, required=True)
    return parser.parse_args()


def _signature_for_item(item: CapturedItem) -> str | None:
    metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
    explicit = metadata.get("metric_signature")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    aweme_id = str(getattr(item, "source_video_external_id", "") or "").strip()
    like_count = metadata.get("like_count")
    comment_count = metadata.get("comment_count")
    favorite_count = metadata.get("favorite_count")
    share_count = metadata.get("share_count")
    if not aweme_id:
        return None
    return f"sig:{aweme_id}:{like_count}:{comment_count}:{favorite_count}:{share_count}"


def main() -> None:
    args = _parse_args()
    session_id = UUID(args.session_id)
    session_factory = get_session_factory()

    with session_factory() as db:
        session = db.execute(select(CaptureSession).where(CaptureSession.id == session_id)).scalar_one_or_none()
        if session is None:
            raise SystemExit("Capture session not found")

        items = db.execute(select(CapturedItem).where(CapturedItem.capture_session_id == session_id)).scalars().all()

    by_signature: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        signature = _signature_for_item(item)
        if not signature:
            continue
        by_signature[signature].append(
            {
                "item_id": str(item.id),
                "aweme_id": str(getattr(item, "source_video_external_id", "") or "").strip() or None,
            }
        )

    duplicates = {
        signature: rows
        for signature, rows in by_signature.items()
        if len(rows) > 1
    }

    print(
        json.dumps(
            {
                "capture_session_id": str(session_id),
                "total_items": len(items),
                "distinct_signatures": len(by_signature),
                "duplicate_signature_groups": len(duplicates),
                "duplicates": duplicates,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
