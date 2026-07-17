# Phase 22A-2 Active Reset Button Hard Clear Resume

## Phase

22A-2 — Force wire active Reset button and clear persisted scanner workflow state.

## Completed Changes

- Audited the visible Douyin Scanner footer Reset button and confirmed the active path is `#scannerResetButton`.
- Added the internal marker comment `22A-2 ACTIVE SCANNER RESET BUTTON` next to the active footer button.
- Forced the footer Reset click listener to pass `"active_footer"` into the shared reset handler.
- Added immediate clicked diagnostics before confirmation or async storage work.
- Kept `preventDefault()` and `stopPropagation()` on the reset event path.
- Kept canonical hard reset through `resetScannerWorkflowState`.
- Reloaded canonical `douyinWholeProfileHarvest` state from storage after reset write before rendering.
- Added reset generation / timestamp protections to avoid older state restoring stale `58 videos`, `New: 58`, or `Queue: 58` views.
- Updated reset storage diagnostics from `written` to `success`, and added a direct `reset_storage_write` field.
- Added `state_generation` and `reset_cleared_storage_keys` diagnostics.
- Updated tests for the active marker, active footer handler path, clicked/pending diagnostics, canonical reload after reset, generation guard, and success diagnostics.

## Files Changed

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase22A-2-active-reset-button-hard-clear-log.md`
- `docs/metadata-phase22A-2-active-reset-button-hard-clear-resume.md`

## Expected Manual State After Reset

After clicking the visible footer Reset button and confirming reset, the scanner should show:

- Status: `Ready`
- Primary action: `Scan Profile`
- Stats hidden or zeroed
- Queue count: `0`
- New count: `0`
- Active task: `none`
- Busy: `no`
- Hint: `Scan a profile to build the collection plan.`

Advanced diagnostics should show:

- Reset result: `success`
- Reset storage write: `success`
- Reset kept calibration: `yes`
- Reset kept settings: `yes`
- Reset queue count: `0`

If confirmation is cancelled, diagnostics should still prove the active handler ran with:

- Reset result: `clicked`
- Reset storage write: `pending`

## Required Verification Commands

Run from repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```
