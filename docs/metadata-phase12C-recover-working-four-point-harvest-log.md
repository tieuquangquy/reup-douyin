# Phase 12C Recover Working Four-Point Harvest Log

## Scope

Phase 12C restored the last known working local-first extension workflow:

- Four-point right rail calibration only: like, comment, favorite, share.
- Smart Capture & Harvest no longer requires a calibrated next-video point.
- Automatic next-video navigation is used after each harvested modal item.
- Existing capture session binding, backend flush, progress UI, calibrated metric extraction, and no-normal-CDP/debug UI behavior were preserved.

No backend or broad web changes were made.

## Git/history audit result

The workspace command `git status --short && git diff -- apps/extension-douyin-capture && git log --oneline --decorate -- apps/extension-douyin-capture && git reflog --date=iso` failed because the current directory was not recognized as a Git repository. Because Git history was unavailable, the audit used current source, tests, and Phase 12A/12B docs to identify exact regression points.

## Exact regression root cause

The regression was caused by Phase 12A/12B production code turning an optional next-video coordinate into a required fifth calibration point:

1. `contentScript.startRightRailCalibration()` changed the operator overlay from four clicks to five clicks and saved `phase12a_calibrated_five_point_workflow`.
2. `popupWorkflow.validateRightRailCalibration()` counted `next_video_button` as required, so old working four-point calibration became `partial` instead of valid.
3. `popup.ts` Smart Capture paths paused with calibration-required state when the only missing point was `next_video_button`.
4. `contentScript.startFullModalHarvest()` and `contentScript.resumeFullModalHarvest()` hard-failed harvest start/resume when `calibration.points.next_video_button` was absent.
5. `FullModalHarvestController.navigateAfterItem()` returned `no_next_point_calibrated` before trying automatic navigation.
6. Tests locked in the regression by asserting that four-point calibration should fail with “Next video point missing”.

## Changes made

### Calibration contract

- Added production version `calibrated_four_point_workflow`.
- Kept compatibility with old `phase10a`, `phase11g_calibrated_points_with_next`, and `phase12a_calibrated_five_point_workflow` stored objects.
- Required validation points are now only:
  - `like_count`
  - `comment_count`
  - `favorite_count`
  - `share_count`
- `next_video_button` remains type-compatible as an optional legacy/debug coordinate, but it is not required for production validity.

### Popup and Smart Capture guard

- Four-point calibration validates as `valid`.
- Old four-point calibration validates as `valid`.
- Popup text now instructs: click like, comment, favorite, share.
- Show Calibration displays point count `4/4` and no longer shows a normal production next-video point row.
- Normal workflow no longer emits “Next video point missing. Recalibrate with five points.”
- Stale probe clearing remains tied to calibration validity.

### Harvest start/resume

- Removed start/resume hard blocks that required `calibration.points.next_video_button`.
- Probe still requires PASS using current modal ID, active video duration, and four calibrated metric points.
- Capture session binding and backend flush behavior were preserved.

### Navigation

- `FullModalHarvestController.navigateAfterItem()` no longer stops early on missing `next_video_button`.
- Navigation now attempts automatic next behavior in this order:
  1. legacy calibrated next point if present, otherwise existing modal next control discovery,
  2. ArrowDown,
  3. PageDown,
  4. wheel scroll down,
  5. focus active video/page and ArrowDown again.
- Harvest waits for modal/aweme ID change.
- `no_next_video` is only applied after real navigation timeout, not because the fifth point is missing.
- Resume remains available after timeout.

## Tests updated

- Four-point calibration validates as calibrated.
- Old four-point calibration validates as calibrated.
- Smart Capture guard does not require `next_video_button`.
- Normal popup/source tests reject the removed five-point production message.
- Probe PASS continues to work with four calibrated points.
- Navigation without a calibrated next point now attempts automatic navigation and only returns timeout after attempts.
- Progress UI copy no longer instructs five-point recalibration.

## Verification

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

The `test` script also runs the extension build and dist module resolution check.
