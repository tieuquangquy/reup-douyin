# Phase 11D Content-Script Viewport Source Resume

## Status

Phase 11D implementation is in progress. The extension popup viewport fallback has been removed from the calibrated harvest guard, and the content script now owns the Douyin page viewport source of truth.

## Files Touched

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
- `apps/extension-douyin-capture/src/popupSmartWorkflow.test.ts`
- `docs/metadata-phase11D-content-script-viewport-source-log.md`
- `docs/metadata-phase11D-content-script-viewport-source-resume.md`

## Root Cause To Preserve

The root cause was that popup code treated the popup viewport (`375x600`) as the Douyin page viewport. Popup code must never use popup `window.innerWidth`, `window.innerHeight`, `visualViewport`, or document client dimensions as calibrated harvest page viewport.

## New Source Of Truth

The content script helper `getDouyinPageViewport()` runs inside the Douyin tab and returns:

```ts
{
  width,
  height,
  visual_width,
  visual_height,
  device_pixel_ratio,
  url,
  modal_id,
  source: "content_script"
}
```

The popup requests this through `GET_DOUYIN_PAGE_VIEWPORT` and only accepts a response whose viewport source is exactly `content_script`.

## Behavior Expectations

- Popup summary uses `Current page viewport`, not `Current viewport`.
- Popup summary includes `Viewport source`.
- If content script viewport is unavailable, popup shows/uses `content_script_viewport_unavailable` and Smart Capture blocks with `Refresh Douyin tab and retry`.
- Popup does not fall back to popup `375x600`.
- Calibration comparison runs only against content-script page viewport.
- A matching `1920x919` content-script viewport clears stale `viewport_changed_significantly` state.
- A real content-script page viewport change greater than 15% still blocks with recalibration.

## Verification Still Required

Run from the repository root on Windows:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Steps

1. Reload the unpacked extension.
2. Open the Douyin modal URL containing `modal_id=7623445952279416107`.
3. Open the popup.
4. Confirm `Current page viewport` matches the Douyin tab viewport, not `375x600`.
5. Confirm `Viewport source: content_script`.
6. Confirm `Viewport warning: none` when calibration and page viewport are both `1920x919`.
7. Confirm no red `Viewport changed significantly` banner remains after a matching content-script viewport is available.
8. Run Smart Capture & Harvest and confirm recalibration is not required when the page viewport matches calibration.
