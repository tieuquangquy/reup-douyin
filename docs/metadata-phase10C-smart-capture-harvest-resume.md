# Phase 10C Smart Capture & Harvest Resume

## Implemented

- primary popup action: `Smart Capture & Harvest`
- smart state persisted in extension local storage
- explicit harvest session binding from capture into harvest start/resume
- top popup status now shows smart workflow state and next required action

## Workflow Summary

1. capture profile page if no reusable capture state exists
2. require calibration
3. require open modal
4. run calibrated probe
5. start full-modal harvest with explicit `capture_session_id`
6. flush and progress remain resumable

## Safe Stop Conditions

- calibration missing
- modal missing
- probe not `PASS`
- viewport changed significantly
- captcha/login wall during harvest
- backend flush failure

## Verification

- `npm run typecheck`: passed
- `npm test`: passed
- build/dist resolution: passed
