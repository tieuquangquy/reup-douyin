# Phase 5E Operator Confirm Ready Resume

## Current step
- Completed.

## Done
- Audited browser-backed revalidate inconclusive flow.
- Audited hydration readiness gate through `preflight_fetch_readiness(...)`.
- Confirmed the narrowest fix is a metadata-backed operator confirmation state with TTL.

## In progress
- none

## Next exact task
- Operator flow:
  1. `python scripts/douyin_account_readiness.py --account-id <id> --operator-confirm-ready`
  2. `python scripts/hydrate_capture_session_metadata.py --session-id <capture_session_id>`
  3. if hydration hits captcha, reopen profile and solve it manually, then rerun hydration

## Key files
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/src/services/capture_inbox_metadata_hydration_service.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `apps/api/tests/test_capture_inbox_metadata_hydration_service.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
