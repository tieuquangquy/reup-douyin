# Phase 22B-3 — Start Collecting preflight bounce fix resume

## Current state

Phase 22B-3 adds deterministic Start Collecting behavior before the one-item collect runner.

## Key files

- `apps/extension-douyin-capture/src/popup.ts`
  - Active visible button is `#scannerPrimaryActionButton`.
  - Internal marker: `// 22B-3 ACTIVE START COLLECTING BUTTON`.
  - Click handler now receives the event and prevents default/propagation.
  - Start Collecting dispatch reads state without calibration sync.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - `runStartCollectingWorkflow()` writes clicked diagnostics immediately.
  - `runStartCollectingPreflight()` performs ordered preflight and returns explicit blocked reasons.
  - `getFirstPendingTargetForOneItemCollect()` selects one pending queue target.
  - `runOneItemCollectAndSave()` is the named one-item runner entrypoint.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
  - Collection status includes `opening_target`.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
  - Opening first video appears as visible scanner progress.
  - Start Collecting failures remain visible as an error alert.

## Validation run

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.

## Manual retest focus

1. Open a scanned profile with queue and calibrated profile-modal points.
2. Click Start Collecting.
3. Confirm the UI immediately shows Opening first video or an exact blocked/failed reason.
4. Confirm there is no Calibrate 4 Points flash/bounce unless the stable preflight result is a calibration block.
5. Confirm one item is saved and verified in Capture Inbox when backend/session/runner are available.
