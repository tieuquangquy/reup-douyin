# Douyin Persistent Browser Context Resume

## Current Step

Implement persistent local browser context reuse for Douyin connect/validate/fetch.

## Done

- Audited browser-assisted connect lifecycle.
- Confirmed browser context currently closes after capture.
- Confirmed validation/live fetch use canonical `DouyinAccountConnection` and cookie-backed fetch.
- Chosen runtime-only registry strategy with fallback to current cookie path.
- Added runtime-only persistent browser context registry.
- Browser connect can keep and bind a Playwright context to the canonical account after login capture.
- Account validation can prefer the live context and fallback to cookie validation.
- Live fetch preparation can refresh cookie artifacts from the live context before using the existing fetch client.
- `/accounts/douyin` displays browser context status.
- `/intake` shows a local live-browser-context hint when available.

## In Progress

Manual live Douyin verification.

## Next Exact Task

Run the browser-assisted connect flow against real Douyin locally, keep the browser open, then validate and force-refresh intake using the same account to confirm repeated QR login is reduced.

## Key Files To Continue

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/core/settings.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-persistent-browser-context-user-guide.md`
