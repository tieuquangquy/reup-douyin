from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import time
from uuid import UUID


def _bootstrap_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _require_account_id(raw_value: str | None, *, argument_name: str) -> UUID:
    if not raw_value:
        raise ValueError(f"{argument_name} is required for this action.")
    return UUID(raw_value)


def _classify_open_profile_failure(reason: str | None) -> tuple[str, str]:
    normalized = (reason or "").lower()
    if "browser_binary_missing" in normalized or "dependency_missing" in normalized:
        return "browser_executable_missing", "Browser runtime dependencies are missing. Install Playwright/Chromium for apps/api and retry."
    if "profile_locked_by_existing_process" in normalized:
        return "profile_locked", "The saved browser profile is already locked by another browser process."
    if "managed_runtime_reopen_failed" in normalized or "browser_launch_failed" in normalized:
        return "browser_launch_failed", "The saved browser profile could not be opened in a managed browser window."
    if "timed_out" in normalized or "timeout" in normalized:
        return "launch_timeout", "Opening the saved browser profile timed out."
    return "unknown_open_profile_failure", reason or "Open profile failed for an unknown reason."


def _classify_revalidate_failure(*, error_code: str | None, error_message: str | None, validation_status: str | None) -> str:
    normalized_code = (error_code or "").lower()
    normalized_message = (error_message or "").lower()
    normalized_status = (validation_status or "").lower()
    if "profile_locked_by_existing_process" in normalized_message:
        return "browser_profile_locked"
    if normalized_code in {"expired_session", "browser_validation_login_required"} or normalized_status == "browser_validation_login_required":
        return "manual_login_required"
    if normalized_code in {"browser_validation_captcha_required", "challenge_cooldown_active", "challenge_recheck_required"}:
        return "captcha_required"
    if normalized_code in {"browser_validation_challenge_required", "browser_validation_manual_verification_required"}:
        return "captcha_required"
    if normalized_code in {"blocked_response", "browser_validation_blocked"}:
        return "douyin_blocked"
    if normalized_code == "browser_validation_runtime_unavailable":
        return "browser_profile_locked" if "profile_locked_by_existing_process" in normalized_message else "profile_open_failed"
    return normalized_code or "unknown_fetch_failure"


def _open_profile_recommendation(code: str, account_id: UUID) -> tuple[str, str]:
    if code == "browser_executable_missing":
        return (
            "python -m playwright install chromium",
            "Install the local browser runtime for apps/api, then rerun --open-profile.",
        )
    if code == "profile_locked":
        return (
            f"python scripts/douyin_account_readiness.py --account-id {account_id} --open-profile --timeout-seconds 300",
            "Close the external browser process using this saved profile, then rerun --open-profile.",
        )
    if code == "launch_timeout":
        return (
            f"python scripts/douyin_account_readiness.py --account-id {account_id} --open-profile --timeout-seconds 300",
            "Check the local browser runtime and profile path, then rerun --open-profile.",
        )
    return (
        f"python scripts/douyin_account_readiness.py --account-id {account_id} --open-profile --timeout-seconds 300",
        "Check the local browser runtime/browser profile configuration, then rerun --open-profile.",
    )


def main(argv: list[str] | None = None) -> int:
    _bootstrap_path()

    from src.db.session import get_session_factory
    from src.services.douyin_account_service import DouyinAccountError, DouyinAccountService
    from src.services.douyin_browser_context_registry import douyin_browser_context_registry

    parser = argparse.ArgumentParser(description="Inspect and prepare browser-profile-backed Douyin accounts for hydration.")
    parser.add_argument("--include-deleted", action="store_true", help="Include soft-deleted accounts in readiness output.")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip preflight/readiness probes and only report stored state.")
    parser.add_argument("--create-browser-account", action="store_true", help="Create a fresh browser-profile-backed Douyin account row.")
    parser.add_argument("--display-name", type=str, default=None, help="Display name for a newly created browser-backed account.")
    parser.add_argument("--profile-path", type=str, default=None, help="Explicit browser profile path to attach or create with.")
    parser.add_argument("--profile-id", type=str, default=None, help="Explicit browser profile id to attach or create with.")
    parser.add_argument("--account-id", type=str, default=None, help="Existing account id for attach/default/open actions.")
    parser.add_argument("--set-default", action="store_true", help="Mark the target account as the default Douyin account.")
    parser.add_argument("--attach-profile", action="store_true", help="Attach the given --profile-path to the target account.")
    parser.add_argument("--open-profile", action="store_true", help="Open/reopen the target browser profile for manual Douyin login.")
    parser.add_argument("--revalidate", action="store_true", help="Run browser-profile-backed revalidation and refresh account fetch readiness.")
    parser.add_argument("--mark-challenge-solved", action="store_true", help="Clear stale challenge/cooldown state after manual browser verification, then require revalidate.")
    parser.add_argument("--operator-confirm-ready", action="store_true", help="Allow browser-backed hydration to proceed for a short TTL after manual profile verification.")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Browser connect timeout when --open-profile is used.")
    args = parser.parse_args(argv)

    session_factory = get_session_factory()
    db = session_factory()
    try:
        account_service = DouyinAccountService(db)
        action_results: list[dict] = []
        target_account_id: UUID | None = UUID(args.account_id) if args.account_id else None

        if args.create_browser_account:
            if not args.display_name or not args.display_name.strip():
                raise ValueError("--display-name is required with --create-browser-account.")
            created = account_service.create_browser_profile_account(
                display_name=args.display_name,
                browser_profile_path=args.profile_path,
                browser_profile_id=args.profile_id,
                is_default=args.set_default and target_account_id is None,
            )
            target_account_id = created.id
            action_results.append(
                {
                    "action": "create_browser_account",
                    "account_id": str(created.id),
                    "browser_profile_id": (created.metadata_json or {}).get("browser_profile_id"),
                    "browser_profile_path": (created.metadata_json or {}).get("browser_profile_path"),
                }
            )

        if args.attach_profile:
            account_id = target_account_id or _require_account_id(args.account_id, argument_name="--account-id")
            if not args.profile_path:
                raise ValueError("--profile-path is required with --attach-profile.")
            attached = account_service.attach_browser_profile(
                account_id,
                browser_profile_path=args.profile_path,
                browser_profile_id=args.profile_id,
            )
            target_account_id = attached.id
            action_results.append(
                {
                    "action": "attach_profile",
                    "account_id": str(attached.id),
                    "browser_profile_id": (attached.metadata_json or {}).get("browser_profile_id"),
                    "browser_profile_path": (attached.metadata_json or {}).get("browser_profile_path"),
                }
            )

        if args.set_default and not args.create_browser_account:
            account_id = target_account_id or _require_account_id(args.account_id, argument_name="--account-id")
            defaulted = account_service.set_default_account(account_id)
            target_account_id = defaulted.id
            action_results.append({"action": "set_default", "account_id": str(defaulted.id)})

        if args.open_profile:
            account_id = target_account_id or _require_account_id(args.account_id, argument_name="--account-id")
            account = account_service.get_account(account_id)
            metadata = dict(getattr(account, "metadata_json", None) or {})
            summary = douyin_browser_context_registry.open_profile_for_account(
                workspace_id=account.workspace_id,
                account_connection_id=account_id,
                browser_profile_id=metadata.get("browser_profile_id") if isinstance(metadata.get("browser_profile_id"), str) else None,
                browser_profile_path=metadata.get("browser_profile_path") if isinstance(metadata.get("browser_profile_path"), str) else None,
                user_agent=account.user_agent,
                proxy_url=account.proxy_url,
            )
            if summary.status != "active":
                code, message = _classify_open_profile_failure(summary.reason)
                recommended_command, next_step = _open_profile_recommendation(code, account_id)
                print(
                    json.dumps(
                        {
                            "success": False,
                            "code": code,
                            "message": message,
                            "account_id": str(account_id),
                            "browser_profile_path": summary.browser_profile_path,
                            "recommended_command": recommended_command,
                            "next_step": next_step,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 1
            target_account_id = account_id
            payload = {
                "success": True,
                "action": "open_profile",
                "open_profile_status": "opened",
                "account_id": str(account_id),
                "browser_profile_id": summary.browser_profile_id or metadata.get("browser_profile_id"),
                "browser_profile_path": summary.browser_profile_path or metadata.get("browser_profile_path"),
                "open_url": "https://www.douyin.com",
                "next_step": "Log into https://www.douyin.com in the opened browser, complete captcha if shown, then run --revalidate.",
                "operator_note": "This command keeps the browser profile open until timeout or Ctrl+C so the visible browser window stays alive.",
                "hold_open_seconds": args.timeout_seconds,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            deadline = time.monotonic() + max(1, int(args.timeout_seconds))
            try:
                while time.monotonic() < deadline:
                    current = douyin_browser_context_registry.summary_for_account(account_id)
                    if current.status != "active":
                        break
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                douyin_browser_context_registry.close_for_account(account_id, reason="operator_open_profile_command_finished")
            return 0

        if args.revalidate:
            account_id = target_account_id or _require_account_id(args.account_id, argument_name="--account-id")
            account, valid, reason = account_service.validate_account(account_id, validation_source="readiness_revalidate")
            target_account_id = account_id
            readiness_row = next(
                (row for row in account_service.readiness_rows(include_deleted=False, run_preflight=True) if row.account_id == account_id),
                None,
            )
            if valid and readiness_row is not None and readiness_row.readiness_status == "READY":
                payload = {
                    "success": True,
                    "action": "revalidate",
                    "account_id": str(account.id),
                    "status": account.status.value,
                    "health_status": account.health_status.value,
                    "readiness_status": readiness_row.readiness_status,
                    "selected_fetch_path": readiness_row.selected_fetch_path,
                    "reason": reason,
                    "next_command": "python scripts/hydrate_capture_session_metadata.py --session-id <capture_session_id>",
                }
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            failure_code = account.last_error_code or account.last_validation_status or reason or "unknown_fetch_failure"
            failure_message = account.last_error_message or reason or "Douyin browser-profile revalidation did not reach a fetch-ready state."
            failure_code = _classify_revalidate_failure(
                error_code=account.last_error_code,
                error_message=account.last_error_message,
                validation_status=account.last_validation_status,
            )
            payload = {
                "success": False,
                "action": "revalidate",
                "code": failure_code,
                "message": failure_message,
                "account_id": str(account.id),
                "status": account.status.value,
                "health_status": account.health_status.value,
                "readiness_status": readiness_row.readiness_status if readiness_row is not None else "NOT_READY",
                "recommended_command": (
                    f"python scripts/douyin_account_readiness.py --account-id {account_id} --revalidate --timeout-seconds {min(args.timeout_seconds, 120)}"
                ),
                "fallback_command": (
                    f"python scripts/douyin_account_readiness.py --account-id {account_id} --open-profile --timeout-seconds 300"
                ),
                "next_step": (
                    "Close other Chrome/Chromium windows using this profile, remove SingletonLock if no browser is running, then rerun --revalidate."
                    if failure_code == "browser_profile_locked"
                    else "Close browser processes using this saved profile or create a fresh browser profile, then rerun --revalidate."
                    if failure_code == "profile_open_failed"
                    else "Log into Douyin or complete captcha in the opened profile, then rerun --revalidate."
                ),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1

        if args.mark_challenge_solved:
            account_id = target_account_id or _require_account_id(args.account_id, argument_name="--account-id")
            account = account_service.clear_challenge_state_for_revalidation(account_id)
            payload = {
                "success": True,
                "action": "mark_challenge_solved",
                "account_id": str(account.id),
                "status": account.status.value,
                "health_status": account.health_status.value,
                "next_command": (
                    f"python scripts/douyin_account_readiness.py --account-id {account_id} --revalidate --timeout-seconds 120"
                ),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.operator_confirm_ready:
            account_id = target_account_id or _require_account_id(args.account_id, argument_name="--account-id")
            account = account_service.operator_confirm_ready(account_id)
            payload = {
                "success": True,
                "action": "operator_confirm_ready",
                "account_id": str(account.id),
                "status": account.status.value,
                "health_status": account.health_status.value,
                "readiness_status": "OPERATOR_CONFIRMED",
                "warning": "Manual confirmation only. Hydration may still hit captcha.",
                "next_command": "python scripts/hydrate_capture_session_metadata.py --session-id <capture_session_id>",
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        rows = account_service.readiness_rows(
            include_deleted=args.include_deleted,
            run_preflight=not args.skip_preflight,
        )
        payload = {
            "success": True,
            "actions": action_results,
            "accounts": [row.to_dict() for row in rows],
            "checked_account_count": len(rows),
            "target_account_id": str(target_account_id) if target_account_id else None,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except (DouyinAccountError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": exc.__class__.__name__,
                    "message": str(exc),
                    "recommended_command": "python scripts/douyin_account_readiness.py",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
