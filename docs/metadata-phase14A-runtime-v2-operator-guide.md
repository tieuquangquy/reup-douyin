# Phase 14A Runtime V2 Operator Guide

## Final operator flow

1. Capture current page.
2. Calibrate right rail.
3. Probe current modal.
4. Start `Smart Capture & Harvest`.
5. Use `Show Progress` to monitor runtime V2.
6. Use `Stop Harvest` only for intentional operator pause.
7. Use `Resume Harvest` to continue the same run.

## What changed operationally

- Harvest no longer depends on popup staying open.
- Successful item processing never produces `Resume Harvest`.
- Only real pause/fail conditions stop the loop.

## Live retest steps

1. `npm --workspace @reup-douyin/extension-douyin-capture run build`
2. Reload the unpacked extension.
3. Open a supported Douyin modal page with valid calibration.
4. Click `Smart Capture & Harvest`.
5. Confirm after video #1:
   - header says `Harvest running`
   - progress panel says `Harvest running`
   - target index advances from `1 / N` to `2 / N`
6. Click `Stop Harvest`.
7. Confirm:
   - status `paused`
   - pause reason `operator_stop`
   - next action `Resume Harvest`
8. Click `Resume Harvest`.
9. Confirm it continues through multiple targets until completion or a real pause reason.
