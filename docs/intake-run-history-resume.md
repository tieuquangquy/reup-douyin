# intake-run-history-resume.md

## Current Step
- Step 8/10: verification + docs finalization for intake run history, compare, and troubleshooting.

## Done
- Re-checked repository rules in `AGENTS.md`.
- Reused canonical intake models and discovery flow (`CrawlSession`, `SourceProfile`, `IntakeDiscoveryService`) with no new run-tracking table.
- Implemented run history backend service in `apps/api/src/services/intake_run_history_service.py`.
- Extended intake schemas/routes for:
  - `GET /intake/runs`
  - `GET /intake/runs/{crawl_session_id}`
  - `GET /intake/runs/compare`
- Persisted intake candidate/account-selection metadata into crawl-session metadata in `apps/api/src/services/intake_discovery_service.py`.
- Extended web API/types and added `/intake` side panels:
  - Run history panel
  - Troubleshooting panel
  - Compare runs panel
- Added i18n keys in both `apps/web/src/lib/i18n/en.json` and `apps/web/src/lib/i18n/vi.json`.
- Added service tests in `apps/api/tests/test_intake_run_history_service.py`.
- Verified web typecheck passed via workspace command.

## In Progress
- Running API-side unit verification command compatible with current environment.

## Next Exact Task
- Finalize `docs/intake-run-history-user-guide.md` and then close out final summary.

## Key Files To Continue
- `docs/intake-run-history-log.md`
- `docs/intake-run-history-resume.md`
- `docs/intake-run-history-architecture.md`
- `apps/api/src/models/ingestion.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/api/routes/intake.py`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/intake.ts`
