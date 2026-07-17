# douyin-browser-connect-retry-resume.md

## Current Step
- Documentation finalized for implemented contract and UX changes; remaining work is manual browser-assisted scenario execution on local runtime.

## Done
- Audited existing backend lifecycle in [`DouyinBrowserConnectService`](apps/api/src/services/douyin_browser_connect_service.py:116).
- Audited existing session states in [`DouyinBrowserConnectSessionStatus`](apps/api/src/enums/__init__.py:66).
- Audited current route/API contracts in [`douyin_accounts` routes](apps/api/src/api/routes/douyin_accounts.py:104).
- Audited frontend start/poll/cancel behavior in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:127).
- Extended browser connect response contract in [`DouyinBrowserConnectSessionResponse`](apps/api/src/schemas/douyin_accounts.py:115) with outcome/phase/deadline/remaining/timed_out/can_retry/can_cancel.
- Added active-running-session guard and response mapping helpers in [`DouyinBrowserConnectService.start_connect()`](apps/api/src/services/douyin_browser_connect_service.py:128) and [`DouyinBrowserConnectService.to_response()`](apps/api/src/services/douyin_browser_connect_service.py:192).
- Updated UI polling + stale response guard + retry/cancel/timed_out messaging in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:150).
- Updated i18n strings in [`en.json`](apps/web/src/lib/i18n/en.json) and [`vi.json`](apps/web/src/lib/i18n/vi.json).
- Added service tests for timeout/action parsing in [`test_douyin_browser_connect_service.py`](apps/api/tests/test_douyin_browser_connect_service.py:12).
- Verification executed:
  - Web typecheck passed via [`npm run -w apps/web typecheck`](apps/web/package.json:6).
  - API unit tests passed via [`python -m unittest tests.test_douyin_browser_connect_service`](apps/api/tests/test_douyin_browser_connect_service.py:12).

## In Progress
- Scenario-level manual verification (start/poll/timeout/retry/cancel/success/failure/manual fallback) in a live local browser-assisted run.

## Next Exact Task
- Execute manual browser-assisted flow and record per-scenario evidence in [`docs/douyin-browser-connect-retry-log.md`](docs/douyin-browser-connect-retry-log.md) for:
  - start enters running
  - polling reflects backend truth
  - timeout guidance and retry behavior
  - cancel behavior
  - success path with derived account
  - failure path guidance
  - manual fallback visibility

## Key Files To Continue
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `docs/douyin-browser-connect-retry-architecture.md`
- `docs/douyin-browser-connect-user-flow.md`
