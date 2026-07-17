# Phase 5E-T TargetClosed Revalidate Resume

## Current step
- Completed.

## Done
- Audited `DouyinAccountService.validate_account(...)`, `_validate_with_live_browser_context(...)`, `_ensure_persistent_profile_context(...)`.
- Audited `DouyinBrowserContextRegistry.open_profile_for_account(...)` and `validate_account_context(...)`.
- Confirmed the failure is in browser-backed page recovery, not metadata hydration logic.

## In progress
- none

## Next exact task
- Operator flow:
  1. `python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --mark-challenge-solved`
  2. `python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --revalidate --timeout-seconds 120`
  3. if revalidate passes, rerun metadata hydration

## Key files
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
