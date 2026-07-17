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
    from src.services.capture_inbox_metadata_hydration_service import (
        CaptureInboxMetadataHydrationError,
        CaptureInboxMetadataHydrationService,
    )
    from src.services.douyin_account_service import DouyinAccountService

    parser = argparse.ArgumentParser(description="Browser-assist metadata hydration for Capture Inbox items.")
    parser.add_argument("--session-id", type=str, default=None, help="Explicit capture_session_id to hydrate.")
    parser.add_argument("--account-id", type=str, default=None, help="Explicit Douyin account connection id to use.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of items to hydrate.")
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="Per-item browser fetch timeout.")
    parser.add_argument("--concurrency-limit", type=int, default=2, help="Requested hydration concurrency limit.")
    parser.add_argument("--force", action="store_true", help="Hydrate even items that already look complete.")
    args = parser.parse_args(argv)

    session_factory = get_session_factory()
    db = session_factory()
    try:
        service = CaptureInboxMetadataHydrationService(db)
        account_id = UUID(args.account_id) if args.account_id else None
        if args.session_id:
            result = service.hydrate_capture_session_metadata(
                UUID(args.session_id),
                account_connection_id=account_id,
                limit=args.limit,
                timeout_seconds=args.timeout_seconds,
                concurrency_limit=args.concurrency_limit,
                force=args.force,
            )
        else:
            result = service.hydrate_latest_capture_session_metadata(
                account_connection_id=account_id,
                limit=args.limit,
                timeout_seconds=args.timeout_seconds,
                concurrency_limit=args.concurrency_limit,
                force=args.force,
            )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    except CaptureInboxMetadataHydrationError as exc:
        payload = {
            "success": False,
            "code": exc.code,
            "message": exc.message,
        }
        if exc.code == "browser_profile_required":
            payload["recommended_command"] = "python scripts/douyin_account_readiness.py"
            payload["next_step"] = (
                "Create or attach a browser-profile-backed Douyin account, log into that saved profile once, "
                "then rerun metadata hydration."
            )
        if exc.code in {"captcha_required", "detail_page_blocked"}:
            account_id = exc.details.get("account_id")
            timeout_seconds = 300
            if account_id:
                payload["account_id"] = account_id
                payload["recommended_command"] = (
                    f"python scripts/douyin_account_readiness.py --account-id {account_id} "
                    f"--open-profile --timeout-seconds {timeout_seconds}"
                )
            payload["next_step"] = (
                "Complete captcha/login in the opened browser profile, open one Douyin video page manually to confirm access, "
                "then rerun metadata hydration."
            )
            for key in (
                "capture_session_id",
                "selected_fetch_path",
                "hydrated_count",
                "skipped_count",
                "failed_count",
                "captcha_required_count",
                "detail_page_blocked_count",
                "next_operator_action",
            ):
                if key in exc.details:
                    payload[key] = exc.details[key]
        if exc.code in {"browser_context_unavailable", "browser_profile_locked", "profile_open_failed", "browser_launch_timeout", "manual_login_required"}:
            account_id = exc.details.get("account_id") or exc.details.get("selected_account_id")
            timeout_seconds = 300
            if account_id:
                payload["account_id"] = account_id
                payload["recommended_command"] = (
                    f"python scripts/douyin_account_readiness.py --account-id {account_id} "
                    f"--open-profile --timeout-seconds {timeout_seconds}"
                )
            payload["next_step"] = (
                "Open/login the saved browser profile or fix browser launch, then rerun metadata hydration."
                if exc.code != "browser_profile_locked"
                else "Close other Chrome/Chromium windows using this profile, remove SingletonLock if no browser is running, then rerun metadata hydration."
            )
            for key in (
                "selected_fetch_path",
                "total_items_considered",
                "detail_hydrate_attempted_count",
            ):
                if key in exc.details:
                    payload[key] = exc.details[key]
        if exc.code == "account_not_fetch_ready":
            resolved_account_id = args.account_id
            if not resolved_account_id:
                default_account = DouyinAccountService(db).default_account()
                if default_account is not None:
                    resolved_account_id = str(default_account.id)
            if resolved_account_id:
                payload["account_id"] = resolved_account_id
                payload["recommended_command"] = (
                    f"python scripts/douyin_account_readiness.py --account-id {resolved_account_id} --revalidate --timeout-seconds 120"
                )
                payload["fallback_command"] = (
                    f"python scripts/douyin_account_readiness.py --account-id {resolved_account_id} --open-profile --timeout-seconds 300"
                )
                payload["operator_confirm_command"] = (
                    f"python scripts/douyin_account_readiness.py --account-id {resolved_account_id} --operator-confirm-ready"
                )
            else:
                payload["recommended_command"] = "python scripts/douyin_account_readiness.py"
            payload["next_step"] = (
                "Open the saved browser profile if needed, log into Douyin or complete captcha, then rerun --revalidate before metadata hydration."
            )
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
