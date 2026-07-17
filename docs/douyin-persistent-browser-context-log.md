# Douyin Persistent Browser Context Log

## Step: Persistent Local Browser Context

Time started: 2026-04-23

## Findings

- Browser-assisted connect currently launches Playwright from `PlaywrightDouyinBrowserSessionCapture.capture()`.
- The current capture path detects login, stabilizes auth, prevalidates in the browser context, captures cookies, then closes `context` and `browser` in `finally`.
- `DouyinAccountConnection` is the canonical persisted source account model.
- Validation currently runs through `DouyinAccountService.validate_account()` using a cookie-backed `DouyinLiveFetchClient`.
- Live fetch/intake currently resolves a `DouyinAccountConnection`, builds a normal account-backed Douyin adapter, then continues through canonical ingest/discovery.
- There is no persistent runtime registry or reusable browser context id today.
- Existing reset/delete actions intentionally affect browser-connect session state/account state separately and must not become a second browser pipeline.

## Current Lifecycle Inventory

1. `/accounts/douyin` starts browser connect through `POST /douyin-accounts/browser-connect/start`.
2. API creates a `DouyinBrowserConnectSession`.
3. Background capture launches a browser and page.
4. Operator logs in/QR scans in the real browser.
5. Capture returns cookie artifacts and user agent.
6. API creates a canonical `DouyinAccountConnection`.
7. Validation runs through the account service.
8. Browser context is currently closed after capture.

## Chosen Persistent Context Strategy

- Add an in-memory local runtime registry for Playwright contexts.
- Keep the browser context alive only when local persistent context config is enabled.
- Bind runtime context availability to `DouyinAccountConnection.id` after successful account creation.
- Use the live context to refresh session cookies and validate when available.
- Use normal cookie-backed validation/fetch as fallback.
- Keep `DouyinAccountConnection` and intake ingest as the canonical persistence and fetch pipeline.

## Files Touched

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/core/settings.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/.env.example`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-persistent-browser-context-log.md`
- `docs/douyin-persistent-browser-context-resume.md`
- `docs/douyin-persistent-browser-context-architecture.md`
- `docs/douyin-persistent-browser-context-user-guide.md`

## Verification Notes

- `PYTHONPATH=apps/api python -m unittest apps/api/tests/test_douyin_account_service.py apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_intake_discovery_service.py` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web run build` passed.
- `DATABASE_URL=sqlite:///:memory: PYTHONPATH=apps/api python -c "from src.main import app; ..."` passed.
- Local HTTP smoke was not run because the dev servers were not active at verification time.

## Status

Completed for V1 implementation. Manual browser login verification is still required because default automated tests do not use live Douyin or Playwright browser windows.
