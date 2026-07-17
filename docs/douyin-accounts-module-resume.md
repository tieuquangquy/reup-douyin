# Douyin Accounts Module Resume

## Current Step
Completed: implement `/accounts/douyin` and account-backed live fetch integration for `/intake`.

## Done
- Audited current intake, live fetch, source ingest, candidate discovery, publish account, and navigation architecture.
- Chosen integration path:
  - `/accounts/douyin` manages Douyin source account connections.
  - `/intake` selects a connection when live fetch is needed.
  - Live fetch uses account session context through existing adapter/client.
  - Persistence and candidate discovery stay on existing canonical services.
- Added backend model, migration, schemas, service, and API routes for Douyin account connections.
- Added `/accounts/douyin` UI.
- Added Douyin account selector to `/intake`.
- Added account-backed live fetch injection into `IntakeDiscoveryService` without changing canonical persistence/candidate flow.
- Ran Alembic migration and focused API/web verification.

## In Progress
- None.

## Next Exact Task
Use `/accounts/douyin` browser-assisted connect with a real Douyin login, validate it, then run `/intake` with Force live refresh and the selected account. If Douyin blocks the request, configure proxy/session rotation and inspect adapter error details.

## Key Files To Continue
- `apps/api/src/models/source_accounts.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `docs/douyin-accounts-architecture.md`
- `docs/douyin-account-session-import.md`
- `docs/douyin-browser-connect-architecture.md`
