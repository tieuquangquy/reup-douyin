# douyin-browser-reset-resume.md

## Current Step
Implement `Reset browser connect state` recovery action for `/accounts/douyin`.

## Done
- Audited canonical session model and account persistence boundary.
- Confirmed reset should only terminalize `DouyinBrowserConnectSession` rows in active-looking states.
- Confirmed reset must not delete or mutate saved `DouyinAccountConnection` records.
- Created log/resume/architecture docs before code changes.
- Added backend reset schema, service method, and route.
- Added web API client, typed response, UI action, confirmation copy, and recovery message.
- Added reset user guide and troubleshooting docs.
- Verified backend tests, Python compile sanity, route registration, frontend typecheck, frontend build, live reset endpoint, and `/accounts/douyin` route.

## In Progress
- Nothing for this reset step.

## Next Exact Task
Manually verify the live stuck-session case by starting browser connect, closing the browser, then using `Reset browser connect state` from `/accounts/douyin`.

## Key Files To Continue
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
