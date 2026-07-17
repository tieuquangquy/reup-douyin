# Phase 5E-R Revalidate Readiness Resume

## Current step
- Phase 5E-R implementation and verification completed.

## Done
- Audited `preflight_fetch_readiness(...)`.
- Audited `validate_account(...)` and live-browser validation path.
- Confirmed the current account is blocked at `account_not_fetch_ready` because status/health were never upgraded after manual browser login.
- Added `--revalidate` to `python scripts/douyin_account_readiness.py`.
- Improved hydration error guidance for `account_not_fetch_ready`.
- Improved readiness listing to show `manual_revalidation_required` when applicable.
- Added focused tests and passed verification.

## In progress
- None.

## Next exact task
- Run the operator flow on the real account:
  - `--open-profile`
  - manual login/captcha
  - `--revalidate`
  - rerun hydration

## Key files
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
