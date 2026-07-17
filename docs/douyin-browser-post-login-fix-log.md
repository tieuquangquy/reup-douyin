# douyin-browser-post-login-fix-log.md

## Step: Post-login stabilization and validation fix

### Time Started
- 2026-04-23

### Findings
- Browser-assisted connect still uses one canonical service: `DouyinBrowserConnectService`.
- Login success is currently detected only by authenticated Douyin cookie names in Playwright context.
- `PlaywrightDouyinBrowserSessionCapture.capture()` currently returns immediately after cookie detection.
- The browser context is closed in `capture()` before `DouyinAccountService.validate_account()` runs.
- Canonical validation currently runs through `DouyinLiveFetchClient` outside browser context.
- `DouyinAccountService.validate_account()` maps HTML markers such as `captcha`, `verify`, `blocked`, and `security check` to `BLOCKED` / `blocked_response`.
- This can create a false blocked account when cookie capture happens too early or when the out-of-browser validation probe is challenged while the browser session would still be usable.
- Current persisted enum has no dedicated `LOGIN_DETECTED`, `STABILIZING_AUTH`, or `VALIDATION_RETRY_READY` values.

### Current Root Causes
- Login detected was treated as ready-to-capture.
- Browser closed before post-login state had time to stabilize.
- Validation happened after browser close.
- A first connect-time `blocked_response` could mark the saved account as blocked even if browser-context post-login state looked usable.

### Decisions Made
- Keep one canonical browser connect pipeline and one `DouyinAccountConnection` persistence path.
- Avoid DB enum migration in this fix; expose richer lifecycle through response `phase`, metadata, and capability flags.
- Add post-login stabilization inside the Playwright browser before returning capture result.
- Add a browser-context prevalidation check before the browser is closed.
- Treat a first connect-time canonical `blocked_response` as retryable when browser-context prevalidation passed.
- Add retry validation for a connect session with a derived account instead of making the operator login again immediately.
- Only leave the account in `BLOCKED` after a real post-login validation failure without browser-context success evidence, or after a retry validation still fails.

### Files Touched
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-browser-post-login-fix-log.md`
- `docs/douyin-browser-post-login-fix-resume.md`
- `docs/douyin-browser-post-login-fix-architecture.md`
- `docs/douyin-browser-post-login-user-guide.md`

### Verification Notes
- Backend unit tests passed:
  - `PYTHONPATH=apps/api python -m unittest apps/api/tests/test_douyin_browser_connect_service.py`
- Python compile sanity passed for changed browser-connect route/schema/service.
- FastAPI route registration includes:
  - `/douyin-accounts/browser-connect/{connect_session_id}/retry-validation`
- Frontend typecheck passed:
  - `npm --workspace @reup-douyin/web run typecheck`
- Frontend build passed:
  - `npm --workspace @reup-douyin/web run build`
- Live local sanity passed:
  - `GET /accounts/douyin` returned `200 OK`
  - `GET /docs` returned `200 OK`
  - `GET /douyin-accounts/browser-connect/active` returned `{"session": null}` when idle

### Status
- Completed.
