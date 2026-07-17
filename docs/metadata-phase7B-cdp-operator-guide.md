# Phase 7B CDP Operator Guide

## Goal

Use Chrome Debugger Protocol capture before Douyin loads modal/video metadata so the extension can read exact aweme JSON instead of relying on visual DOM fallback metrics.

## Preferred Workflow

1. Open a supported Douyin profile tab.
2. Open the extension popup.
3. Click `Attach CDP to Current Douyin Tab`.
4. Confirm `Show CDP Status` reports:
   - `CDP attached = yes`
   - `Network enabled = yes`
   - `Runtime enabled = yes`
5. Open a video modal or move to the next video.
6. Click `Probe Current Modal via CDP`.
7. Start full modal harvest only when probe status is `PASS`.

## Already Open Modal Workflow

1. Keep the modal URL open.
2. Click `Attach CDP and Refresh Current Modal`.
3. The extension attaches CDP, reloads the current URL, waits for Douyin responses, and probes after reload.
4. Review the probe diagnostics.

## Diagnostics To Check

CDP status should show:

- `CDP attached`
- `Attached tab id`
- `Debugger version`
- `Network enabled`
- `Runtime enabled`
- `CDP response count`
- `CDP JSON response count`
- `CDP aweme candidates`
- `CDP exact matches`
- `Runtime exact matches`
- `Last matching aweme`
- `Last matching response URL`
- `CDP last error`

Probe diagnostics should show:

- `Probe source used`
- `Probe exact aweme found`
- `Probe raw aweme keys`
- `Probe duration seconds`
- `Probe like`, `Probe comment`, `Probe favorite`, `Probe share`
- CDP response and exact-match counters

## Interpreting Results

- `PASS`: Exact CDP/page-cache aweme source found and all required metrics exist.
- `WARN`: DOM fallback, partial metrics, or CDP attached but exact aweme not found. Normal full harvest is blocked; attach before opening video or refresh/next video.
- `FAIL`: Missing aweme id, missing duration, or debugger attach/probe failure.

## Safety Notes

The extension does not bypass captcha, does not use backend browser crawling, and does not fake metrics. CDP attachment is local to the operator's active browser tab and can be removed with `Detach CDP`.
