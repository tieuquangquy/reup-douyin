# Phase 11D Content-Script Viewport Source Log

## Scope

Phase 11D is limited to `apps/extension-douyin-capture` and extension docs/tests for the popup viewport source-of-truth bug.

## Exact Root Cause

The popup was using its own extension window dimensions as the Douyin page viewport. In the live bug, the popup reported `375x600` as `Current viewport` even while the active Douyin tab modal viewport was calibrated at `1920x919`. That happened because popup workflow state accepted a popup-computed `currentViewport`, and Smart Capture compared calibration dimensions against `globalThis.window.innerWidth` / `globalThis.window.innerHeight` inside the popup context.

## Fix Implemented

- Added a typed `DouyinPageViewport` contract whose only valid source is `content_script`.
- Added the `GET_DOUYIN_PAGE_VIEWPORT` popup-to-content-script message.
- Added content-script helper `getDouyinPageViewport()` that reads viewport data inside the Douyin tab and returns width, height, visual viewport, device pixel ratio, URL, modal id, and `source: "content_script"`.
- Reworked popup state to store `currentPageViewport` and `currentPageViewportSource` instead of popup `currentViewport`.
- Removed the popup `getCurrentViewport()` fallback and removed popup `globalThis.window.innerWidth` / `globalThis.window.innerHeight` from harvest calibration checks.
- Renamed the status summary label from `Current viewport` to `Current page viewport` and added `Viewport source`.
- When the content-script viewport bridge is unavailable, Smart Capture now blocks with `content_script_viewport_unavailable` and the operator action `Refresh Douyin tab and retry`.
- Viewport comparison now runs only when the current page viewport source is `content_script`.
- Stale `viewport_changed_significantly` state is cleared when a valid content-script viewport matches calibration and the workflow is otherwise ready.

## Popup Fallback Removed

The popup no longer computes Douyin page viewport from popup `window` dimensions. The removed behavior was the direct comparison of calibration dimensions against popup `globalThis.window.innerWidth` / `globalThis.window.innerHeight`, plus the popup `getCurrentViewport()` fallback stored in the operational snapshot.

## Content-Script Message Flow

1. Popup requests the active Douyin tab viewport with `GET_DOUYIN_PAGE_VIEWPORT`.
2. The Douyin content script handles that message.
3. The content script returns `{ ok: true, success: true, viewport }` with `viewport.source === "content_script"`.
4. Popup accepts the viewport only if the response is successful and the source is exactly `content_script`.
5. Any missing, failed, or invalid response becomes `content_script_viewport_unavailable` without falling back to popup dimensions.

## Tests Added/Updated

- Popup source assertions forbid popup `globalThis.window.innerWidth` / `globalThis.window.innerHeight` as page viewport.
- Popup source assertions require `GET_DOUYIN_PAGE_VIEWPORT`, `Current page viewport`, and `Viewport source`.
- Workflow tests require viewport warning comparison only from `content_script` source.
- Workflow tests verify content-script viewport unavailable blocks with `content_script_viewport_unavailable`, not `viewport_changed_significantly`.
- Workflow tests verify calibrated `1920x919` plus content-script `1920x919` returns `Viewport warning: none`.
- Workflow tests verify popup-sized `375x600` without `content_script` source does not trigger `viewport_changed_significantly`.
- Source tests verify calibrated point ratios are calculated in content script using `getDouyinPageViewport()`.

## Verification

Pending final command verification:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Steps

1. Reload the unpacked extension from `apps/extension-douyin-capture`.
2. Open a Douyin profile in the browser tab.
3. Open the target video modal so the tab URL contains `modal_id=7623445952279416107`.
4. Open the extension popup.
5. Confirm the popup status summary shows `Current page viewport: 1920x919` or the actual Douyin tab viewport, not `375x600`.
6. Confirm `Viewport source: content_script`.
7. Confirm `Viewport warning: none` when the current page viewport matches the calibrated viewport.
8. Confirm `Last error: none` after stale `viewport_changed_significantly` is cleared.
9. Click Smart Capture & Harvest and confirm it does not require recalibration when page viewport matches calibration.
10. Refresh the Douyin tab and retry if the popup reports `content_script_viewport_unavailable`.
