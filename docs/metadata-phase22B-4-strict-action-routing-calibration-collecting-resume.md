# Phase 22B-4 — Strict action routing calibration/collecting resume

## Current state

Phase 22B-4 is implemented and validated. The active scanner primary button now routes by typed action key. Start Collecting no longer starts or inherits calibration mode.

## Key files

- `apps/extension-douyin-capture/src/popup.ts`
  - Active primary button path: `scannerPrimaryActionButton` -> `runWholeProfilePrimaryActionFromPopup(event)` -> `getScannerControlPanelViewModel(state).primaryAction` -> `handlePrimaryActionClick(primaryAction.key, primaryAction.label)`.
  - Strict dispatcher: `handlePrimaryActionClick(actionKey, label)`.
  - Dispatch target helper: `primaryActionDispatchTarget(actionKey)`.
  - `start_collecting` routes to `runWholeProfileHarvestProductFromPopup()` only.
  - `calibrate` routes to `startCalibration()` only.
  - Start Collecting first calls `ensureCalibrationModeStoppedBeforeStartCollecting()`.
  - Diagnostics recorded: `last_primary_action_key_clicked`, `last_primary_action_label_clicked`, `last_primary_action_dispatch_target`, `calibration_mode_active_before_start`, `calibration_mode_stopped_before_start`.

- `apps/extension-douyin-capture/src/contentScript.ts`
  - Tracks active calibration mode in `activeCalibrationMode`.
  - `ensureCalibrationModeStopped()` clears prompt state, removes overlay/listeners, and nulls active calibration mode.
  - Handles `REUP_DOUYIN_STOP_RIGHT_RAIL_CALIBRATION` with cleanup diagnostics.

- `apps/extension-douyin-capture/src/types.ts`
  - Adds `REUP_DOUYIN_STOP_RIGHT_RAIL_CALIBRATION` to extension messages.
  - Adds `calibration_mode_active_before_stop` and `calibration_mode_stopped` response fields.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
  - Defines canonical `ScannerActionKey`.
  - Requires canonical calibration readiness from `status`, `ready`, `point_count`, and all four points.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
  - Exposes `primaryAction` with key, label, title, description, enabled, and disabledReason.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - `runStartCollectingWorkflow()` records Start Collecting click/stage diagnostics.
  - `validateStartCollectingCalibrationContext()` enforces exact Phase 22B-4 calibration block reasons.
  - Blocks if calibration mode cleanup reports `calibration_mode_stopped_before_start === false`.

## Action dispatch mapping

- `scan_profile` -> `runScanProfileWorkflow` / `verifyWholeProfileFromPopup()`.
- `calibrate` -> `runCalibrationWorkflow` / `startCalibration()`.
- `start_collecting` -> `runStartCollectingWorkflow` / `runWholeProfileHarvestProductFromPopup()`.
- `pause` -> `pauseCollecting` / `stopWholeProfileHarvestFromPopup()`.
- `resume` -> `resumeCollecting` / `handleResumeCollectingClick("primary_action_card")`.
- `open_capture_inbox` -> `openCaptureInbox` / `setDeckActivePanel("results")`.
- `none` -> no-op.

## Start Collecting preflight behavior

Start Collecting blocks without auto-calibrating when:

- Calibration is incomplete: `Calibrate 4 Points first.`
- Calibration context is missing: `Calibration context is missing. Re-run calibration from Advanced.`
- Calibration layout is not profile-modal compatible: `Calibration was captured in a different layout. Re-run calibration on a profile modal.`
- Calibration mode remains active after cleanup request: `Calibration mode is still active. Cancel calibration first.`

## Validation run

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.

## Manual retest steps

1. Open a Douyin profile state where the scanner shows Profile, Cal ready, Safe, and Next action Start Collecting.
2. Click the visible Start Collecting primary button.
3. Confirm no calibration overlay appears and no like/comment/favorite/share click-capture prompt starts.
4. Confirm collection enters Opening first video, running, completed, or a visible exact blocked reason.
5. Open Advanced calibration explicitly and click Calibrate 4 Points.
6. Confirm calibration overlay appears only from the explicit calibration action.
7. Start calibration, then click Start Collecting while calibration mode is active.
8. Confirm calibration mode is stopped before collection, or collection blocks with `Calibration mode is still active. Cancel calibration first.` if cleanup fails.
9. Inspect debug JSON and confirm the latest click includes `last_primary_action_key_clicked`, `last_primary_action_label_clicked`, `last_primary_action_dispatch_target`, `start_collecting_clicked_at`, and `start_collecting_stage`.
