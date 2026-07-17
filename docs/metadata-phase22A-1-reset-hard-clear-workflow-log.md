# Phase 22A-1 Reset Hard Clear Workflow Log

## Scope

Phase 22A-1 fixes the Douyin Scanner Reset action so it hard-clears scanner workflow state instead of preserving stale scan/classification/queue UI such as `58 videos`, `Start Collecting`, and `Queue 58`.

## Active Reset Button Path

- Active popup footer button: `apps/extension-douyin-capture/public/popup.html`, `#scannerResetButton`.
- The button is explicitly `type="button"` and remains a danger ghost action.
- Popup wiring is in `apps/extension-douyin-capture/src/popup.ts`.

## Implementation Summary

- Reset click handlers now receive the click event and call `preventDefault()` plus `stopPropagation()` inside the reset handler.
- The reset handler writes the canonical hard-reset state through `resetScannerWorkflowState(...)`.
- The popup immediately assigns the returned reset state to local popup state and renders from that returned state with `renderWholeProfileHarvestProductStateFromState(...)`.
- Reset does not reload the popup, extension, or Douyin tab.
- The controller hard reset continues to start from the idle state and preserve only allowed operator context.

## Storage Keys / State Cleared

The canonical storage key is `douyinWholeProfileHarvest` (`WHOLE_PROFILE_HARVEST_STATE_KEY`). Reset clears the workflow-bearing data under that key, including:

- `run_id`
- `capture_session_id`
- `layer`
- `profile_scan`
- `target_status`
- `classification`
- `verify`
- `dry_run`
- `workflow.scan`
- `workflow.classification`
- `workflow.collection`
- `workflow.active_task`
- `workflow.action_lock`
- `harvest.queue`
- `harvest.queue_preview`
- `harvest.planned_total`
- `harvest.current_index`
- `harvest.current_aweme_id`
- `harvest.progress_counts`
- `harvest.pause_diagnostics`
- `harvest.collect_trace`
- `harvest.backend`
- `harvest.results`
- `last_error`

## State Kept

Reset preserves by default:

- calibration state
- operator harvest settings (`mode`, `batch`, `speed`, unattended safe mode)
- current profile/source URL context
- page context
- latest tab-health/resume-check safety diagnostics
- API base URL in sync storage is not touched

## Reset While Busy

Reset is allowed while scanner workflow state is busy. The hard reset clears running collection state, `active_task`, `action_lock`, current target, current index, queue, and progress. After reset the scanner view model returns to `Scan Profile`.

## Diagnostics Added

Reset diagnostics are stored in `debug.last_request_summary` and `debug.last_response_summary`, including:

- `reset_at`
- `reset_result`
- `reset_cleared_keys`
- `reset_kept_calibration`
- `reset_kept_settings`
- `reset_storage_write_status`
- `reset_background_cancel_status`
- `state_version_after_reset`
- `profileScanReady`
- `classificationReady`
- `collectQueueReady`
- `queueCount`
- `active_task`
- `busy`

Advanced details now display reset result, reset timestamp, storage write status, kept calibration/settings, reset queue count, and background cancel status.

## Tests Added / Updated

- Controller reset tests now assert profile scan, classification, target status, queue preview, current index/target, progress counts, active locks, diagnostics, and persisted storage write are cleared.
- Busy reset coverage verifies reset works when collection is running and active task/action lock exist.
- Popup static tests verify reset button type, event handling, no reload calls, canonical reset write, immediate local render, and no backend call from reset rendering.
- View-model tests verify post-reset hero is `Ready`, primary action is `Scan Profile`, queue count is zero, stats are hidden by cleared profile scan, and Advanced reset diagnostics show success.

## Non-Goals

- No UI redesign.
- No backend API changes.
- No Capture Inbox UI changes.
- No crawler/video processing/scoring implementation.
- No clearing calibration, API base URL, or operator collection settings by default.
