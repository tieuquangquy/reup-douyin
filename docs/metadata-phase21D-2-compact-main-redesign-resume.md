# Phase 21D-2 — Compact main redesign resume

## Objective

Phase 21D-2 converts the popup main screen into a compact scanner-first operator surface without changing scanner logic, collection logic, or backend behavior.

## What changed

### Main popup shell

[`popup.html`](apps/extension-douyin-capture/public/popup.html) now renders a compact structure instead of the previous vertical card stack.

The main screen now presents:

- compact hero with title, status, and progress
- compact health strip
- compact stats strip
- compact primary action panel
- compact settings row
- compact bottom actions

### CSS contract

[`popup.css`](apps/extension-douyin-capture/public/popup.css) now styles the compact surface with scanner-prefixed compact classes such as:

- `scanner-hero`
- `scanner-health-strip`
- `scanner-stats-grid`
- `scanner-primary-panel`
- `scanner-inline-alert`
- `scanner-settings-compact__row`
- `scanner-bottom-actions`

Legacy main-screen classes like the old header/card/footer stack are no longer the active contract for the main shell.

### View-model

[`getDouyinScannerMainViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1122) now exposes a merged [`stats_summary`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1220) instead of separate profile/plan summary blocks.

It still derives data from the same readiness and state sources, but formats it for the compact UI.

### Popup renderer

[`renderDouyinScannerMainScreen()`](apps/extension-douyin-capture/src/popup.ts:834) was updated to:

- render compact health chips
- render the merged compact stats grid
- keep the same primary-action orchestration
- keep the same settings persistence wiring
- keep Results and Advanced overlay switching

### Overlay boundaries preserved

Results and Advanced remain the places for secondary information.

Results overlay still contains:

- backend flow
- queue preview
- extraction results
- backend results

Advanced overlay still contains:

- API controls
- harvest options/safety controls
- calibration controls
- progress details
- troubleshooting guidance
- safety tips
- maintenance/debug actions

## Tests updated

The compact redesign required updating popup contract tests that still expected the removed stacked layout.

Updated tests include:

- [`wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [`ui20B1CommandCenterShell.test.ts`](apps/extension-douyin-capture/src/ui20B1CommandCenterShell.test.ts)
- [`wholeProfileHarvest.tabs.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts)
- [`ui20C1ActionDeck.test.ts`](apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts)
- [`wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
- [`extensionReset.test.ts`](apps/extension-douyin-capture/src/extensionReset.test.ts)
- [`wholeProfileHarvest.queueResults.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.queueResults.test.ts)

## Validation status

Validated via [`npm --workspace @reup-douyin/extension-douyin-capture run test`](docs/metadata-phase21D-2-compact-main-redesign-resume.md:1).

That script completed:

- extension tests
- extension build
- dist module resolution check

## Important preserved behavior

- no scanner/backend workflow rewrite
- no new route introduced
- no main-screen return to stacked cards
- Results and Advanced remain overlay-driven
- existing button handlers and persistence flows remain in place

## Closeout note

Phase 21D-2 is ready for handoff as the compact popup main-screen replacement with passing extension validation.
