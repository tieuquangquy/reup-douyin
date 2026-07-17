# Phase 13D Operator Workflow

## Purpose

This guide describes the corrected Douyin extension workflow after Phase 13D. The popup now separates profile-page capture from modal/video metric extraction so a profile page no longer incorrectly requires right-rail calibration.

## Correct Workflow

1. Open a supported Douyin profile page.
2. Open the extension popup.
3. Confirm diagnostics show `Page type: profile`.
4. Run `Capture current page` or `Smart Capture & Harvest`.
5. The extension captures the profile grid and creates a capture session.
6. If target videos exist, the popup asks the operator to open the first modal/video.
7. Open the target modal or direct video page.
8. Calibrate only when the popup is on a modal/video page and needs right-rail like/comment/favorite/share counts.
9. Probe the current modal after calibration.
10. Start or resume harvest after the modal probe passes.

## State Priority

The popup now prioritizes states in this order:

1. Backend unavailable.
2. Unsupported active tab.
3. Content script unavailable.
4. Detector unavailable.
5. Profile capture required.
6. Modal required.
7. Calibration required on modal/video pages.
8. Probe required on modal/video pages.
9. Harvest ready or harvest running state.

This means detector and content-script problems should show `Reconnect Douyin tab` instead of calibration guidance.

## Reconnect Douyin Tab

Use `Reconnect Douyin tab` when diagnostics show the content script or detector is unavailable.

The reconnect action performs:

1. Active tab URL validation.
2. Content-script ping with `REUP_DOUYIN_PING`.
3. `contentScript.js` injection when ping fails or forced reconnect is requested.
4. A second ping after injection.
5. Page-context detection with `REUP_DOUYIN_DETECT_PAGE_CONTEXT`.

After reconnect succeeds, diagnostics should show the detected page type and ready detector status.

## Diagnostics To Check

The popup operational summary should include:

- Page type.
- Content script status.
- Detector status.
- Capture session.
- Calibration.
- Current state.
- Next required action.

## Profile Page Expectations

On `https://www.douyin.com/user/...` without `modal_id`:

- Missing calibration should not block profile capture.
- Missing probe should not block profile capture.
- Stale modal probe PASS should not be reused.
- With no capture session, the current state should be `profile_capture_required`.
- With a capture session and harvest targets, the current state should be `modal_required`.

## Modal Or Video Page Expectations

On `https://www.douyin.com/user/...?modal_id=...` or `https://www.douyin.com/video/...`:

- Missing calibration may produce `calibration_required`.
- Partial calibration remains blocked until all four right-rail points are captured.
- Valid calibration with no current matching probe requires probing the current modal.
- A probe only counts when it matches the current modal/video aweme id and comes from calibrated point sources.

## Non-Goals

Phase 13D does not change backend APIs, web UI, metric extraction, the calibrated point concept, CDP/debug workflow, crawler behavior, queue implementation, or auto-publishing.
