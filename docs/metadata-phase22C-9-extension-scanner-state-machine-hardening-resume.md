# Phase 22C-9 - Extension Scanner State Machine Hardening Resume

## Implemented
- Primary action selector now uses 22C-9 versioning and emits a richer decision trace with snake_case fields.
- Scan Profile remains before calibration in selector priority.
- Runtime diagnostics include `state_machine_version`.
- Zero-round incomplete scan normalization now exposes `scan_error_normalizer_applied`.
- State normalization now runs `validateScannerState` and quarantines legacy storage under `storage_state_audit`.
- Expected-count scan diagnostics include `scan_run_id` and `expected_count_scan_run_id`.
- Advanced diagnostics expose group summaries for profile scan, calibration, collection, backend session, reset, storage audit, and primary action decision trace.

## Files Changed
- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
- `docs/metadata-phase22C-9-extension-scanner-state-machine-hardening-log.md`
- `docs/metadata-phase22C-9-extension-scanner-state-machine-hardening-resume.md`

## Validation Status
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed after the initial implementation slice.
- Full test and build validation still need to run after final test assertion updates.

## Remaining Work
- Finish running full tests and build.
- Fix any assertions that still reference previous phase strings.
- Confirm docs and final report use the 14 required Phase 22C-9 sections.
