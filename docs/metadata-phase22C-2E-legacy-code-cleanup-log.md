# Phase 22C-2E Legacy Code Cleanup Log

## Legacy inventory

- Active canonical code:
  - `runStartCollectingWorkflow()`
  - `resumeHarvest()`
  - `runBatchCollectNext3SafeMode()`
  - `runOneItemCollectAndSave()`
- Legacy but still imported:
  - `runHarvest()` export, retained for Node test/dev compatibility only
  - `runRealModalExtractionHarvest()` internal legacy whole-profile runner
- Dead UI/actions:
  - Advanced `Dry run + verify` buttons in `public/popup.html`
  - non-rendered popup selectors/handlers for legacy save/flush controls remain inert because the DOM ids are absent
- Legacy state:
  - forbidden stored runner targets inside `harvest.pause_diagnostics`
  - forbidden stored runner targets inside `debug.last_request_summary` / `debug.last_response_summary`

## Cleanup implemented

- Added explicit allowlist:
  - `runBatchCollectNext3SafeMode`
  - `wholeProfileHarvest/controller.runBatchCollectNext3SafeMode`
  - `runOneItemCollectAndSave`
  - `wholeProfileHarvest/controller.runOneItemCollectAndSave`
- Added explicit denylist for:
  - `runRealModalExtractionHarvest`
  - `wholeProfileHarvest/controller.runRealModalExtractionHarvest`
  - legacy modal/flush aliases
- `resumeHarvest()` and `runStartCollectingWorkflow()` now assert the canonical safe batch target before dispatch.
- `runHarvest()` is quarantined:
  - available in Node test/dev only
  - blocked in production scanner flow
  - records `forbidden_runner_target_*` diagnostics and clears stale collect locks if called

## State migration

- Added `migrateLegacyScannerStateToCanonical(state)` during `readWholeProfileHarvestState()`.
- Preserves:
  - calibration
  - settings
  - collect queue
  - capture session id
- Removes/quarantines:
  - forbidden `resume_runner_target`
  - forbidden `start_collecting_dispatch_target`
  - forbidden legacy runner target diagnostics
- If stale collect lock is paired with a forbidden runner target:
  - clears `active_task`
  - clears `action_lock`
  - recovers collection state to `paused` or `idle`

## UI cleanup

- Removed the visible `Dry run + verify` section from `public/popup.html`.
- Current popup flow remains:
  - Scan Profile
  - Start Collecting
  - Pause
  - Resume
  - Capture Inbox
  - Advanced
  - Reset
  - Collection settings

## Tests added

- Start Collecting and Resume dispatch static checks
- forbidden runner allowlist/denylist checks
- forbidden runner state migration and lock-clear recovery checks
- popup static check that production popup code does not import or dispatch `runRealModalExtractionHarvest`

## Remaining legacy code

- `runRealModalExtractionHarvest()` remains in the controller because the existing test/dev compatibility surface still exercises `runHarvest()`.
- It is now quarantined behind a runtime guard and is no longer reachable from popup Start/Resume production flow.
