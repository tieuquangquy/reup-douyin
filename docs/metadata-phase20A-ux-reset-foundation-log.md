# Phase 20A UX Reset Foundation Log

## Scope
- Task: Phase 20A only.
- Surface: [`popup.html`](apps/extension-douyin-capture/public/popup.html), [`popup.css`](apps/extension-douyin-capture/public/popup.css), [`popup.ts`](apps/extension-douyin-capture/src/popup.ts), popup test files under [`apps/extension-douyin-capture/src`](apps/extension-douyin-capture/src), and supporting notes in [`docs`](docs).
- Goal: reset the Douyin Profile Harvester popup UX foundation into an operator dashboard with clear `Run` / `Results` / `Advanced` information architecture, standardized design tokens, and reduced non-core clutter in the main flow.

## What Changed
- Rebuilt the popup structure in [`popup.html`](apps/extension-douyin-capture/public/popup.html) around three top-level tabs:
  - Run
  - Results
  - Advanced
- Kept the Run tab focused on the core operator sequence:
  - Scan Profile
  - Test 3 Videos
  - Extract Metrics
  - Save to Capture Inbox
- Moved queue preview, extraction results, backend save flow, and recent save outcomes into Results.
- Moved connection settings, calibration, detailed diagnostics, troubleshooting, safety tips, raw state, and advanced test controls into Advanced.
- Preserved existing handler compatibility where useful, including the existing [`#wholeProfileOpenTechnicalButton`](apps/extension-douyin-capture/public/popup.html) id while changing visible wording to `Advanced`.

## Styling Foundation
- Added/standardized popup design tokens in [`popup.css`](apps/extension-douyin-capture/public/popup.css):
  - surface/background tokens
  - text/muted tokens
  - semantic status colors
  - spacing tokens
  - radius tokens
- Standardized button variants in [`popup.css`](apps/extension-douyin-capture/public/popup.css):
  - primary
  - secondary
  - warning
  - danger
  - ghost
  - disabled
- Kept the popup width stable while improving compact dashboard layout behavior.

## Wiring And Compatibility
- Updated tab state handling in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts) from `technical` to `advanced` in [`WholeProfileHarvestUiPrefs`](apps/extension-douyin-capture/src/popup.ts:272), [`applyWholeProfileActiveTab()`](apps/extension-douyin-capture/src/popup.ts:323), and [`setWholeProfileActiveTab()`](apps/extension-douyin-capture/src/popup.ts:338).
- Renamed DOM references in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts) to `wholeProfileTabAdvancedButton`, `wholeProfileTabAdvancedPanelEl`, and `wholeProfileOpenAdvancedButton` while preserving behavior.
- Kept the hidden quick-start DOM node for local UI preference compatibility and continued forcing it closed in compact Run rendering.
- Updated run-tab alert wording in [`getRunTabViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:756) so operator guidance now points to `Advanced` instead of `Technical`.

## Tests Updated
- Updated static popup IA and wording assertions in:
  - [`wholeProfileHarvest.tabs.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts)
  - [`wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-couyin-capture/src/wholeProfileHarvest.wording.test.ts)
  - [`wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
  - [`popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts)
  - [`phase18aPopupCleanup.test.ts`](apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts)
  - [`extensionReset.test.ts`](apps/extension-douyin-capture/src/extensionReset.test.ts)
  - [`modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts)
- Added assertions that Run no longer exposes non-core wording such as queue preview, debug details, payload guard, and first/last dry-run actions.

## Non-Goals Preserved
- No harvester workflow logic changes.
- No controller or backend contract changes.
- No new extraction, crawler, scoring, queue, or publishing behavior.
- No API contract redesign.

## Verification Status
- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed (all 24 test suites).
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed with no errors.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed, producing `dist/contentScript.js` (188.1kb).
- Stale `Technical` wording sweep completed: remaining references are only in test assertions that explicitly reject the old label (`/>Technical<\//`) or in comments describing friendly error copy.

## 9-Section Summary

### 1. Objective
Reset the Douyin Profile Harvester popup UX foundation into an operator dashboard with clear `Run` / `Results` / `Advanced` information architecture, standardized design tokens, and reduced non-core clutter in the main flow.

### 2. Scope
- Surface: [`popup.html`](apps/extension-douyin-capture/public/popup.html), [`popup.css`](apps/extension-douyin-capture/public/popup.css), [`popup.ts`](apps/extension-douyin-capture/src/popup.ts), popup test files under [`apps/extension-douyin-capture/src`](apps/extension-douyin-capture/src), and supporting notes in [`docs`](docs).
- Phase 20A only. No harvester logic changes, no backend contract changes, no new product capabilities beyond the UI foundation reset.

### 3. Changes Made
- Rebuilt popup structure around three top-level tabs: `Run`, `Results`, `Advanced`.
- Kept `Run` focused on core operator sequence: Scan Profile → Test 3 Videos → Extract Metrics → Save to Capture Inbox.
- Moved queue preview, extraction results, backend save flow, and recent save outcomes into `Results`.
- Moved connection/configuration, calibration, diagnostics, troubleshooting, safety, and debug into `Advanced`.
- Standardized design tokens (surface, text, status colors, spacing, radius) and button variants (primary, secondary, warning, danger, ghost, disabled) in [`popup.css`](apps/extension-douyin-capture/public/popup.css).
- Updated tab persistence and DOM references in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts) from `technical` to `advanced`.
- Updated run-tab alert wording in [`viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts) to point to `Advanced` instead of `Technical`.
- Updated 7 popup-related test files to match the new IA and wording.
- Preserved existing handler compatibility hooks such as [`#wholeProfileOpenTechnicalButton`](apps/extension-douyin-capture/public/popup.html) and the hidden quick-start DOM node.

### 4. Files Modified
- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
- [`apps/extension-douyin-capture/public/popup.css`](apps/extension-douyin-capture/public/popup.css)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [`apps/extension-douyin-capture/src/popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts)
- [`apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts`](apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts)
- [`apps/extension-douyin-capture/src/extensionReset.test.ts`](apps/extension-douyin-capture/src/extensionReset.test.ts)
- [`apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts)

### 5. Tests Updated
- Added/replaced assertions that `Run` no longer exposes non-core wording (queue preview, debug details, payload guard, first/last dry-run actions).
- Added assertions that top-level tab label `Technical` is removed.
- All 24 extension test suites pass.

### 6. Non-Goals Preserved
- No harvester workflow logic changes.
- No controller or backend contract changes.
- No new extraction, crawler, scoring, queue, or publishing behavior.
- No API contract redesign.

### 7. Decisions
- Keep `Run` strictly operator-facing and compact.
- Preserve existing ids or compatibility hooks when they avoid logic churn.
- Preserve quick-start preference compatibility while hiding the expanded guide in compact `Run` rendering.
- Avoid harvest logic changes.

### 8. Risks / Follow-Up
- None identified. Foundation is stable and all validation commands pass.

### 9. Next Steps
- Phase 20A is complete. Proceed to next planned phase or pause for operator review.
