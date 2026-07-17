# Phase 22A-2 Active Reset Button Hard Clear Log

## Summary

Implemented Phase 22A-2 to force-wire the visible Douyin Scanner footer Reset button and prove the active handler runs before any asynchronous reset work.

## Active Reset Button

The active footer Reset button is `#scannerResetButton` in `apps/extension-douyin-capture/public/popup.html` and now carries the internal marker comment:

```html
<!-- 22A-2 ACTIVE SCANNER RESET BUTTON -->
```

The button remains `type="button"` to avoid submit/navigation behavior.

## Handler Proof

The active footer Reset button now calls `resetWholeProfileHarvestStateFromPopup(event, "active_footer")`. The handler calls `event.preventDefault()` and `event.stopPropagation()`, then immediately records local diagnostics before confirmation or async storage reset:

- `last_action_clicked = "reset"`
- `last_action_result = "clicked"`
- `reset_result = "clicked"`
- `reset_at = now`
- `reset_storage_write_status = "pending"`
- `reset_source = "active_footer"`

## Hard Clear Behavior

The canonical reset still uses `resetScannerWorkflowState`, which writes a reset `douyinWholeProfileHarvest` state that clears stale scanner workflow state, queue/progress, backend transient readiness, session ids, active task/action lock, stale paused/running collection state, previous errors, and readiness flags.

## Preserved State

Reset preserves:

- profile/source URL context
- calibration
- harvest options such as mode, batch, speed, unattended safe mode
- page context
- tab health and resume-check diagnostics

## Old State Restoration Prevention

The popup now reloads canonical state from storage after reset write and renders that stored reset state. A local reset generation guard prevents older async reset responses from replacing newer reset state. The storage change listener also rejects incoming scanner state snapshots whose reset timestamp is older than the currently rendered reset diagnostics.

## Diagnostics

Successful reset diagnostics now expose:

- `reset_result = "success"`
- `reset_storage_write_status = "success"`
- `reset_storage_write = "success"`
- `state_generation = reset_at`
- `reset_cleared_storage_keys = ["douyinWholeProfileHarvest"]`
- queue count, active task, busy state cleared indicators

## Files Changed

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase22A-2-active-reset-button-hard-clear-log.md`
- `docs/metadata-phase22A-2-active-reset-button-hard-clear-resume.md`
