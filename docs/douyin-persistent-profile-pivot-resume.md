# Douyin Persistent Profile Pivot Resume

## Current Step

Completed the persistent browser profile pivot for Douyin local-dev accounts.

## Done

- Audited browser connect, live context registry, account validation, and intake fetch integration.
- Confirmed current live context support is runtime-only and does not survive API restart.
- Added persistent browser profile settings and `.env.example` entries.
- Updated `DouyinBrowserContextRegistry` to launch/reopen Playwright persistent profiles.
- Stored browser profile metadata on canonical `DouyinAccountConnection.metadata_json`.
- Validation/fetch now try to reopen the persistent profile before falling back to detached session behavior.
- `/accounts/douyin` and `/intake` now label saved reusable browser profiles.
- Fixed `scripts/dev-stop.ps1` to stop child Node/worker process trees, preventing stale Next.js listeners on port 3000.
- Verified backend tests, API import smoke, web typecheck, and web build.
- Restarted the local stack and verified frontend/API routes.

## In Progress

- None.

## Next Exact Task

Run one real Douyin browser connect, close/reopen API/browser, then validate/fetch from `/accounts/douyin` and `/intake` to confirm the same local profile remains authenticated.

## Key Files To Continue

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/core/settings.py`
- `apps/api/.env.example`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
