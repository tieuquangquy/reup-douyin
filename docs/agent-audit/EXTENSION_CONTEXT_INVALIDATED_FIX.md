# Extension Context Invalidated Fix

## Root cause

Reloading the unpacked Chrome extension while a Douyin tab stays open leaves the old content script running in the page with an invalid extension context. When that stale content script later calls Chrome extension APIs, calls such as `chrome.storage.local.get("douyinSafeHarvestRun")` can reject with `Extension context invalidated`.

The most visible failing path was the Harvest Runtime V2 loader in the content script. It read `HARVEST_RUNTIME_V2_KEY` directly from `chrome.storage.local` without a local guard, so an invalidated context could escape as an unhandled promise rejection. Popup stale recovery could then show a mixed state: scanner locks recovered, but `workflow.collection.status` still displayed `running` even when there was no active task or action lock.

A separate browser invariant caused the XHR error. `XMLHttpRequest.responseText` is only accessible when `xhr.responseType` is `""` or `"text"`. The page network hook and the older network cache hook read `responseText` directly, so Douyin XHRs with `arraybuffer`, `blob`, `document`, or `json` response types could throw `InvalidStateError`.

## Files changed

- `apps/extension-douyin-capture/src/contentScript.ts`
  - Added narrow safe wrappers around `chrome.storage.local.get`, `set`, and `remove` for context invalidation.
  - Added an in-memory failed Harvest Runtime V2 fallback with the operator-facing message: reload the Douyin tab after reloading the extension, then scan again.
  - Applied the wrappers to runtime initialization, load/save, pending queue load/save, reset, and legacy state cleanup paths.
- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
  - Added `safeXhrResponseText()` and only reads `responseText` for `""` or `"text"` XHR response types.
- `apps/extension-douyin-capture/src/networkCache.ts`
  - Added the same XHR `responseType` guard to the older cache hook.
- `apps/extension-douyin-capture/src/popup.ts`
  - Made stale collection recovery consistent when `workflow.collection.status` is `running` with no active task and no action lock.
  - The popup now pauses that stale ownerless collection display and records diagnostics without clearing queue or calibration.
- `apps/extension-douyin-capture/src/networkProbe.test.ts`
  - Updated source-text coverage for the XHR responseText guard.
  - Aligned stale route/marker assertions with the current protected 22C-11B route ownership.
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
  - Added stale ownerless collection recovery assertions.

## Before behavior

- Old content scripts in tabs that survived an extension reload could throw unhandled `Extension context invalidated` errors from runtime storage reads.
- Popup recovery could report `stale_recovered` while still showing collection as `running` with no active task/action lock.
- XHR hooks could throw `InvalidStateError` when Douyin used non-text XHR response types.

## After behavior

- Context invalidation at the content-script runtime storage boundary is caught and converted into a clear in-memory failed/interrupted runtime state.
- The operator-facing recovery direction is explicit: reload the Douyin tab after extension reload, then scan again.
- Ownerless stale running collection state is displayed consistently as paused/interrupted instead of harvesting/running.
- XHR hooks skip non-text response bodies and preserve existing text JSON passive probe behavior.

## Manual validation steps

1. Run `npm run build` in `apps/extension-douyin-capture`.
2. Load or reload the unpacked extension in Chrome.
3. If a Douyin profile tab was already open before the extension reload, refresh that Douyin tab once.
4. Open the popup and confirm diagnostics do not show an ownerless `collection.status: running` with `active_task: none` and `action_lock: none`.
5. Click Scan Profile and confirm the current protected 22C-11B route still starts.
6. Click Start Collecting and confirm the state either starts normally or clearly asks to reload the Douyin tab after extension reload.
7. Observe DevTools console while Douyin network traffic loads. Non-text XHRs should not produce `responseText` `InvalidStateError`.
8. Use Reset Harvest only when intentionally clearing the current harvest run. Calibration should remain available after Reset Harvest.

## Remaining risks

- A content script with an invalidated extension context cannot persist diagnostics back to extension storage because the storage API itself is unavailable. The fallback state is intentionally in-memory and user-action oriented.
- The safest recovery after reloading the extension is still to reload the Douyin tab so Chrome injects a fresh content script context.
- The fix makes stale Start Collecting state consistent and diagnosable; it does not guarantee continuation of work from an invalidated stale content script because Chrome extension APIs are no longer available in that old context.
- Route marker assertions were aligned to current protected 22C-11B ownership only; no runtime route marker migration was performed.
