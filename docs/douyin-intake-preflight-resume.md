# Douyin Intake Preflight Resume

## Current Step

Completed. `/intake` now runs account/browser fetch-readiness preflight before canonical ingest.

## Done

- Audited current account health and browser runtime signals.
- Added `DouyinAccountService.preflight_fetch_readiness()`.
- Added preflight call in `IntakeDiscoveryService.discover()` before adapter construction and `SourceIngestService.ingest_profile()`.
- Added preflight response fields to Intake schema and UI.
- Added preflight failure details to Intake API errors.
- Added tests for preflight stopping before live ingest.
- Verified API tests, API compile, and web typecheck.

## In Progress

- None.

## Next Exact Task

Live operator verification:

1. Select a connected Douyin account in `/intake`.
2. Run discovery with a saved browser profile closed.
3. Confirm preflight auto reopens the same profile or reports a clear fallback/failure.

## Key Files To Continue

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/components/intake/IntakePage.tsx`

## Guardrails

- No duplicate discovery pipeline.
- Preflight must not persist source/video/candidate records.
- Auto reopen must target the same persistent browser profile.
- No raw cookies or local private paths in UI/logs.
