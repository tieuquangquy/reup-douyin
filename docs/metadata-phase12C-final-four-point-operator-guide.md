# Phase 12C Final Four-Point Operator Guide

## Purpose

This guide is the live operator procedure for the restored Phase 12C Smart Capture & Harvest workflow. Production calibration is four points only: like, comment, favorite, and share.

## Build and reload

1. Run the extension build from the repository root:

   ```bash
   npm --workspace @reup-douyin/extension-douyin-capture run build
   ```

2. Open Chrome or Edge extension management.
3. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
4. Refresh the active Douyin tab after reloading the extension so the current content script is active.

## Normal live workflow

1. Open a supported Douyin profile page.
2. Open the extension popup.
3. Confirm the API base URL is correct for the local API service.
4. Click Capture current page or start Smart Capture & Harvest to establish an explicit capture session.
5. Click Start Right Rail Calibration.
6. Click exactly four right-rail metric points in this order:
   - like count
   - comment count
   - favorite count
   - share count
7. Do not click a next-video button as part of calibration.
8. Click Show Calibration and confirm:
   - status is calibrated/valid
   - version is `calibrated_four_point_workflow`
   - point count is `4/4`
   - viewport source is `content_script`
9. Open the first video modal on the profile.
10. Click Probe Current Modal Metrics.
11. Confirm the probe shows PASS and includes:
    - current modal aweme ID
    - video duration
    - like count
    - comment count
    - favorite count
    - share count
12. Click Smart Capture & Harvest or Resume Harvest.
13. Watch the progress panel confirm:
    - current video begins at Video 1
    - modal/aweme ID is shown
    - metrics are extracted
    - backend flush counts update
    - automatic navigation attempts move to the next modal item
14. Confirm progress advances from Video 1 to Video 2 after the modal ID changes.
15. Continue until the configured target count completes or the operator stops the harvest.

## Expected restored behavior

- Four calibrated metric points are enough for a valid calibration.
- Old valid four-point calibration can still be accepted.
- Smart Capture & Harvest does not require `next_video_button`.
- The popup does not show normal five-point calibration instructions.
- The normal workflow does not show “Next video point missing. Recalibrate with five points.”
- Probe PASS works from the four calibrated metric points.
- Harvest starts after a four-point PASS probe on an open modal.
- Automatic next-video navigation is attempted without a calibrated next point.
- `no_next_video` is only expected after real navigation attempts time out.

## Navigation behavior

After each modal item is harvested, the extension attempts automatic navigation using the available production fallbacks:

1. legacy calibrated next point if present from older saved state
2. DOM next control discovery
3. `ArrowDown`
4. `PageDown`
5. wheel scroll
6. focus page/video and retry `ArrowDown`

The harvest waits for the modal/aweme ID to change. If the modal ID changes, progress continues to the next item. If all attempts time out, the progress panel reports a navigation timeout and the operator can manually click next once, then click Resume Harvest.

## Troubleshooting

### Content script not ready

Refresh the Douyin tab, reopen the extension popup, then retry the action.

### Calibration missing or incomplete

Clear calibration and recalibrate exactly four metric points: like, comment, favorite, share. Do not include a next-video point.

### Probe does not PASS

Open a video modal and confirm all four calibrated points sit on visible numeric metric labels. Recalibrate if the page layout or browser viewport changed significantly.

### Automatic navigation times out

Manually click the next video once in the Douyin modal, wait for the modal ID to change, then click Resume Harvest. This timeout should happen only after real navigation attempts, not because a fifth calibration point is missing.

### Backend unavailable

Confirm the local API service is running and the extension API base URL is correct. Re-run Capture current page after the backend is reachable.

## Operator stop and resume

- Stop Harvest records an operator stop without changing the four-point calibration.
- Resume Harvest continues from persisted harvest state when the current modal is compatible with the saved workflow.
- If the page navigated manually during a timeout, Resume Harvest should continue from the new modal ID after it is detected.

## Production non-goals for Phase 12C

- No crawler implementation.
- No new extraction strategy.
- No backend contract rewrite.
- No required five-point calibration.
- No manual next click required for every video.
- No CDP/debug buttons as normal operator UI.
