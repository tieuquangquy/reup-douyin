# Douyin Accounts Module Log

## Step
Implement `/accounts/douyin` module and account-backed live fetch workflow.

## Findings
- `/intake` uses `POST /intake/discover`.
- `IntakeDiscoveryService` decides existing-data vs live-fetch and calls `SourceIngestService.ingest_profile` for live ingest.
- `SourceIngestService` persists the canonical `CrawlSession`, `SourceProfile`, `SourceVideo`, and `VideoMetricSnapshot` records.
- `CandidateEvaluationService` remains the canonical candidate discovery path.
- `DouyinLiveFetchClient` already accepts `user_agent`, `session_cookie`, `proxy_url`, timeout, and max videos.
- Existing `PlatformAccount` is for publish targets and routing; it should not be reused for Douyin source fetch sessions.
- Current worker path can call `SourceIngestService`, but `/intake` is still synchronous. This step keeps sync intake to avoid a large job migration.

## Existing Architecture Inventory
- Live fetch transport: `apps/api/src/adapters/douyin_live_fetch.py`
- Adapter wiring: `apps/api/src/adapters/registry.py`
- Canonical ingest persistence: `apps/api/src/services/source_ingest_service.py`
- Intake orchestration: `apps/api/src/services/intake_discovery_service.py`
- Candidate discovery: `apps/api/src/services/candidate_service.py`
- Publish accounts: `apps/api/src/models/publish.py` and `PlatformAccountService`, intentionally separate.
- Operator navigation: `apps/web/src/lib/navigationConfig.ts`
- Intake UI: `apps/web/src/components/intake/IntakePage.tsx`

## Decisions Made
- Add a separate `DouyinAccountConnection` entity for source fetch account/session state.
- Store imported session cookie in a V1 local blob field and never echo it through API responses.
- Add API endpoints under `/douyin-accounts`.
- Add frontend route `/accounts/douyin`.
- Add an Operator Studio navigation entry under Intake because this is a source acquisition workflow.
- Add `douyin_account_connection_id` to `/intake/discover`.
- Account-backed live fetch reuses `DouyinLiveFetchClient`, `DouyinProfileAdapter`, and `SourceIngestService`.
- Keep `/intake` synchronous for V1; worker account-backed crawl can use the same service later.

## Security Choices
- No password import.
- Browser-assisted / QR-style login was not part of the original account module step; it is implemented in the follow-up browser-connect step.
- API responses never include raw session cookie.
- Validation and fetch services should not log cookie/session data.
- V1 local storage is not production-grade secret storage; docs must state this clearly.

## Files Touched
- `apps/api/src/enums/__init__.py`
- `apps/api/src/models/source_accounts.py`
- `apps/api/src/models/__init__.py`
- `apps/api/alembic/versions/0016_douyin_account_connections.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/main.py`
- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/intakeState.ts`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/app/accounts/douyin/page.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/intake.test.ts`
- `apps/web/src/test/route-nav.test.ts`
- `docs/douyin-accounts-module-log.md`
- `docs/douyin-accounts-module-resume.md`
- `docs/douyin-accounts-architecture.md`
- `docs/douyin-account-session-import.md`

## Implementation Notes
- Added `DouyinAccountConnectionStatus` enum.
- Added `DouyinAccountConnection` as source-account domain model, separate from publish-side `PlatformAccount`.
- Added Alembic migration `0016_douyin_account_connections`.
- Added safe response schemas that expose only `session_cookie_present` and masked preview.
- Added `/douyin-accounts` API:
  - `GET /douyin-accounts`
  - `POST /douyin-accounts`
  - `GET /douyin-accounts/{id}`
  - `PATCH /douyin-accounts/{id}`
  - `POST /douyin-accounts/{id}/validate`
  - `POST /douyin-accounts/{id}/disable`
  - `DELETE /douyin-accounts/{id}`
- Added `DouyinAccountService` for create/update/list/default/validation/runtime client construction.
- Validation URLs are restricted to Douyin hosts to avoid arbitrary backend fetches.
- Added `DouyinLiveFetchClient.fetch_html` so validation can use the same transport.
- Added `douyin_account_connection_id` to `/intake/discover`.
- Live intake paths now resolve selected/default account and inject account-backed `DouyinProfileAdapter` into `SourceIngestService`.
- Existing usable data still runs without account.
- Added Operator route `/accounts/douyin` and navigation entry under Intake.
- `/intake` now lists Douyin account connections and sends selected account id.

## Verification Notes
- Ran migration:
  - `alembic upgrade head`
- API unit tests passed:
  - `python -m unittest apps/api/tests/test_douyin_account_service.py apps/api/tests/test_intake_discovery_service.py apps/api/tests/test_douyin_adapter.py`
- API app import/route smoke passed with `DATABASE_URL=sqlite:///:memory:`:
  - `/douyin-accounts` route present
  - `/intake/discover` route present
- API compile check passed:
  - `python -m compileall -q apps/api/src`
- Web checks passed:
  - `npm run typecheck`
  - `npm run test`
  - i18n JSON parse check
- Runtime smoke passed:
  - `GET http://127.0.0.1:8000/douyin-accounts`
  - create/validate/delete temporary Douyin account without raw cookie echo
  - `GET http://localhost:3000/accounts/douyin`
  - `GET http://localhost:3000/intake`
  - existing-data `/intake/discover` still returns `existing_data`, 2 videos, and 2 matched candidates without account

## V1 Limitations
- Session storage is a local V1 blob, not production-grade secret vaulting.
- Validation checks session presence plus network/login/blocking markers. It is useful for local operator feedback, but not a complete proof of account health.
- Browser-assisted / QR-style login is now handled by `docs/douyin-browser-connect-architecture.md`.
- Intake remains synchronous; worker account-backed crawl can be added later using the same account service and source ingest path.

## Status
Completed.
