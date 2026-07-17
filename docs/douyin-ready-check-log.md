# Douyin Ready Check Log

## Status

Ready Check API/UI scope is implemented; documentation handoff updated.

## Findings

- Canonical readiness inputs already exist in API:
  - `DouyinAccountService.health_summary()`
  - `DouyinAccountService.preflight_fetch_readiness()`
  - `DouyinBrowserContextRegistry.watchdog_for_account()`
  - `IntakeDiscoveryService._resolve_live_fetch_account_selection()`
- `/intake` UI already shows partial readiness only after a real discovery run:
  - preflight result
  - fetch readiness category
  - selected fetch path
  - browser reopen result
  - watchdog result
- Operators still have to infer readiness before submitting the real intake form.

## Reusable Signal Inventory

- Account health status and `can_use_for_live_fetch`
- Browser profile metadata existence on `DouyinAccountConnection.metadata_json`
- Watchdog runtime status and reconciliation result
- Preflight cache reuse
- Browser reopen requirement/result
- Browser-primary vs HTTP fallback fetch-path selection
- Intake account selection and fallback selection reason

## Chosen Aggregation Policy

- Ready Check will aggregate existing canonical signals.
- It will not run ingest/discovery or create a second preflight system.
- It will return one operator-facing category:
  - `READY`
  - `READY_AFTER_REOPEN`
  - `FALLBACK_READY`
  - `NOT_READY`
- It will expose the intended fetch path, selected/resolved account, browser profile state, and a recommended next action.

## Files Touched

- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/intake/IntakePage.tsx`
- `docs/douyin-ready-check-user-guide.md`

## Verification Notes

- Ready Check aggregation is already wired through [`IntakeDiscoveryService.ready_check()`](apps/api/src/services/intake_discovery_service.py:167) and exposed by [`ready_check_intake()`](apps/api/src/api/routes/intake.py:63).
- Web client request/response wiring is already present in [`runIntakeReadyCheck()`](apps/web/src/lib/api.ts:114) and [`IntakeReadyCheckResponse`](apps/web/src/types/intake.ts:42).
- `/intake` already renders operator actions and summary output around [`executeReadyCheck()`](apps/web/src/components/intake/IntakePage.tsx:288) and [`ReadyCheckSummaryCard()`](apps/web/src/components/intake/IntakePage.tsx:946).
- API test execution could not be completed in this environment because `pytest` is not installed for the available Python interpreter.
