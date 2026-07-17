# Phase 22C-9E Background-Owned Scan Profile Log

## Scope

Phase 22C-9E moves Scan Profile execution out of the popup runtime. The popup now starts the job by sending `DOUYIN_SCANNER_START_SCAN_PROFILE`; the background service worker owns the scan lifecycle.

## Root Cause

The previous Scan Profile route was popup-owned. The popup wrote `action_lock=scan_profile`, `active_task=scan_profile`, `phase=ensuring_content_script`, and `background_route_hit=not_applicable_popup_runtime`, then directly entered the controller path. If the popup closed or stalled, the scan could remain stuck with no `scan_run_id`, no watchdog start, and no finalization diagnostics.

## Implementation

- Added a background `DOUYIN_SCANNER_START_SCAN_PROFILE` route in `background.ts`.
- The background creates a `scan_profile_22C9E_*` run id and starts `runScanProfileWorkflow()` using a background runtime.
- The popup Scan Profile primary action now calls `dispatchBackgroundScanProfileAction22C9E()` and sends only the background start message.
- The controller accepts background-provided scan diagnostics so `scan_run_id`, watchdog timestamps, and owner markers persist from the beginning of the run.
- Content-script DOM probe responses now echo `traceVersion: "22C-9E"` and `scan_run_id`.
- Popup stale-lock recovery clears old popup-authored Scan Profile locks that have no run id and no watchdog start.

## Runtime Contract

Popup responsibilities:

- Send `DOUYIN_SCANNER_START_SCAN_PROFILE` with `traceVersion: "22C-9E"`.
- Render the updated state after background dispatch.
- Record dispatch failure diagnostics if `chrome.runtime.sendMessage` fails.

Background responsibilities:

- Own `scan_run_id`.
- Own `action_lock=scan_profile` through the controller lifecycle.
- Resolve the active Douyin tab.
- Ping/inject the content script.
- Send DOM probe and profile scan messages.
- Persist watchdog, stage, route, and finalization diagnostics.

Content script responsibilities:

- Respond to scanner ping, DOM probe, and profile scan messages.
- Echo `traceVersion` and `scan_run_id` on probe diagnostics.

## Files Changed

- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`

## Validation

Focused tests passed:

```cmd
npx --workspace @reup-douyin/extension-douyin-capture tsx src/popupWorkflow.test.ts && npx --workspace @reup-douyin/extension-douyin-capture tsx src/modalWholeProfileTest.test.ts && npx --workspace @reup-douyin/extension-douyin-capture tsx src/wholeProfileHarvest.viewModel.test.ts
```

Earlier typecheck passed after implementation fixes:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
```
