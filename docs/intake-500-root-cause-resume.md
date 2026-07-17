# Intake 500 Root Cause Resume

Current step: completed.

## Done

- Reproduced the failing `/intake` request locally.
- Captured the exact backend root cause.
- Identified the failing stage: `IntakeDiscoveryService` -> `SourceIngestService` handoff.

## In Progress

- None.

## Next Exact Task

If work continues, the next useful step is adding an intake-side troubleshooting panel that links `diagnostics_id` with run history and fetch observability when a live fetch fails after crawl session creation.

## Key Files To Continue

- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/intake/IntakePage.tsx`
