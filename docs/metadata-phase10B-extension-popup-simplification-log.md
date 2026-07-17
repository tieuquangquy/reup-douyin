# Phase 10B Popup Simplification Log

## Scope

- App: `apps/extension-douyin-capture`
- Goal: simplify the normal popup workflow around capture, calibrated-point probe, and full modal harvest
- Non-goals:
  - backend changes
  - reintroducing CDP/global DOM extraction as normal PASS sources
  - changing flush/resume safety

## Root Cause

The popup kept exposing obsolete CDP and debug actions from earlier failed extraction strategies. That cluttered the operator path and made it too easy to use workflows that are no longer production-valid.

## Final Operator Workflow

1. Capture current page
2. Start Right Rail Calibration
3. Probe Current Modal Metrics
4. Start Full Modal Harvest
5. Resume / Stop / Flush / Show Harvest Progress as needed

## Buttons Kept

- Capture current page
- Start Right Rail Calibration
- Show Calibration
- Clear Calibration
- Probe Current Modal Metrics
- Start Full Modal Harvest
- Resume Full Modal Harvest
- Stop Full Modal Harvest
- Flush Harvested Metadata
- Show Harvest Progress

## Buttons Hidden From Normal UI

- Detect current page
- Attach CDP to Current Douyin Tab
- Detach CDP
- Show CDP Status
- Probe Current Modal via CDP
- Attach CDP and Refresh Current Modal

These are now legacy/debug-only in the popup layout and hidden by default.

## Harvest Start Guard

Start Full Modal Harvest is blocked unless:

1. capture session exists
2. calibration exists
3. last probe status is `PASS`

## Tests Run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`

## Verification Result

- `npm run typecheck`: passed
- `npm test`: passed
- popup build completed and static files copied into `dist`
