# Phase 12B Calibration Persistence Fix Log

## Scope

Phase 12B was limited to `apps/extension-douyin-capture` calibration persistence/state behavior plus extension tests and docs.

Non-goals preserved:

- No backend changes.
- No web app changes.
- No CDP/debug workflow reintroduction.
- No harvest endpoint changes.
- No broad metric extraction changes.

## Root Cause

The content script already saved Phase 12A five-point calibration under the canonical local storage key, but the popup-side calibration reader still accepted only the legacy `phase10a` calibration version. As a result, a newly saved `phase12a_calibrated_five_point_workflow` calibration was displayed as missing by the popup.

A second state bug allowed a previously stored `douyinLastProbeResult` PASS to remain visible even when calibration was missing or no longer valid. That produced the inconsistent operator state: `Calibration: missing` with `Last probe: PASS`.

## Changes

### Canonical storage contract

The canonical calibration storage key remains:

```text
douyinRightRailCalibration
```

The popup and content script now read/write/delete calibration through this key consistently.

### Five-point calibration persistence

The content-script calibration overlay records all five required points:

1. LIKE count
2. COMMENT count
3. FAVORITE count
4. SHARE count
5. NEXT video button / down arrow

The saved shape now includes the content-script viewport source:

```json
{
  "version": "phase12a_calibrated_five_point_workflow",
  "viewport_width": 1920,
  "viewport_height": 919,
  "viewport_source": "content_script",
  "points": {
    "like_count": {},
    "comment_count": {},
    "favorite_count": {},
    "share_count": {},
    "next_video_button": {}
  }
}
```

### Validation

Added `validateRightRailCalibration()` with statuses:

- `missing`: no usable calibration or no usable points/viewport.
- `partial`: calibration has usable viewport and at least one point, but not all five points.
- `valid`: viewport exists and all five required points have numeric `x`, `y`, `x_ratio`, and `y_ratio`.

Old four-point calibration is now `partial`, not fully calibrated for Smart Capture & Harvest.

### Stale probe handling

If calibration is missing or not valid, the popup ignores and clears `douyinLastProbeResult`. A stale PASS can no longer satisfy Smart Capture & Harvest when calibration is missing or partial.

### Popup observability

Show Calibration now displays:

- calibration status
- validation status
- point count
- version
- calibration viewport
- viewport source
- all five point coordinates/ratios
- next action

Start Calibration now re-reads storage after content-script save and fails visibly if the content script is unavailable or calibration is incomplete.

## Tests

Updated extension workflow tests to cover:

- Phase 12A calibration version accepted by popup readers.
- Five-point validation passes.
- Four-point validation is partial.
- Smart Capture blocks partial/four-point calibration with the next-point missing message.
- Missing calibration clears stale probe status in reconciled smart state.
- Popup source uses canonical calibration key reads.
- Content script saves five-click calibration with viewport source.
- Start Calibration sends the content-script calibration message.
- Show Calibration displays five-point count.
- `content_script_not_ready` and `calibration_incomplete` are observable error strings.

## Verification

Ran during implementation:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Both passed after fixes. Final verification commands are recorded in the final report.
