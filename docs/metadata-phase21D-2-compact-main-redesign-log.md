# Phase 21D-2 — Compact main redesign log

## Goal

Compress the popup main screen into a dense operator control surface for **Douyin Profile Scanner** while keeping the underlying scanner, collector, backend, and overlay flows unchanged.

## Scope used in this phase

This phase only changes popup presentation and popup-facing view-model formatting:

- compact hero panel
- compact health strip
- compact stats strip
- compact primary action panel
- compact settings row on the main screen
- compact bottom actions
- relocation validation for Results and Advanced overlays
- popup contract test updates

## Explicit non-goals

- no scanner/collector orchestration rewrite
- no backend/API contract change
- no state-machine redesign
- no Results workflow rewrite
- no Advanced workflow rewrite
- no Capture Inbox route change
- no queue persistence change

## Files touched

- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
- [`apps/extension-douyin-capture/public/popup.css`](apps/extension-douyin-capture/public/popup.css)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [`apps/extension-douyin-capture/src/ui20B1CommandCenterShell.test.ts`](apps/extension-douyin-capture/src/ui20B1CommandCenterShell.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts)
- [`apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts`](apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
- [`apps/extension-douyin-capture/src/extensionReset.test.ts`](apps/extension-douyin-capture/src/extensionReset.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.queueResults.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.queueResults.test.ts)

## Main-screen redesign outcome

The old stacked card-first layout was replaced with a compact control surface.

The main screen now contains:

- hero panel with title, status, and progress summary
- four-chip health strip
- one compact stats grid
- one primary action panel with inline alert
- one compact settings row for Mode, Batch, and Speed
- bottom action row for Capture Inbox, pause/resume, and reset

The main shell now uses compact contract identifiers such as:

- `scanner-hero`
- `scanner-health-strip`
- `scanner-stats-strip`
- `scannerStatsGrid`
- `scanner-primary-panel`
- `scanner-inline-alert`
- `scanner-settings-compact`
- `scanner-bottom-actions`

## View-model change

[`getDouyinScannerMainViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1122) now emits one merged compact stats block instead of separate profile/plan card summaries.

The compact mapping keeps existing state sources but reformats them into:

- `status_chips`
- `stats_summary`
- `primary_action`
- `progress`
- `footer_actions`
- `alert`

The stats subtitle was normalized to readable separators and the running label was normalized away from mojibake.

## Runtime wiring change

[`renderDouyinScannerMainScreen()`](apps/extension-douyin-capture/src/popup.ts:834) now renders the compact shell using the merged stats summary and the compact chip/grid structure.

Existing handlers were preserved for:

- primary action
- Results overlay opening
- Advanced overlay opening
- pause/resume
- reset
- settings persistence

## Results and Advanced placement

Main-screen-only detail density was reduced without removing operator access.

Kept behind overlays:

- Results dashboard and save flow in `deckPanelResults`
- queue preview and result lists in `deckPanelResults`
- API connection, harvest options, calibration, troubleshooting, safety tips, and maintenance/debug in `deckPanelAdvanced`

This preserves the local-first operator workflow while keeping the first screen compact.

## Test migration outcome

Updated popup contract tests now assert the compact surface and the removal of legacy main-screen classes/IDs.

This included updates to:

- [`wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [`ui20B1CommandCenterShell.test.ts`](apps/extension-douyin-capture/src/ui20B1CommandCenterShell.test.ts)
- [`wholeProfileHarvest.tabs.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts)
- [`ui20C1ActionDeck.test.ts`](apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts)
- [`wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
- [`extensionReset.test.ts`](apps/extension-douyin-capture/src/extensionReset.test.ts)
- [`wholeProfileHarvest.queueResults.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.queueResults.test.ts)

## Validation completed

Executed successfully:

- `npm --workspace @reup-douyin/extension-douyin-capture run test`

That run also completed the extension build and dist module resolution checks because they are chained inside the extension test script.

## Acceptance direction

This phase completes the hard compact replacement requested for the popup main screen:

1. compact first-screen control surface
2. old detail-heavy sections kept behind overlays
3. existing scanner/backend behavior preserved
4. updated tests aligned to the new UI contract
