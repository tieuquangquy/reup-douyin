from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID


def _bootstrap_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main(argv: list[str] | None = None) -> int:
    _bootstrap_path()

    from src.db.session import get_session_factory
    from src.services.capture_inbox_engagement_backfill_service import CaptureInboxEngagementBackfillService

    parser = argparse.ArgumentParser(
        description="Backfill missing comment/share counts from stored zero-sentinel text and statistics evidence."
    )
    parser.add_argument("--session-id", type=str, default=None, help="Capture session id to backfill.")
    parser.add_argument("--profile-identifier", type=str, default=None, help="Douyin profile sec_uid / identifier.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum number of items to scan.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many ordered items before scanning.")
    parser.add_argument("--batch-size", type=int, default=50, help="Commit batch size.")
    parser.add_argument("--sleep-ms", type=int, default=100, help="Sleep between batches to rate-limit writes.")
    parser.add_argument("--dry-run", action="store_true", help="Report recoverable items without writing.")
    args = parser.parse_args(argv)

    if not args.session_id and not args.profile_identifier:
        parser.error("Provide --session-id or --profile-identifier.")

    session_factory = get_session_factory()
    db = session_factory()
    try:
        service = CaptureInboxEngagementBackfillService(db)
        if args.session_id:
            result = service.backfill_capture_session(
                UUID(args.session_id),
                limit=args.limit,
                offset=args.offset,
                batch_size=args.batch_size,
                sleep_ms=args.sleep_ms,
                dry_run=args.dry_run,
            )
        else:
            result = service.backfill_profile(
                args.profile_identifier,
                limit=args.limit,
                offset=args.offset,
                batch_size=args.batch_size,
                sleep_ms=args.sleep_ms,
                dry_run=args.dry_run,
            )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
