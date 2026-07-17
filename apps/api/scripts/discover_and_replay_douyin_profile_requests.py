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
    from src.services.capture_inbox_request_replay_service import (
        CaptureInboxRequestReplayError,
        CaptureInboxRequestReplayService,
    )

    parser = argparse.ArgumentParser(description="Discover and replay Douyin profile/feed requests for batch aweme metadata.")
    parser.add_argument("--session-id", type=str, required=True, help="Capture session id to update.")
    parser.add_argument("--account-id", type=str, default=None, help="Optional Douyin account id override.")
    parser.add_argument("--max-pages", type=int, default=3, help="Maximum replay pages.")
    parser.add_argument("--delay-seconds", type=float, default=2.0, help="Delay between replay pages.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0, help="Browser page/replay timeout.")
    args = parser.parse_args(argv)

    session_factory = get_session_factory()
    db = session_factory()
    try:
        service = CaptureInboxRequestReplayService(db)
        result = service.discover_and_replay(
            UUID(args.session_id),
            account_connection_id=UUID(args.account_id) if args.account_id else None,
            max_pages=args.max_pages,
            delay_seconds=args.delay_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    except CaptureInboxRequestReplayError as exc:
        payload = {
            "success": False,
            "code": exc.code,
            "message": exc.message,
        }
        if exc.code == "no_aweme_list_request_found":
            payload["next_step"] = "Open the Douyin profile/feed page in the saved browser profile, scroll naturally, then rerun discovery."
        if exc.code in {"captcha_or_login_wall_detected", "browser_context_unavailable", "browser_profile_locked", "profile_open_failed", "browser_launch_timeout", "manual_login_required"}:
            account_id = args.account_id or exc.details.get("account_id") or exc.details.get("selected_account_id")
            if account_id:
                payload["recommended_command"] = (
                    f"python scripts/douyin_account_readiness.py --account-id {account_id} --open-profile --timeout-seconds 300"
                )
            payload["next_step"] = "Open/login the saved browser profile, confirm the Douyin profile page loads normally, then rerun request replay."
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
