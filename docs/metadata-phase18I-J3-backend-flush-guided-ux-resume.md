# Phase 18I-J3 Backend Flush Guided UX Resume

## Outcome

Backend Flush in the Whole Profile Harvest popup is now presented as a guided four-step flow instead of a loose collection of buttons.

## Final flow

1. Prepare Backend Session
2. Build Payload Preview
3. Flush One Item
4. Flush Batch

## Key behavior

- Each step exposes:
  - status chip
  - short summary
  - enable/disable state
  - disabled reason
- Batch flush is blocked by default until one-item flush succeeds.
- Guard failures surface compact offending paths in the main backend card and move full details into Details.

## Files touched

- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.backendFlow.test.ts`

## Test commands

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Follow-up

Next UX iteration should focus on making backend failures more operator-readable without expanding the main popup height again.
