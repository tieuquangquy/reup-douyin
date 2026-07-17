# Phase 5I Hydration Browser Context Resume

## Current step
- Completed.

## Done
- Audited hydration, browser context registry, and account-service integration.
- Confirmed `fetch_detail_page(...)` was failing because no context had been opened before item iteration.
- Added hydration-side ensure-context path before the item loop.
- Added session-level error handling for browser context open/probe failures.
- Updated focused tests and verification.

## In progress
- none

## Next exact task
- Operator flow:
  1. `python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --operator-confirm-ready`
  2. `python scripts/hydrate_capture_session_metadata.py --session-id a57e64d1-a7a8-48e0-b49a-199128b25740`
  3. if hydration reports captcha/block, reopen the saved profile, complete verification manually, then rerun hydration

## Key files
- `apps/api/src/services/capture_inbox_metadata_hydration_service.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/tests/test_capture_inbox_metadata_hydration_service.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
