# douyin-browser-active-session-fix-resume.md

## Current Step
Fix stale/active browser connect session handling for `/accounts/douyin`.

## Done
- Audited backend service, routes, schema, model, frontend API client, and `/accounts/douyin` UI.
- Identified `active_session_exists` guard in `DouyinBrowserConnectService.start_connect()`.
- Confirmed existing timestamps are enough for V1 stale detection without schema migration.
- Implemented backend stale detection and stale finalization.
- Added active-session discovery endpoint.
- Added force restart endpoint.
- Updated response contract with `age_seconds`, `is_stale`, `stale_reason`, `can_resume`, and `can_force_restart`.
- Updated `/accounts/douyin` to discover active sessions, resume, cancel, and force restart.
- Added tests for stale session policy and timeout outcome mapping.
- Verified backend tests, Python compile sanity, frontend typecheck, and frontend build.

## In Progress
- Nothing for this fix.

## Next Exact Task
Manually exercise `/accounts/douyin` with a real browser connect session:
1. Open `/accounts/douyin`.
2. Start browser connect.
3. Refresh the page and confirm it reattaches to the active session.
4. Cancel and confirm the UI clears the blocking state.
5. Start again and confirm no `active_session_exists` dead end appears.

## Key Files To Continue
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/douyin-accounts.ts`
