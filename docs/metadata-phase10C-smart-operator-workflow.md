# Phase 10C Smart Operator Workflow

## First-Time Workflow

1. Open the Douyin profile page.
2. Click `Smart Capture & Harvest`.
3. If prompted, run `Start Right Rail Calibration`.
4. Open the first video modal when prompted.
5. Click `Smart Capture & Harvest` again.
6. The popup runs calibrated probe and starts harvest with the explicit capture session.

## Repeat Workflow After Calibration Exists

1. Open the profile page.
2. Click `Smart Capture & Harvest`.
3. Open the first modal if requested.
4. Click `Smart Capture & Harvest` again if the workflow paused at `modal_required`.

## Session Binding

The popup binds harvest to the latest explicit capture session created by the smart capture step.

That binding is passed into harvest start/resume so backend updates stay tied to the intended capture session.

## Start / Stop / Resume

- `Resume Harvest` resumes a paused harvest with the saved capture session binding.
- `Stop Harvest` pauses safely.
- `Flush Pending` retries pending writes without losing buffered harvested items.
- `Show Progress` refreshes the current smart/harvest state.

## Tests Run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`

## Live Retest Steps

1. `cd apps/extension-douyin-capture`
2. `npm run build`
3. Reload the unpacked extension.
4. Open a Douyin profile page.
5. Click `Smart Capture & Harvest`.
6. Follow popup next-step guidance for calibration or modal opening.
7. Reclick `Smart Capture & Harvest` if it paused at calibration or modal requirement.
8. Use `Show Progress` and `Flush Pending` during or after harvest.
