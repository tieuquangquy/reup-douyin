# Phase 19B Compact Dashboard UI Log

## Scope
- Task: Phase 19B only.
- Surface: [`popup.html`](apps/extension-douyin-capture/public/popup.html), [`popup.css`](apps/extension-douyin-capture/public/popup.css), [`popup.ts`](apps/extension-douyin-capture/src/popup.ts), and related popup tests under [`apps/extension-douyin-capture/src`](apps/extension-douyin-capture/src).
- Goal: redesign the Douyin Profile Harvester popup into a compact professional dashboard where Run stays compact, while Results and Technical contain the rest.

## What Changed
- Rebuilt the popup information architecture in [`popup.html`](apps/extension-douyin-capture/public/popup.html) into three tabs:
  - Run
  - Results
  - Technical
- Kept Run focused on compact operator actions only:
  - header status chips
  - workflow stepper
  - one primary action card
  - compact harvest settings
  - small metrics and shortcuts
- Moved queue, extraction, backend/save flow, and save outcomes into Results.
- Moved API/configuration, calibration, technical details, troubleshooting, safety guidance, and debug tools into Technical.
- Preserved the quick-start guide DOM node for local UI preference compatibility, but hid it in compact Run rendering from [`renderWholeProfileHarvestProductState()`](apps/extension-douyin-capture/src/popup.ts:463).

## Implementation Notes
- [`popup.html`](apps/extension-douyin-capture/public/popup.html)
  - Added compact dashboard header and tabbed layout.
  - Introduced `Run Dashboard` heading and short workflow hint area.
  - Removed the old standalone Controls section from the Run tab.
  - Renamed backend outcome wording to `Recent Save Results` in Results.
- [`popup.css`](apps/extension-douyin-capture/public/popup.css)
  - Added compact layout styling for header, section heading rows, primary action card, compact settings card, compact secondary actions, and Results backend flow.
  - Added narrow-width fallback behavior for the dashboard layout.
- [`popup.ts`](apps/extension-douyin-capture/src/popup.ts)
  - Preserved existing harvesting logic and tab-switch persistence behavior.
  - Forced the hidden quick-start guide closed while continuing to show the short hint text.
- Tests updated:
  - [`wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
  - [`popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts)
  - [`wholeProfileHarvest.tabs.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts)
  - [`wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)

## Non-Goals Preserved
- No harvester logic changes.
- No extraction pipeline changes.
- No save API contract changes.
- No backend workflow semantics changed.
- Tab changes remain local popup UI state only.

## Verification
- Ran [`npm --workspace @reup-douyin/extension-douyin-capture run test`](package.json).
- Phase 19B popup-related tests passed, including:
  - [`wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
  - [`wholeProfileHarvest.tabs.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts)
  - [`wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
  - [`popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts)
