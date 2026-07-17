# Douyin Post-Login Blocked Fix Resume

## Current Step

Completed the post-login blocked classification fix for browser-assisted Douyin connect.

## Done

- Audited the blocked assignment path.
- Identified `post_login_blocked` raises in:
  - `apps/api/src/services/douyin_browser_context_registry.py`
  - `apps/api/src/services/douyin_browser_connect_service.py`
- Identified direct live-browser blocked mapping in:
  - `apps/api/src/services/douyin_account_service.py`
- Removed hard terminal `post_login_blocked` raise from the first post-login blocked-like prevalidation.
- Changed connect-time live-browser blocked results to retryable account/session state.
- Added repeated-evidence guard before connect retry can mark an account `BLOCKED`.
- Updated `/accounts/douyin` wording for post-login blocked retry guidance.
- Added focused backend tests.
- Verified backend tests, web typecheck, web build, and API import smoke.

## In Progress

- None.

## Next Exact Task

Run a real browser-assisted connect attempt in `/accounts/douyin` and use `Retry validation` if Douyin returns another immediate post-login challenge page.

## Key Files To Continue

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/api/tests/test_douyin_account_service.py`
