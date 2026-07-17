# Phase 7B CDP Observability Attach-Before-Modal Log

## Scope

Phase 7B is limited to `apps/extension-douyin-capture` and CDP attach/probe diagnostics documentation. It makes the active-tab CDP harvester visible in the extension popup and gives the operator a reliable attach-before-modal path.

## Root Cause

The Phase 7A CDP harvester existed behind content-script probe flow, but the operator could not see CDP attachment state or counters from the popup. When the modal video was already loaded before CDP attached, network responses were missed, so probe output fell back to DOM diagnostics and looked like the old action-rail path.

## Changes

- Confirmed `debugger` permission in `public/manifest.json`.
- Added popup actions for attach, detach, status, CDP probe, and attach-refresh-probe.
- Extended CDP status with debugger version, domain enablement flags, JSON response counters, runtime exact matches, last matching aweme id, last response URL, and last error.
- Propagated richer CDP diagnostics into probe results.
- Added `REUP_DOUYIN_CDP_STATUS` and `REUP_DOUYIN_CDP_REFRESH_MODAL` message handling.
- Added background CDP tests for manifest permission, attach state, network body parsing counters, exact match caching, refresh reload, and safe detach.

## Operator Behavior

Use `Attach CDP to Current Douyin Tab` on a Douyin profile before opening a video modal. CDP then listens for `Network.responseReceived` and `Network.loadingFinished`, calls `Network.getResponseBody`, parses JSON, and caches aweme candidates by `aweme_id`.

If already in a modal, use `Attach CDP and Refresh Current Modal`. It attaches CDP, enables Network/Runtime/Page, reloads the current tab while preserving the current URL, waits briefly for network responses, then probes the modal.

## Verification

- `npx tsc -p tsconfig.json --noEmit`
- `npx tsx src\\background.test.ts`
- `npx tsx src\\modalHarvest.test.ts`
