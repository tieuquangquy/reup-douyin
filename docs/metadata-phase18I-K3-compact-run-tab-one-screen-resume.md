# Phase 18I-K3 Compact Run Tab One-Screen Resume

## Scope completed

`Run` tab was compacted into a near-one-screen operator layout without changing harvest logic.

## Key changes

- added dedicated `getRunTabViewModel(...)`
- replaced tall run-tab summaries with compact mini metrics
- hid Quick Start after profile scan
- moved queue/results emphasis to `Results`
- kept raw/debug data in `Technical`
- added `View Results` and `Technical Details` shortcuts

## Files changed

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts`

## Verification commands

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
