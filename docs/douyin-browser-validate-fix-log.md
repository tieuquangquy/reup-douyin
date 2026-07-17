# douyin-browser-validate-fix-log.md

## Status

- Audit complete.
- Architecture note created before major code changes.
- Browser-backed Validate implementation updated.
- Operator wording and focused regression tests updated.
- Backend focused tests and frontend typecheck passed.

## Audit Findings

- The Validate button in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:293) calls [`validateDouyinAccount()`](apps/web/src/lib/api.ts:247).
- The API route [`validate_douyin_account()`](apps/api/src/api/routes/douyin_accounts.py:230) calls [`DouyinAccountService.validate_account()`](apps/api/src/services/douyin_account_service.py:383).
- [`validate_account()`](apps/api/src/services/douyin_account_service.py:383) attempts browser-backed validation before detached HTTP validation.
- Browser validation uses [`DouyinAccountService._ensure_persistent_profile_context()`](apps/api/src/services/douyin_account_service.py:1224) to reopen/reuse the saved persistent profile before calling [`DouyinBrowserContextRegistry.validate_account_context()`](apps/api/src/services/douyin_browser_context_registry.py:509).
- [`DouyinBrowserContextRegistry.validate_account_context()`](apps/api/src/services/douyin_browser_context_registry.py:509) probes the active context with [`_prevalidate_record_context()`](apps/api/src/services/douyin_browser_context_registry.py:808).
- The weak point was result mapping: `uncertain` browser results with authenticated cookies were returned as available, but [`DouyinAccountService._validate_with_live_browser_context()`](apps/api/src/services/douyin_account_service.py:1114) previously returned `None` for non-`passed`/`blocked`/`login_required`, so validation fell through to detached HTTP.
- For browser-backed accounts, that fallthrough let detached HTTP failure dominate an inconclusive browser probe and could leave the account blocked even though the saved browser profile may be visibly usable.

## Exact Validation-Execution Root Cause

Browser-backed Validate already reopened/reused the saved persistent profile, but its positive-evidence collection was too narrow and its inconclusive mapping was unsafe. If the browser probe returned `uncertain`, the API did not record an explicit browser inconclusive result. Instead, it fell through to detached HTTP validation, where fallback failure could preserve or create blocked-like account state.

## Decisions Made

- Treat browser `passed` as explicit `browser_validation_success`.
- Treat browser `uncertain` as explicit `browser_validation_inconclusive` for browser-backed accounts.
- Do not let detached HTTP fallback overwrite a browser-profile-backed Validate attempt that reached the correct persistent profile but was inconclusive.
- Keep hard negative browser results explicit as `browser_validation_blocked` and `browser_validation_login_required`.
- Preserve runtime/profile unavailable categories for saved-profile accounts.
- Strengthen the browser probe so authenticated, non-challenged browser pages can produce `browser_validation_success`.
- Keep the canonical account model and Intake pipeline unchanged.

## Implementation Notes

- [`DouyinAccountService._validate_with_live_browser_context()`](apps/api/src/services/douyin_account_service.py:1114) now records explicit browser validation categories in account status fields and safe metadata.
- `browser_validation_success` sets the account to `ACTIVE`, clears stale error fields, updates `last_successful_validation_at`, refreshes session/user-agent artifacts from the browser context, and projects `HEALTHY` account health.
- `browser_validation_inconclusive` sets an `INVALID` connection status but projects `UNKNOWN` health with `WARN` level instead of hard-blocking the account.
- Saved-profile runtime unavailable states are recorded as browser validation results instead of falling through to detached HTTP.
- [`DouyinAccountService._browser_health_alignment_summary()`](apps/api/src/services/douyin_account_service.py:943) now exposes inconclusive browser validation as a distinct operator-visible state.
- [`DouyinBrowserContextRegistry._prevalidate_record_context()`](apps/api/src/services/douyin_browser_context_registry.py:808) keeps success tied to authenticated cookies plus non-login/non-challenge browser page signals.
- [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:678) now labels inconclusive automated browser validation distinctly.

## Files Touched

- [`apps/api/src/services/douyin_account_service.py`](apps/api/src/services/douyin_account_service.py)
- [`apps/api/src/services/douyin_browser_context_registry.py`](apps/api/src/services/douyin_browser_context_registry.py)
- [`apps/api/tests/test_douyin_account_service.py`](apps/api/tests/test_douyin_account_service.py)
- [`apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx)
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json)
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json)
- [`docs/douyin-browser-validate-fix-architecture.md`](docs/douyin-browser-validate-fix-architecture.md)
- [`docs/douyin-browser-validate-fix-log.md`](docs/douyin-browser-validate-fix-log.md)
- [`docs/douyin-browser-validate-fix-resume.md`](docs/douyin-browser-validate-fix-resume.md)
- [`docs/douyin-browser-validate-fix-user-guide.md`](docs/douyin-browser-validate-fix-user-guide.md)

## Verification Notes

- Passed: `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_account_service`
- Passed: `npm run typecheck --workspace apps/web`
- The focused tests cover:
  - saved browser profile success clears stale blocked state,
  - inconclusive browser validation does not fall through to detached HTTP or remain hard blocked,
  - validation reopens the exact saved profile identity without allocating a new profile.

## Edge Cases

- A saved profile path alone is not success; browser validation still requires authenticated cookies and non-login/non-challenge browser evidence.
- A visible browser window can still return inconclusive if Douyin navigation/page signals are temporarily unavailable.
- Login-required and blocked browser evidence still produce hard negative account states.
- Detached HTTP fallback remains weaker than fresh browser-backed evidence for saved-profile accounts.
