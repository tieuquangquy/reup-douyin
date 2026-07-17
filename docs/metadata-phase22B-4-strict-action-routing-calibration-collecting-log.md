# Phase 22B-4 — Strict action routing calibration/collecting log

## Scope

Implemented only Phase 22B-4: strict primary action routing so Start Collecting never activates calibration. The change keeps the local-first extension workflow SaaS-ready by making popup action intent explicit, preserving controller preflights, and recording stable diagnostics.

## Problem fixed

A scanner state could show Profile scanned, Cal ready, Safe, and Next action/primary button as Start Collecting, but clicking the primary button could surface the calibration overlay instead of starting collection. Phase 22B-4 makes this impossible by routing from typed action keys rather than label text or inferred UI state.

## Changes

- Standardized scanner action keys in `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`.
- Extended scanner view models in `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts` with a canonical `primaryAction` object while preserving legacy-compatible `action` fields.
- Refactored the popup primary action path in `apps/extension-douyin-capture/src/popup.ts`:
  - `runWholeProfilePrimaryActionFromPopup()` reads `primaryAction.key` from `getScannerControlPanelViewModel(state)`.
  - `handlePrimaryActionClick(actionKey, label)` switches directly on the action key.
  - `start_collecting` routes only to `runWholeProfileHarvestProductFromPopup()`.
  - `calibrate` routes only to `startCalibration()`.
  - No primary handler infers behavior from button label text.
- Added primary action diagnostics in `apps/extension-douyin-capture/src/popup.ts`:
  - `last_primary_action_key_clicked`
  - `last_primary_action_label_clicked`
  - `last_primary_action_dispatch_target`
- Added Start Collecting calibration cleanup in `apps/extension-douyin-capture/src/popup.ts` and `apps/extension-douyin-capture/src/contentScript.ts`:
  - Popup sends `REUP_DOUYIN_STOP_RIGHT_RAIL_CALIBRATION` before Start Collecting.
  - Content script tears down active calibration overlay/listeners via `ensureCalibrationModeStopped()`.
  - Popup passes `calibration_mode_active_before_start` and `calibration_mode_stopped_before_start` into the controller.
- Added content-script message/response contract fields in `apps/extension-douyin-capture/src/types.ts`.
- Tightened canonical calibration readiness in `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`:
  - canonical `status === "calibrated"`
  - `ready === true`
  - `point_count >= 4`
  - all four canonical or legacy point records present
- Added Start Collecting diagnostics and exact preflight blocks in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`:
  - `start_collecting_clicked_at`
  - `start_collecting_stage`
  - `Calibrate 4 Points first.`
  - `Calibration context is missing. Re-run calibration from Advanced.`
  - `Calibration was captured in a different layout. Re-run calibration on a profile modal.`
  - `Calibration mode is still active. Cancel calibration first.`
- Updated fixtures/tests for canonical calibration readiness and Phase 22B-4 routing/diagnostics.

## Test coverage added/updated

- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
  - Verifies popup strict dispatch target mapping.
  - Verifies `handlePrimaryActionClick(actionKey, label)` dispatches by key.
  - Verifies `start_collecting` handler case routes to Start Collecting only.
  - Verifies `start_collecting` handler case does not call calibration APIs/messages.
  - Verifies primary action diagnostics fields are present.
  - Verifies popup sends the calibration stop message before Start Collecting.
  - Verifies content script exposes the explicit calibration cleanup message and cleanup path.
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
  - Verifies Start Collecting blocked calibration readiness diagnostics.
  - Verifies strict Start Collecting dispatch diagnostics survive controller blocking.
  - Verifies active calibration mode blocks Start Collecting with the exact required message.
  - Verifies cleanup diagnostics are recorded when calibration mode remains active.
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
  - Verifies canonical calibration readiness rejects status-only, ready-only, point-count-only, and stale unknown/missing states.
  - Verifies canonical/complete legacy records remain accepted only when all required points exist.
- `apps/extension-douyin-capture/src/wholeProfileHarvest.backendFlow.test.ts`
  - Updated backend-flow fixtures to use canonical-ready calibration.

## Validation

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No scoring or filtering implementation.
- No database schema or queue implementation.
- No UI redesign beyond strict action routing behavior required for Phase 22B-4.
- No auto-publish integration.
