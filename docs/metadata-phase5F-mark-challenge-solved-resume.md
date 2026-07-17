# Phase 5F Mark Challenge Solved Resume

## Current step
- Completed.

## Done
- Audited existing challenge recovery methods.
- Confirmed current `mark_challenge_solved(...)` service performs immediate post-solve recheck, which is not the same as a manual stale-state clear.
- Added `clear_challenge_state_for_revalidation(...)` in `DouyinAccountService`.
- Added `--mark-challenge-solved` to `scripts/douyin_account_readiness.py`.
- Added focused service/script tests.
- Ran unittest and compile verification.

## In progress
- none

## Next exact task
- Operator flow:
  1. `python scripts/douyin_account_readiness.py --account-id <id> --mark-challenge-solved`
  2. `python scripts/douyin_account_readiness.py --account-id <id> --revalidate --timeout-seconds 120`
  3. rerun hydration if revalidate passes

## Key files
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
