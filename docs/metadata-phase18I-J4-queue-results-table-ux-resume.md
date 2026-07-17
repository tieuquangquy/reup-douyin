# Phase 18I-J4 Queue / Results Table UX Resume

## Outcome

Whole Profile Harvest popup now renders queue preview and recent results as compact row tables instead of plain text blobs.

## Main UI behavior

- Queue Preview appears as a compact list after targets exist
- Recent Extraction Results appears once extraction results exist
- Recent Backend Results appears once backend flush results exist
- Each section shows only 5 rows in the main panel and uses `+N more`

## Details behavior

Details now keeps:

- Full Queue
- Full Extraction Results
- Full Backend Results

These remain readable row tables instead of raw JSON.

## Files touched

- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.queueResults.test.ts`
- `apps/extension-douyin-capture/package.json`

## Test commands

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Follow-up

Next UX iteration should focus on summarizing per-row backend verification outcomes more clearly without adding extra popup height.
