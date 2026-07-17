# Phase 18I-J7 Popup Operator Flow User Guide

## What It Does
The Phase 18I-J7 popup cleanup leaves the main Douyin extension popup focused on one operator-ready workflow:

1. reconnect to the active Douyin tab
2. calibrate if needed
3. verify the profile scan
4. run a dry-run test sample
5. extract the selected harvest batch
6. save one item to verify Capture Inbox write behavior
7. save the remaining verified batch

Technical and recovery actions remain available through [`Technical Details`](apps/extension-douyin-capture/public/popup.html:252), but the main surface no longer treats legacy probe/test controls as primary operator actions.

## Main Operator Steps
1. Open the Douyin extension popup.
2. If the popup shows a disconnected or blocked state, click `Reconnect Douyin Tab`.
3. If calibration is missing or stale, click `Start Calibration` and complete the rail-point capture.
4. In the `Douyin Profile Harvester` section, choose:
   - harvest mode
   - batch size
   - speed
   - whether unattended safe mode should remain enabled
5. Click `Scan Profile` to verify profile readiness and collect target cards.
6. Click one dry-run button:
   - `Test First Videos`
   - `Test Last Videos`
   - `Test Random Videos`
7. Confirm the dry-run result is successful before extracting a real batch.
8. Click `Extract Batch`.
9. In the `Save to Capture Inbox` section, click `Save 1 Video` first.
10. Confirm the popup reports a verified one-item save.
11. Click `Save Batch` to flush the remaining verified items.
12. Review the queue preview, extraction results, backend results, and next-action guidance in the progress panels.

## Expected Safe Workflow
- Use `Save 1 Video` first whenever a new save session starts.
- If `Save Batch` is disabled, follow the popup guidance instead of forcing a batch save.
- If the popup pauses for captcha or checkpoint handling, resolve it in the active Douyin tab, then click `Resume Harvest`.
- If extraction was stopped intentionally, use `Resume Harvest` instead of starting over unless a full reset is required.
- Use `Reset Harvest State` only when the current run should be discarded.

## Technical Details
Use [`Technical Details`](apps/extension-douyin-capture/public/popup.html:252) for maintenance and diagnostics such as:
- copying debug JSON
- clearing legacy state
- reviewing progress details
- using explicit reset/recovery actions

This panel is intentionally secondary. It should help recovery and diagnostics without reintroducing legacy-noise buttons into the primary operator workflow.

## Manual Verification Script
Use this manual E2E checklist after loading a fresh extension build:

1. Open a supported Douyin profile tab.
2. Open the popup and confirm the visible primary workflow only shows the canonical operator actions.
3. Confirm the removed legacy probe button is not present on the main popup surface.
4. Run `Scan Profile` and confirm verified target counts appear.
5. Run one dry-run action and confirm it completes without exposing hidden legacy controls.
6. Run `Extract Batch` and confirm queue preview / extraction results populate.
7. Run `Save 1 Video` and confirm verified Capture Inbox write status appears.
8. Run `Save Batch` and confirm backend result counts update.
9. Trigger a pause/recovery path if available and confirm `Resume Harvest` remains available.
10. Expand `Technical Details` and confirm diagnostics remain accessible there instead of the main workflow.

## Deferred
- No crawler implementation.
- No backend contract redesign.
- No auto-publish flow.
- No browser-level full E2E automation suite in this step.
