# Phase 12B Calibration Operator Guide

## Purpose

Use this guide to retest Right Rail Calibration after the Phase 12B persistence and stale-probe fix.

## Expected healthy state

After a successful five-click calibration, the popup should show:

- `Calibration: calibrated`
- `Calibrated viewport: <width>x<height>`
- `Current page viewport: <width>x<height>`
- `Viewport source: content_script`
- `Viewport warning: none`
- `Last probe: none`, `stale`, or `PASS` only after a current modal probe

The popup must not show `Calibration: missing` with `Last probe: PASS`.

## Calibration steps

1. Reload the unpacked extension build.
2. Refresh the active Douyin tab so the content script is current.
3. Open a Douyin profile and open the first video modal.
4. Open the extension popup.
5. Click `Clear Calibration` if you need a clean retest.
6. Click `Start Right Rail Calibration`.
7. In the page overlay, click the requested targets in order:
   1. LIKE count
   2. COMMENT count
   3. FAVORITE count
   4. SHARE count
   5. NEXT video button / down arrow
8. After the fifth click, the popup should refresh and show calibrated status.
9. Click `Show Calibration` and confirm:
   - `Validation status: valid`
   - `Point count: 5/5`
   - version is `phase12a_calibrated_five_point_workflow`
   - viewport source is `content_script`
   - all five point rows are populated

## Probe and harvest steps

1. With the current modal open, click `Probe Current Modal Metrics`.
2. Confirm the probe result is for the current `modal_id`.
3. Confirm metrics are populated from calibrated point sources.
4. Click `Smart Capture & Harvest`.
5. The workflow should not stop at calibration required when Show Calibration reports `valid` and `5/5`.

## Error meanings

### `content_script_not_ready`

The popup could not reach the Douyin tab content script.

Operator action:

1. Refresh the Douyin tab.
2. Reopen the popup.
3. Click `Start Right Rail Calibration` again.

### `calibration_incomplete`

The calibration was cancelled or did not complete all five points.

Operator action:

1. Click `Start Right Rail Calibration` again.
2. Complete all five overlay clicks.

### `Next video point missing. Recalibrate with five points.`

An old four-point calibration exists. Manual probing may still be possible, but Smart Capture & Harvest requires the fifth next-video point.

Operator action:

1. Click `Clear Calibration`.
2. Run Start Right Rail Calibration and complete all five points.

## Storage contract

Canonical calibration key:

```text
douyinRightRailCalibration
```

Probe key cleared when calibration is missing or partial:

```text
douyinLastProbeResult
```
