# Douyin Browser Connect Log

## Step
Implement browser-assisted / QR-style Douyin account connect flow.

## Findings
- `/accounts/douyin` already exists and manages canonical `DouyinAccountConnection` records.
- Manual cookie import currently uses `DouyinAccountService.create_account`.
- Validation currently uses `DouyinAccountService.validate_account` and the same Douyin live fetch transport.
- `/intake` already accepts `douyin_account_connection_id` and uses active/default Douyin account connections for live fetch.
- No browser-assisted connect lifecycle exists yet.
- No QR protocol abstraction exists, and reverse-engineering a native QR API is out of scope.

## Current Manual Flow Inventory
- UI route: `/accounts/douyin`
- API routes:
  - `GET /douyin-accounts`
  - `POST /douyin-accounts`
  - `POST /douyin-accounts/{id}/validate`
- Canonical model: `DouyinAccountConnection`
- Session storage: V1 local blob, masked in API responses.

## Chosen Browser-Assisted Architecture
- Add a short-lived `DouyinBrowserConnectSession` lifecycle record.
- Add API endpoints under `/douyin-accounts/browser-connect/...`.
- Browser-assisted worker logic captures cookies from a real Douyin browser login session.
- Captured session artifacts are passed into the existing `DouyinAccountService.create_account` path.
- Validation reuses `DouyinAccountService.validate_account`.
- The resulting account is a normal `DouyinAccountConnection` and is immediately visible to `/intake`.

## Decisions Made
- Browser-assisted connect becomes the primary UX.
- Manual session import remains as a fallback.
- QR-style support means opening the real Douyin login page; if Douyin shows a QR code, the operator scans it there.
- No password login.
- No raw cookie returned to the UI after persistence.
- No duplicate source account model or intake pipeline.

## Files Touched
- `apps/api/pyproject.toml`
- `apps/api/src/enums/__init__.py`
- `apps/api/src/models/source_accounts.py`
- `apps/api/src/models/__init__.py`
- `apps/api/alembic/versions/0017_douyin_browser_connect_sessions.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-browser-connect-log.md`
- `docs/douyin-browser-connect-resume.md`
- `docs/douyin-browser-connect-architecture.md`
- `docs/douyin-browser-connect-user-guide.md`
- `docs/douyin-accounts-architecture.md`
- `docs/douyin-account-session-import.md`

## Verification Notes
- API unit tests passed:
  - `python -m unittest apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_douyin_account_service.py apps/api/tests/test_intake_discovery_service.py apps/api/tests/test_douyin_adapter.py`
- API compile check passed:
  - `python -m compileall -q apps/api/src`
- Web checks passed:
  - `npm run typecheck`
  - `npm run test`
- Migration passed:
  - `alembic upgrade head`
- Route registry verified that `/douyin-accounts/browser-connect/...` routes are registered before `/douyin-accounts/{account_id}`.
- Runtime smoke:
  - `GET /accounts/douyin` returned 200.
  - `GET /intake` returned 200.
  - `GET /douyin-accounts` returned safe account list JSON.
  - `GET /douyin-accounts/browser-connect/{missing-id}` returned 404 through the browser-connect route.
- A real browser login was not launched during verification to avoid opening Douyin/Chrome unexpectedly on the operator machine.

## Status
Completed.
