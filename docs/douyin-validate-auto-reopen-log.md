# douyin-validate-auto-reopen-log.md

## Status

- Audit complete.
- Architecture doc created before major code changes.
- Implementation complete.
- Focused backend tests passed.
- Frontend typecheck passed.

## Audit Findings

- The Validate button in [`DouyinAccountsPage`](../apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:293) calls [`validateDouyinAccount()`](../apps/web/src/lib/api.ts:247).
- The API route [`validate_douyin_account()`](../apps/api/src/api/routes/douyin_accounts.py:230) calls [`DouyinAccountService.validate_account()`](../apps/api/src/services/douyin_account_service.py:383).
- Browser-backed validation runs in [`DouyinAccountService._validate_with_live_browser_context()`](../apps/api/src/services/douyin_account_service.py:1114).
- Current validation calls [`DouyinAccountService._ensure_persistent_profile_context()`](../apps/api/src/services/douyin_account_service.py:1236), then [`DouyinBrowserContextRegistry.validate_account_context()`](../apps/api/src/services/douyin_browser_context_registry.py:509).
- [`validate_account_context()`](../apps/api/src/services/douyin_browser_context_registry.py:509) returns `no_live_browser_context` when the registry has no live record for the account.
- [`open_profile_for_account()`](../apps/api/src/services/douyin_browser_context_registry.py:358) can reopen a saved persistent profile and register a runtime entry for the same account.
- The failing path occurred when saved profile metadata existed but the live registry record was missing or was lost after restart.

## Exact Root Cause

Saved profile metadata and live browser runtime state are different. Validate could see a browser-backed account with saved `browser_profile_id` / `browser_profile_path`, but if the in-memory registry had no active record, [`validate_account_context()`](../apps/api/src/services/douyin_browser_context_registry.py:509) returned `no_live_browser_context`. The service then mapped this as `browser_validation_runtime_unavailable` instead of explicitly auto-reopening and retrying the canonical browser probe.

## Decisions Made

- Use the existing canonical reopen helper rather than creating a new profile or alternate validation path.
- Reuse the exact saved profile identity/path for the same account.
- Treat successful auto-reopen as runtime recovery metadata, then continue the normal browser validation probe.
- Return runtime unavailable only after reopen/reattach fails.
- Preserve browser-primary Intake and canonical account model boundaries.
- Expose concise `/accounts/douyin` wording for runtime-missing and runtime-reopened states.

## Implementation Notes

- [`DouyinAccountService._validate_with_live_browser_context()`](../apps/api/src/services/douyin_account_service.py:1114) now detects `no_live_browser_context` for saved-profile accounts, forces the canonical persistent profile reopen helper, and retries browser validation when reopen succeeds.
- [`DouyinAccountService._ensure_persistent_profile_context()`](../apps/api/src/services/douyin_account_service.py:1236) now returns the registry summary and supports a forced validation reopen path.
- Auto-reopen success records `browser_validation_runtime_reopened` metadata, but the final validation status is still the result of the browser probe after reopen.
- Auto-reopen failure records `browser_validation_runtime_unavailable` only after the reopen attempt fails or the runtime still cannot be validated.
- `/accounts/douyin` now distinguishes saved profile auto-reopen from missing live runtime and final validation outcome.

## Files Touched

- [`apps/api/src/services/douyin_account_service.py`](../apps/api/src/services/douyin_account_service.py)
- [`apps/api/tests/test_douyin_account_service.py`](../apps/api/tests/test_douyin_account_service.py)
- [`apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`](../apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx)
- [`apps/web/src/lib/i18n/en.json`](../apps/web/src/lib/i18n/en.json)
- [`apps/web/src/lib/i18n/vi.json`](../apps/web/src/lib/i18n/vi.json)
- [`docs/douyin-validate-auto-reopen-architecture.md`](docs/douyin-validate-auto-reopen-architecture.md)
- [`docs/douyin-validate-auto-reopen-log.md`](docs/douyin-validate-auto-reopen-log.md)
- [`docs/douyin-validate-auto-reopen-resume.md`](docs/douyin-validate-auto-reopen-resume.md)
- [`docs/douyin-validate-auto-reopen-user-guide.md`](docs/douyin-validate-auto-reopen-user-guide.md)

## Verification Notes

- Passed: `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_account_service`
- Passed: `npm run typecheck --workspace apps/web`
- Backend tests cover saved-profile auto-reopen from `no_live_browser_context`, same saved profile identity reuse, runtime-unavailable only after reopen failure, stale blocked/invalid clearing on success, and inconclusive warning behavior.

## Edge Cases

- A saved profile path alone is not final validation success; the reopened browser context must still pass the browser validation probe.
- If the saved profile cannot be opened by Playwright/browser runtime, Validate returns runtime unavailable after the reopen attempt.
- If saved profile metadata is missing, the browser-backed path cannot auto-reopen and the profile-unavailable category remains applicable.
- Login-required and blocked browser evidence remain hard negative states.
