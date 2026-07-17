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
from src.models.capture_inbox import CaptureSession, CapturedItem, SourcePlatformEnum


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Douyin captured items for identical finalized modal metric signatures across different aweme ids. Read-only."
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--session-id", type=str, help="Capture session UUID to audit.")
    scope.add_argument("--profile-url", type=str, help="Capture session profile URL / normalized profile identifier to audit.")
    scope.add_argument("--source-platform", type=str, choices=["douyin"], help="Audit all items for a source platform.")
    return parser.parse_args()


def _metadata(item: CapturedItem) -> dict[str, Any]:
    return item.metadata_json if isinstance(item.metadata_json, dict) else {}


def _signature_for_item(item: CapturedItem) -> str | None:
    metadata = _metadata(item)
    raw_metrics = metadata.get("raw_dom_detail_metrics") if isinstance(metadata.get("raw_dom_detail_metrics"), dict) else {}
    duration_seconds = metadata.get("duration_seconds") if metadata.get("duration_seconds") is not None else raw_metrics.get("duration_seconds")
    like_count = metadata.get("like_count") if metadata.get("like_count") is not None else raw_metrics.get("like_count")
    comment_count = metadata.get("comment_count") if metadata.get("comment_count") is not None else raw_metrics.get("comment_count")
    favorite_count = metadata.get("favorite_count") if metadata.get("favorite_count") is not None else raw_metrics.get("favorite_count")
    share_count = metadata.get("share_count") if metadata.get("share_count") is not None else raw_metrics.get("share_count")
    if any(value is None for value in (duration_seconds, like_count, comment_count, favorite_count, share_count)):
        return None
    return f"{duration_seconds}|{like_count}|{comment_count}|{favorite_count}|{share_count}"


def _row(item: CapturedItem, signature: str) -> dict[str, Any]:
    metadata = _metadata(item)
    return {
        "item_id": str(item.id),
        "capture_session_id": str(item.capture_session_id) if item.capture_session_id else None,
        "aweme_id": str(getattr(item, "source_video_external_id", "") or "").strip() or None,
        "signature": signature,
        "data_integrity_status": metadata.get("data_integrity_status"),
        "duplicate_signature_warning": metadata.get("duplicate_signature_warning"),
    }


def main() -> None:
    args = _parse_args()
    session_factory = get_session_factory()
    scope: dict[str, str | None] = {"session_id": args.session_id, "profile_url": args.profile_url, "source_platform": args.source_platform}

    with session_factory() as db:
        if args.session_id:
            session_id = UUID(args.session_id)
            items = db.execute(select(CapturedItem).where(CapturedItem.capture_session_id == session_id)).scalars().all()
        elif args.profile_url:
            sessions = db.execute(
                select(CaptureSession).where(
                    (CaptureSession.profile_url == args.profile_url)
                    | (CaptureSession.normalized_profile_identifier == args.profile_url)
                )
            ).scalars().all()
            session_ids = [session.id for session in sessions]
            items = db.execute(select(CapturedItem).where(CapturedItem.capture_session_id.in_(session_ids))).scalars().all() if session_ids else []
        else:
            items = db.execute(select(CapturedItem).where(CapturedItem.source_platform == SourcePlatformEnum.DOUYIN)).scalars().all()

    by_signature: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        aweme_id = str(getattr(item, "source_video_external_id", "") or "").strip()
        if not aweme_id:
            continue
        signature = _signature_for_item(item)
        if not signature:
            continue
        by_signature[signature].append(_row(item, signature))

    duplicates = {
        signature: rows
        for signature, rows in by_signature.items()
        if len({row["aweme_id"] for row in rows if row["aweme_id"]}) > 1
    }

    print(
        json.dumps(
            {
                "scope": scope,
                "read_only": True,
                "total_items_scanned": len(items),
                "distinct_signatures": len(by_signature),
                "duplicate_metric_groups": len(duplicates),
                "warning_code": "possible_stale_metrics_reuse",
                "duplicates": duplicates,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
