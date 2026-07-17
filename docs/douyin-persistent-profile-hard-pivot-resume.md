# Douyin Persistent Profile Hard Pivot Resume

## Current Step

Hard pivot browser connect from transient session identity to account persistent profile identity.

## Done

- Audited API, UI, schema, runtime registry, and account service paths.
- Identified the remaining session-centric profile generation in `DouyinBrowserContextRegistry`.
- Identified missing `account_connection_id` in `DouyinBrowserConnectStartRequest`.
- Added `account_connection_id` to API and web start request schemas.
- Updated browser connect service to target an existing `DouyinAccountConnection` and update that account rather than creating a duplicate account on reconnect.
- Updated browser context registry so existing account reconnect reuses the same live context or the same persistent profile directory.
- Added `/accounts/douyin` account-row `Open profile` action.
- Added focused tests for account-targeted connect and stable account profile ids.
- Added user guide for the new persistent-profile workflow.

## In Progress

- None.

## Next Exact Task

Use `/accounts/douyin` to connect or open a saved Douyin profile, then select the connected account from `/intake` for live fetch.

If further hardening is needed, the next task should be profile-lock handling for cases where Chrome has the same `userDataDir` open outside the API runtime.

## Key Files To Continue

- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
