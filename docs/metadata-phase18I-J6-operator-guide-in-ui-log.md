# metadata-phase18I-J6-operator-guide-in-ui-log.md

## Step
- Phase 18I-J6 only: add an in-popup operator guide, contextual help/tooltips, and quick troubleshooting hints for the whole-profile popup UI in [`apps/extension-douyin-capture`](apps/extension-douyin-capture).

## Time Started
- 2026-05-06 (UTC)

## Scope
- Allowed:
  - whole-profile popup markup in [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
  - popup styling in [`apps/extension-douyin-capture/public/popup.css`](apps/extension-douyin-capture/public/popup.css)
  - whole-profile help/view-model wiring in [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
  - popup rendering/state wiring in [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
  - targeted extension tests in [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts) and [`apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
- Explicit non-goals:
  - no scanner logic changes
  - no dry-run logic changes
  - no extraction logic changes
  - no backend flush logic changes
  - no payload guard contract changes
  - no backend calls during render
  - no new V2 or legacy state dependency for help UI
  - no large popup docs dump

## Findings
- The whole-profile popup already had stable rendering entry points in [`renderWholeProfileHarvestProductState()`](apps/extension-douyin-capture/src/popup.ts:424) and [`renderWholeProfileHarvestProgressView()`](apps/extension-douyin-capture/src/popup.ts:732).
- Existing canonical readiness/action computation in [`getWholeProfileHarvestReadiness()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:1) and [`getWholeProfileHarvestActionState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:245) could drive operator-facing hints without changing workflow logic.
- The popup already separated UI rendering from controller operations, so J6 could stay UI-only by extending [`getWholeProfileHarvestProgressViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:688).
- No existing popup-local preference key covered collapsible help panels, so J6 required isolated local storage state in [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts).

## Changes Made
- Added in-popup guide panels and helper surfaces in [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html):
  - Quick Start panel
  - disabled reason helper line
  - field help badges for mode/batch/speed
  - troubleshooting panel
  - Capture Inbox CTA helper line
  - safety tips panel
- Added popup-safe guide styling in [`apps/extension-douyin-capture/public/popup.css`](apps/extension-douyin-capture/public/popup.css):
  - [`operator-guide`](apps/extension-douyin-capture/public/popup.css)
  - [`field-help`](apps/extension-douyin-capture/public/popup.css)
  - [`helper--warning`](apps/extension-douyin-capture/public/popup.css)
  - [`helper--success`](apps/extension-douyin-capture/public/popup.css)
- Extended [`WholeProfileHarvestProgressViewModel`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:151) with operator-help content and added [`getActionHelpText()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:190) for contextual action guidance.
- Wired popup rendering in [`renderWholeProfileHarvestActionState()`](apps/extension-douyin-capture/src/popup.ts:514) to:
  - surface a single disabled reason
  - update contextual help text
  - set `title` help on action buttons and options
- Added popup-only collapsed panel preferences in [`readWholeProfileHarvestUiPrefs()`](apps/extension-douyin-capture/src/popup.ts:277), [`syncWholeProfileGuidePrefsFromDom()`](apps/extension-douyin-capture/src/popup.ts:293), and [`applyWholeProfileGuidePrefs()`](apps/extension-douyin-capture/src/popup.ts:301).
- Expanded tests in [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts) and [`apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts) to cover guide surfaces, wording, local prefs wiring, disabled-reason helper presence, and no legacy runtime coupling.

## Verification Plan
- Run extension tests for whole-profile popup coverage.
- Run extension typecheck to catch popup/view-model contract mismatches.
- Run extension build to confirm popup bundle still compiles.

## Status
- Implementation complete.
- Tests updated.
- Validation pending.
