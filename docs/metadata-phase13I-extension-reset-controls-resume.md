# Phase 13I Extension Reset Controls Resume

## Status

Phase 13I implementation is in progress. Code and focused tests have been added; typecheck has passed. Remaining steps are full extension test, standalone build, and final report.

## Files Changed

- `apps/extension-douyin-capture/src/storageKeys.ts`
  - Centralized extension storage key audit and reset key groups.

- `apps/extension-douyin-capture/src/extensionReset.ts`
  - Added `resetHarvestState()`, `resetCalibrationState()`, and `factoryResetExtensionState()`.
  - Added confirmation message constants.

- `apps/extension-douyin-capture/src/popup.ts`
  - Added Maintenance button bindings.
  - Added reset handlers.
  - Added running-harvest confirmation/stop behavior.
  - Resets stale progress panel immediately after reset.

- `apps/extension-douyin-capture/src/contentScript.ts`
  - Added `REUP_DOUYIN_RESET_FULL_MODAL_HARVEST_STATE` handling.
  - Added in-memory harvest controller reset and persisted harvest-state cleanup.

- `apps/extension-douyin-capture/src/types.ts`
  - Added reset message to `ExtensionMessage` union.

- `apps/extension-douyin-capture/src/chrome.d.ts`
  - Added `chrome.storage.sync.remove()` and array remove overloads.

- `apps/extension-douyin-capture/public/popup.html`
  - Added Maintenance section and three reset buttons.

- `apps/extension-douyin-capture/public/popup.css`
  - Added secondary, warning, and danger button styles.

- `apps/extension-douyin-capture/src/extensionReset.test.ts`
  - Added reset storage cleanup and source/UI assertions.

- `apps/extension-douyin-capture/src/popupWorkflow.ts`
  - Added Maintenance buttons to production button id list.

- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
  - Updated production button count and Maintenance assertion.

- `apps/extension-douyin-capture/package.json`
  - Added reset test to extension test command.

## Preservation Policy

Factory Reset preserves:

- `apiBaseUrl`
- `harvestMode`
- `installId`

It removes local extension workflow state and capture session ids only; backend database data is not touched.

## Commands Already Run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`

Result: passed.

## Next Steps

1. Run `npm --workspace @reup-douyin/extension-douyin-capture run test`.
2. Run `npm --workspace @reup-douyin/extension-douyin-capture run build`.
3. Update docs if command results reveal changes.
4. Final report with exactly the requested Phase 13I sections.
