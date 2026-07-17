# intake-run-history-log.md

## Step
- Audit-first documentation bootstrap for intake run history, compare runs, and failed fetch troubleshooting panel.

## Time Started
- 2026-04-22 (UTC)

## Findings
- Canonical intake run source-of-truth already exists in `apps/api/src/models/ingestion.py` via `CrawlSession` linked to `SourceProfile` and `SourceVideo`.
- `CrawlSession` already stores run lifecycle and operator-troubleshooting primitives (`status`, `started_at`, `finished_at`, discovered/created/updated counts, `error_code`, `error_message`, `raw_summary_json`, `result_summary_json`, `metadata_json`).
- `SourceIngestService.ingest_profile()` in `apps/api/src/services/source_ingest_service.py` already computes and persists summary metadata and marks failed sessions with structured error code/message.
- `IntakeDiscoveryService.discover()` in `apps/api/src/services/intake_discovery_service.py` already computes intake-facing context (fetch mode, account-selection metadata, warning text, candidate summary), but some context remains response-level unless persisted to crawl-session metadata.

## Existing Architecture Inventory
- API route layer currently exposes intake discover/productivity endpoints in `apps/api/src/api/routes/intake.py`.
- Intake schema contracts are in `apps/api/src/schemas/intake.py` and currently focus on discover + productivity payloads.
- Web intake page state and side panels live in `apps/web/src/components/intake/IntakePage.tsx` with API helpers in `apps/web/src/lib/api.ts` and types in `apps/web/src/types/intake.ts`.
- Existing docs with strong alignment constraints:
  - `docs/douyin-live-fetch-architecture.md`
  - `docs/douyin-intake-account-selection-architecture.md`
  - `docs/douyin-account-health-architecture.md`

## Decisions Made
- Reuse `CrawlSession` as the single canonical run-history entity; do not introduce duplicate run-tracking tables.
- Keep run-history scope operator-focused and minimal (read-only aggregation + quick form-fill actions), not analytics dashboard scope.
- Extend intake API contracts and web intake side panels incrementally while preserving current discover flow behavior.
- Maintain deterministic troubleshooting classification from persisted session signals (`status`, `error_code`, result counts, account-selection metadata where available).

## Files Touched
- `docs/intake-run-history-log.md` (created)
- `docs/intake-run-history-resume.md` (created, updated)
- `docs/intake-run-history-architecture.md` (created)
- `apps/api/src/services/intake_run_history_service.py` (created)
- `apps/api/src/schemas/intake.py` (updated)
- `apps/api/src/api/routes/intake.py` (updated)
- `apps/api/src/services/intake_discovery_service.py` (updated)
- `apps/web/src/types/intake.ts` (updated)
- `apps/web/src/lib/api.ts` (updated)
- `apps/web/src/components/intake/IntakePage.tsx` (updated)
- `apps/web/src/lib/i18n/en.json` (updated)
- `apps/web/src/lib/i18n/vi.json` (updated)
- `apps/api/tests/test_intake_run_history_service.py` (created)

## Verification Notes
- Web typecheck passed:
  - `npm run typecheck --workspace apps/web`
- API test command attempted with pytest failed because `pytest` is not installed in current environment.
- Fallback unittest command is being used for service-level verification.

## Status
- Implementation complete; verification/docs finalization in progress.
