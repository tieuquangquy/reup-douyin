# Phase 21D-9 Scan, Calibration, and Reset Fix Resume

## Phase

21D-9 — Fix Scan/Profile priority, calibration readiness, and Reset button

## Completed changes

- Changed scanner action priority so `Scan Profile` is the first primary action when no usable profile scan exists.
- Kept `Scan Profile` as the primary action after a scan when classification has not succeeded yet.
- Delayed `Calibrate 4 Points` until there is a classified queue with videos to collect.
- Kept `Start Collecting` gated by both queued videos and calibration readiness.
- Kept `Open Capture Inbox` for classified no-eligible-video states.
- Added canonical calibration readiness detection across status, alternate status, ready flag, point count, and stored four-point objects.
- Updated calibration completion to persist calibrated whole-profile scanner state and re-render the scanner popup immediately.
- Updated reset to clear scanner workflow progress while preserving calibration.
- Updated static popup fallback copy so the initial primary action is `Scan Profile`.
- Added and updated tests for action priority, calibration readiness, stored four-point readiness, popup fallback copy, primary action routing, and reset clearing behavior.

## Explicit non-goals preserved

- No backend contract changes.
- No crawler implementation changes.
- No video extractor implementation changes.
- No scanner/backend classification logic redesign.
- No UI redesign beyond required copy and action fallback alignment.
- No reset behavior that clears calibration by default.

## Validation status

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual retest focus

1. Open the extension popup on a Douyin profile page with no scanner workflow state.
2. Confirm the hero reads `No profile · API not checked · Cal needed · Safe` or equivalent current runtime chip values.
3. Confirm the primary action title, description, and button all show `Scan Profile`.
4. Click `Scan Profile` and confirm calibration is not requested before the scan/classification workflow.
5. After a classified queue exists with videos and calibration missing, confirm the primary action changes to `Calibrate 4 Points`.
6. Complete four-point calibration and confirm the popup immediately changes to `Cal ready`.
7. Confirm a queued calibrated state shows `Start Collecting`.
8. Confirm running collection shows `Pause`, and paused collection shows `Resume`.
9. Confirm a classified state with no eligible videos shows `Open Capture Inbox`.
10. Click `Reset` and confirm the scanner returns to the scan-ready state while calibration remains preserved.
