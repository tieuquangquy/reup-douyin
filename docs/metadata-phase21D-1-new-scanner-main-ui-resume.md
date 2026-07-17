# Phase 21D-1 — New scanner main UI resume

## Objective

Phase 21D-1 replaces the popup main Run screen with a scanner-first UI for the **Douyin Profile Scanner** without changing the underlying collection workflow logic.

## What changed

### Main popup shell

The old deck-style main shell was replaced by scanner-specific markup in [`popup.html`](apps/extension-douyin-capture/public/popup.html).

The new main screen now presents:

- header status
- four connection chips
- profile scan summary card
- scan plan summary card
- one primary action card
- progress strip
- footer actions

### View-model

A new scanner main-screen mapper was added at [`getDouyinScannerMainViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1127).

It derives:

- status chip tone/value
- profile summary metrics
- plan summary metrics
- primary action label and enablement
- progress label/value/detail
- footer action visibility
- warning/error/info alert state

### Popup runtime

The main renderer now calls [`renderDouyinScannerMainScreen()`](apps/extension-douyin-capture/src/popup.ts:836).

Scanner buttons reuse existing flows for:

- primary action
- pause/resume
- reset
- Results overlay opening
- Advanced overlay opening

### CSS

The main popup surface now uses `scanner-` prefixed styles in [`popup.css`](apps/extension-douyin-capture/public/popup.css).

Overlay panel styling for Results and Advanced remains under `deck-panel` because those panels were intentionally retained.

### Tests

[`wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts) was updated toward:

- scanner main view-model assertions
- scanner popup markup assertions
- scanner CSS assertions
- scanner popup runtime wiring assertions
- removal checks for old main-screen deck shell elements

## Important preserved behavior

- existing whole-profile readiness logic remains the action source
- existing collection/save handlers remain the runtime source
- existing Results content remains available
- existing Advanced content remains available
- review destination remains Capture Inbox
- no new review route was introduced

## Known implementation intent

The main screen should feel product-facing and minimal.

Technical details that still exist for operator safety and debugging should stay behind Results or Advanced rather than dominating the first screen.

## Route decision preserved

Review remains on the existing Capture Inbox surface from Phase 21A:

- [`/extensions/douyin/capture-inbox`](docs/metadata-phase21D-1-new-scanner-main-ui-resume.md:1)

## Remaining validation work after this phase file

Before considering the phase fully closed, validate:

- extension tests
- extension typecheck
- extension build
- main-screen absence of old deck UI
- correct pause/resume behavior in the popup
- scanner styling and overlay behavior in the live popup
