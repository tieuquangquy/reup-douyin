# Phase 10B Operator Workflow

## Normal Popup Workflow

### Section 1: Capture

- `Capture current page`

Run this first to create or refresh the Capture Inbox session.

### Section 2: Calibration

- `Start Right Rail Calibration`
- `Probe Current Modal Metrics`
- `Show Calibration`
- `Clear Calibration`

Calibrate once by clicking:

1. like
2. comment
3. favorite
4. share

Recalibrate if viewport, zoom, or Douyin layout changes.

### Section 3: Harvest

- `Start Full Modal Harvest`
- `Resume Full Modal Harvest`
- `Stop Full Modal Harvest`
- `Flush Harvested Metadata`
- `Show Harvest Progress`

Run harvest only after Probe reports `PASS`.

## Hidden Legacy Actions

The popup no longer shows CDP/debug actions in normal operator mode.

## Harvest Start Guard

The popup blocks harvest start when:

- capture session is missing
- calibration is missing
- probe is missing or not `PASS`

## Tests Run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`

## Verification Result

- `npm run typecheck`: passed
- `npm test`: passed
- popup bundle/build: passed
