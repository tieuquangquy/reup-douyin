# Phase 13B Harvest State UI Cleanup Log

## Scope

Phase 13B is limited to `apps/extension-douyin-capture` and extension-facing documentation. It fixes popup consistency after operator Stop Harvest and improves the Smart harvest mode control without changing backend APIs, web UI, metric extraction, calibration, CDP/debug workflows, or the harvest algorithm beyond stop-state consistency.

## Root Cause

The popup rendered raw harvest progress snapshots. When the operator clicked Stop Harvest, the content script returned the controller snapshot immediately after setting `stopped_reason = "operator_stopped"`. That snapshot could still contain `running: true`, `current_state: "harvesting"`, and a stale active phase such as `extracting_metrics` before the async controller loop unwound. The popup view model treated those raw fields as authoritative, so it displayed `Harvest running` and `Extracting metrics...` even though the summary state had already moved to paused/stopped.

## Changes

- Added display normalization for harvest progress so `operator_stopped`, `paused`, and `stopped` states override stale active phases.
- Added paused/stopped harvest phase and current-state values for explicit operator stop state.
- Updated Stop Harvest to stop popup polling before rendering the stop response.
- Updated Stop Harvest to render normalized stopped progress and keep a local paused panel instead of immediately fetching another stale progress snapshot.
- Updated the content script stop path to return a non-running paused progress object immediately.
- Updated the controller operator-stop path so manual stop is represented as paused/stopped instead of failed.
- Updated popup button state logic to use normalized display-running state.
- Disabled Smart Capture, harvest mode controls, Start Calibration, and Clear Calibration while harvest is actually running; re-enabled them after stop/pause.
- Replaced the raw default mode select with human-readable radio cards while retaining the internal fallback select and values.
- Persisted selected Smart harvest mode in `chrome.storage.sync` with `new_and_incomplete` as the default.

## Verification Added

Extension tests now cover:

- `normalizeHarvestProgressForDisplay()` converts stopped + stale `extracting_metrics` into paused display state.
- Stopped panels do not show active extracting/loading/waiting phase labels.
- Stopped panels preserve counts and target index.
- Paused state shows Resume/Flush guidance.
- Running state still shows active Harvest running behavior.
- Popup HTML renders all three human-readable harvest modes.
- Popup source restores and persists mode selection.
- Stop Harvest cancels polling before rendering normalized stopped progress.
- Button state uses normalized display-running state and disables harvest mode controls while running.

## Operator Result

After Stop Harvest, the popup should show a paused/stopped panel with preserved counts and Resume guidance. It must not show `Harvest running`, `Extracting metrics...`, `Loading next video...`, or `Waiting for modal change...` for the stopped snapshot.