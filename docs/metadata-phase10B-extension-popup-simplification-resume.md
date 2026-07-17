# Phase 10B Popup Simplification Resume

## Implemented

- normal popup reduced to production actions only
- compact top status for backend/tab/session/calibration/probe/harvest
- legacy CDP/debug actions hidden by default
- start-harvest guard tightened around capture session, calibration, and probe `PASS`

## Key Files

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.ts`

## Expected Live Flow

1. Capture current page
2. Start Right Rail Calibration
3. Probe Current Modal Metrics
4. Start Full Modal Harvest

## Verification

- `npm run typecheck`: passed
- `npm test`: passed
- popup bundle/build: passed
