# Douyin Manual Import Fetch Fix Resume

Current step: implementing manual-import intake fetch fix.

## Done

- Audited manual import persistence, account resolution, intake discovery, and source ingest wiring.
- Reproduced the backend 500.
- Identified exact root cause: `adapters` was passed to `ingest_profile` instead of `SourceIngestService`.

## In Progress

- Normalize manual session cookie input into a runtime-safe Cookie header.
- Add diagnostic error mapping for manual import fetch failures.
- Add focused tests.

## Next Exact Task

Patch:

- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/douyin_account_service.py`
- relevant tests under `apps/api/tests`

Then run focused backend tests and an API route verification.

## Key Files To Continue

- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/api/routes/intake.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/intake/IntakePage.tsx`
