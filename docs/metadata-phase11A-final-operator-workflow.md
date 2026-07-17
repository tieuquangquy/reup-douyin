# Phase 11A Final Operator Workflow

## Normal popup buttons

1. Smart Capture & Harvest
2. Capture current page only
3. Start Right Rail Calibration
4. Show Calibration
5. Clear Calibration
6. Probe Current Modal Metrics
7. Resume Harvest
8. Stop Harvest
9. Flush Pending
10. Show Progress

Legacy CDP/debug actions remain hidden in normal mode.

## First-time workflow

1. Open Douyin profile page
2. Click `Capture current page only`
3. Open the first video modal
4. Click `Start Right Rail Calibration`
5. Click `Probe Current Modal Metrics`
6. When probe passes, click `Smart Capture & Harvest`

## Repeat workflow

If calibration already exists and viewport still matches:

1. Open profile
2. Open first modal
3. Probe
4. Smart Capture & Harvest

## Recalibration conditions

Recalibrate only when:

- viewport changes by more than 15%
- point reads fail
- layout changed
- browser zoom changed

If calibrated viewport equals current viewport, normal workflow should not block on recalibration.
