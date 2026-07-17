# douyin-validate-auto-reopen-hard-fix-user-guide.md

## What Changed

The `/accounts/douyin` Validate action now has a strict saved-profile recovery path for browser-backed accounts.

When a Douyin account has saved browser profile metadata but the API process no longer has a live runtime attached, Validate now:

1. detects the missing runtime,
2. reopens the same saved persistent profile,
3. verifies the reopened runtime is bound to the same account and profile,
4. continues browser-backed validation in that runtime,
5. records stage-specific diagnostics for the operator.

## What Operators Should See

On `/accounts/douyin`, the browser health alignment panel now shows safe diagnostics for the latest Validate attempt:

- whether auto-reopen was attempted,
- whether auto-reopen succeeded,
- whether the runtime was reattached,
- whether validation continued after reopen,
- the final validation category.

These fields intentionally avoid raw cookies, tokens, credentials, and private local paths.

## Result Meanings

- `browser_validation_success`: the live or reopened browser profile validated successfully and stale invalid/blocked state was cleared.
- `browser_validation_inconclusive`: the browser profile was reached, but the probe could not prove success or hard failure. This now includes the exact `browser_context_blocked_response` probe path from a reusable browser profile, because page text alone must not hard-block an account that still has reusable browser runtime/cookie material. Retry is appropriate.
- `browser_validation_blocked`: reserved for stronger non-browser-profile block evidence. A reusable browser-profile probe that reports `browser_context_blocked_response` is preserved in diagnostics as `last_browser_validation_blocked_probe_reason` but is not persisted as hard account `BLOCKED` from page text alone.
- `browser_validation_login_required`: the saved browser profile needs login again.
- `profile_reopen_failed`: Validate attempted to reopen the saved profile, but the local browser runtime could not open it. If the detail mentions `TargetClosedError`, the app now retries the saved-profile launch with bundled Chromium before falling back to Chrome; if it still fails, close any visible Douyin/Chrome windows using that profile, reset runtime state, then validate again.
- `runtime_attach_failed`: Validate reopened a runtime, but it was not safely attached to the same account/profile.
- `browser_validation_profile_unavailable`: no reusable saved profile metadata exists for this account.

## Recommended Operator Actions

- If the profile is open and logged in but Validate previously showed `browser_validation_blocked` with `browser_context_blocked_response`, restart the API/web processes so the latest backend code is loaded, refresh `/accounts/douyin`, then Validate again. The next Validate call rewrites the old persisted blocked status to `browser_validation_inconclusive` for this browser-profile probe path.
- If Validate succeeds after auto-reopen, no manual Reopen profile action is needed.
- If Validate is inconclusive, keep the Douyin profile available and retry validation.
- If login is required, open the browser profile, log in again, then Validate.
- If profile reopen fails with `TargetClosedError`, close duplicate browser windows for that profile, click Reset runtime state, then Validate again. The backend will retry the same saved profile instead of creating a new profile.
- If profile reopen still fails, verify local Playwright/browser runtime setup and try opening the saved profile manually.
- If runtime attach fails, reset stuck browser runtime state, then reopen or validate the saved profile again.

## Verification Completed

- Python syntax verification passed with `python -m py_compile apps/api/src/services/douyin_browser_context_registry.py apps/api/tests/test_douyin_browser_connect_service.py`.
- Python syntax verification passed with `python -m py_compile apps/api/src/services/douyin_account_service.py apps/api/tests/test_douyin_account_service.py`.
- Frontend typecheck passed with `npm --prefix apps/web run typecheck`.
- Full pytest verification could not run in the active environment because `pytest` is not installed and Python 3.12 is unavailable on this host.

## Canonical Constraints

This hard fix keeps the same account row, same saved browser profile metadata, same runtime registry, and same browser-primary Intake path. It does not add a second account model, second browser profile model, crawler implementation, or video processing implementation.
