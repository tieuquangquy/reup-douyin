# douyin-validate-auto-reopen-hard-fix-log.md

## Status

- Audit complete.
- Hard-fix architecture document created before major code changes.
- Backend hard fix implemented.
- Frontend diagnostics implemented.
- Focused tests added.
- Follow-up fix added for `TargetClosedError` during saved profile reopen.
- Follow-up fix added for the exact `browser_context_blocked_response` screenshot path so a reusable browser-profile probe no longer hard-blocks the account from page text alone.
- Backend syntax verification and frontend typecheck passed.

## Audit Findings

- The `/accounts/douyin` Validate button calls `validateDouyinAccount()` from the web API client.
- The FastAPI route is `POST /douyin-accounts/{account_id}/validate` in `apps/api/src/api/routes/douyin_accounts.py`.
- The route calls `DouyinAccountService.validate_account()`.
- Browser-backed validation runs before detached HTTP validation in `DouyinAccountService._validate_with_live_browser_context()`.
- `DouyinBrowserContextRegistry.validate_account_context()` emits `no_live_browser_context` when no runtime record is bound to the account.
- `DouyinAccountService._ensure_persistent_profile_context()` calls the canonical `DouyinBrowserContextRegistry.open_profile_for_account()` helper.
- `open_profile_for_account()` opens the resolved persistent profile and inserts a runtime record into the registry.

## Exact Broken Step

The existing flow could attempt reopen, but it did not enforce the full hard-fix contract:

1. verify that reopen returned an active runtime context,
2. verify the runtime record is bound to the same account,
3. verify profile identity matches the saved profile,
4. re-read the registry summary after reopen,
5. distinguish profile reopen failure from runtime attach failure,
6. record whether validation continued after reopen,
7. avoid collapsing post-reopen `no_live_browser_context` into only generic runtime unavailable.

## Decisions

- Reuse the canonical reopen helper used by separate Reopen profile behavior.
- Do not allocate a new browser profile during Validate when saved profile metadata exists.
- Add service-layer verification around the registry summary instead of duplicating browser launch code.
- Store only safe stage diagnostics in account metadata.
- Preserve browser-primary Intake and canonical account model boundaries.

## Implementation Summary

- Added explicit reopen/rebind verification in `DouyinAccountService._validate_with_live_browser_context()`.
- Added `_browser_reopen_attach_failure_reason()` to distinguish account/profile/context mismatch from browser launch failure.
- Added `_set_browser_validation_failure()` for safe, stage-specific failure metadata.
- Persisted final validation categories for success, inconclusive, blocked, login-required, reopen failure, attach failure, and runtime-unavailable cases.
- Added `auto_reopen_succeeded` to the account response schema and web type.
- Updated `/accounts/douyin` browser health alignment diagnostics to display attempted/succeeded/reattached/continued/final-category values.
- Added English and Vietnamese labels for new diagnostics.
- Added focused backend tests for successful same-profile reopen, runtime reattach, validation continuation, attach failure, reopen failure mapping, and response diagnostics.
- Added `docs/douyin-validate-auto-reopen-hard-fix-user-guide.md`.

## Follow-up Fix For Screenshot Failure

The operator screenshot showed `persistent_profile_open_failed:TargetClosedError`. That means Validate correctly detected the missing runtime and attempted auto-reopen, but Playwright/Chrome closed immediately while launching the saved persistent profile.

The registry reopen helper now:

- tries the bundled Playwright Chromium persistent context before the system Chrome channel,
- retries retryable persistent-profile launch failures such as `TargetClosedError`, process singleton/profile lock errors, and already-in-use profile directory errors,
- logs safe retry diagnostics without cookies, credentials, or private session material,
- still reuses the same saved profile path and does not allocate a replacement profile.

## Follow-up Fix For False Blocked Validation

The second operator screenshot showed a live reusable browser profile, but Validate returned `browser_validation_blocked` with `browser_context_blocked_response`.

Root cause: the browser prevalidation marker list treated the generic Chinese character `验证` as a hard blocked/challenge signal. Douyin can show `验证` in benign login/auth-related text even when authenticated cookies and positive Douyin page markers are present. This caused active browser profiles to be marked blocked too aggressively.

The registry prevalidation now only treats more explicit challenge phrases as blocked, such as `安全验证`, `验证码`, `请完成验证`, `滑块验证`, and `拖动滑块`. Generic `验证` alone no longer hard-blocks an otherwise authenticated reusable profile.

## Final Fix For The Exact `browser_context_blocked_response` Path

The latest screenshot still showed `browser_validation_blocked` because the service layer was mapping any browser registry `blocked` result to a hard account block. That was still too aggressive for a reusable browser-profile validation probe.

The account validation service now maps `result.status == "blocked"` from the live/reopened browser context path to `browser_validation_inconclusive` instead of `browser_validation_blocked`. It preserves `browser_context_blocked_response` in `last_browser_validation_blocked_probe_reason` for diagnostics, increments `browser_context_blocked_count`, and avoids detached HTTP fallback for that validation attempt. This means an active saved browser profile is no longer persisted as account `BLOCKED` from page text alone.

## Files Changed

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-validate-auto-reopen-hard-fix-log.md`
- `docs/douyin-validate-auto-reopen-hard-fix-resume.md`
- `docs/douyin-validate-auto-reopen-hard-fix-user-guide.md`

## Verification Notes

- `python -m pytest apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_douyin_account_service.py -q` could not run because `pytest` is not installed in the active Python environment.
- `py -3.12 -m pytest apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_douyin_account_service.py -q` could not run because Python 3.12 is not installed on this Windows host.
- `python -m py_compile apps/api/src/services/douyin_browser_context_registry.py apps/api/tests/test_douyin_browser_connect_service.py` passed after the `TargetClosedError` and false-blocked fixes.
- `python -m py_compile apps/api/src/services/douyin_account_service.py apps/api/tests/test_douyin_account_service.py` passed after the final `browser_context_blocked_response` service mapping fix.
- `npm --prefix apps/web run typecheck` passed after the `TargetClosedError`, false-blocked, and final service mapping fixes.
