# Extension Cleanup Changelog

Date: 2026-06-02
Scope: `apps/extension-douyin-capture`

This note records the cleanup pass that removed legacy UI wiring, dead compatibility paths, stale storage keys, and outdated version markers while keeping the current scanner/collection flow green under `typecheck`, `extension:test`, and `extension:build`.

## Files changed

### `apps/extension-douyin-capture/src/popup.ts`
- Removed dead popup selector wiring for controls no longer present in `public/popup.html`.
- Removed old blocked-legacy action path usage and related residual button state logic.
- Removed the legacy `WholeProfileStagedHarvestV2` popup cluster, including staged state types, storage helpers, render helpers, and popup entrypoints.
- Removed residual loading/hidden/disabled handling for old controls such as smart capture, capture-only, staged harvest, old flush/progress buttons, and legacy harvest mode inputs.
- Preserved current scanner-shell UI, canonical primary action routing, advanced maintenance actions, calibration actions, capture-inbox navigation, and canonical collect/reset flows.

### `apps/extension-douyin-capture/src/legacy/legacyGuard.ts`
- Deleted the file completely.
- Reason: popup no longer routed through `blockedLegacyPopupAction`, so the guard became dead code.

### `apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts`
- Removed stale legacy keys no longer needed for quarantine/cleanup:
  - `douyinCdpStatus`
  - `douyinCdpDebugState`
  - `douyinWholeProfileStagedHarvestV2`
- Kept keys that still matter for legacy cleanup compatibility, including `douyinSafeHarvestRun` and pending flush/runtime bridge keys.

### `apps/extension-douyin-capture/src/storageKeys.ts`
- Removed storage-key aliases for unused legacy CDP state:
  - `legacyCdpStatus`
  - `legacyCdpDebugState`
- Kept harvest/reset/calibration key groups that still participate in reset flows and compatibility cleanup.

### `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- Removed the legacy `runHarvest(...)` execution path.
- Removed `legacyDouyinHarvestEnabled()`.
- Kept forbidden-runner quarantine logic and migration/scrub behavior for legacy runner references stored in state.
- Normalized controller diagnostic/version constants from old `22C-9*` values to current `22C-12F` family where appropriate:
  - scanner runtime
  - state machine
  - scan controller
  - post-probe handoff version
  - post-probe handoff patch
  - reset controller
  - primary action selector
- Updated the remaining `runPostPingProfileDomProbe22C9I` trace-version usage and related diagnostics so old `22C-9Z-10` string markers no longer remain in active controller diagnostics.

### `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- Updated leftover reset-controller cosmetic version string from old `22C-9` marker to `22C-12F` naming for consistency with the current scanner runtime family.

### `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- Removed legacy tests that kept the deleted `runHarvest(...)` path alive.
- Kept tests for current canonical flows such as `runStartCollectingWorkflow(...)`, safe batch collection, forbidden-runner denylist behavior, and legacy-runner state migration/quarantine.
- Updated version-string expectations to match the normalized `22C-12F` runtime family.

### `apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts`
- Removed assertions that depended on the deleted legacy guard path and deleted popup controls.
- Updated cleanup expectations after staged-harvest and legacy-key removal.
- Kept assertions that verify:
  - popup no longer renders legacy button text
  - popup keeps canonical scanner-shell controls
  - Clear Legacy State preserves calibration
  - primary action routing stays on canonical scan/start-collecting flow

## What was intentionally kept

### Forbidden legacy runner references
- `runRealModalExtractionHarvest` still exists as a forbidden/quarantined reference in controller/test coverage.
- Reason: it now serves as a denylist/migration contract, not as a live popup/runtime route.

### `harvestRuntimeV2` compatibility layer
- Not removed.
- Reason: it is still used by `contentScript.ts`, reset flows, readiness/viewmodel tests, and runtime pause/progress compatibility behavior.

### Legacy cleanup APIs
- `getLegacyStateSummary(...)` and `clearLegacyState(...)` were kept.
- Reason: popup advanced maintenance and tests still use them, and they remain part of controlled cleanup/recovery behavior.

## Validation performed

The cleanup pass repeatedly re-ran:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm run extension:test`
- `npm run extension:build`

Final status after the cleanup series: all three passed.

## Post-cleanup recovery note

- A final aggressive popup cleanup pass temporarily removed selector and helper symbols in `apps/extension-douyin-capture/src/popup.ts` that were still referenced by the current scanner-shell render path.
- The visible symptom was a TypeScript/build failure in the extension workspace with missing names such as `wholeProfileViewResultsButton`, `wholeProfileOpenAdvancedButton`, `wholeProfileQuickStartHintEl`, `wholeProfileStepperEl`, `wholeProfileRunMetricsEl`, `wholeProfileRunAlertEl`, and several backend/result panel references.
- Recovery action: restored the still-live popup symbols and reintroduced minimal compatibility stubs needed by the current file shape, then re-ran validation.
- Post-recovery validation passed again:
  - `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
  - `npm run extension:test`
  - `npm run extension:build`
- Final safe state: the large legacy paths removed in this cleanup series remain removed, but popup-level residual cleanup stopped at the point where build/test health stayed green. Further popup simplification should be done only as a controlled refactor, not as blind token removal.
