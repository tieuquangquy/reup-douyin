# Phase 20C-1 — Action Deck UI Hard-Replace Log

## Goal
Replace the legacy popup card-stack layout with a single-screen Action Deck UI that keeps every existing workflow step reachable while surfacing the most important operator controls first.

## Summary of Changes

### Files Created
- `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts` — dedicated contract test for the Action Deck markup, CSS, source wiring, and primary-action dispatch.

### Files Modified
- `apps/extension-douyin-capture/public/popup.html` — hard-replaced legacy card stack with seven Action Deck sections:
  1. `deck-header` — title + subtitle + status
  2. `deck-health-ribbon` — four metric chips (Detected / Profile / Queue / Saved)
  3. `deck-action-panel` — primary CTA, disabled reason, and stepper rail
  4. `deck-settings-bar` — mode / batch / speed selectors
  5. `deck-kpi-strip` — backend readiness chips
  6. `deck-bottom-dock` — tab switcher (Results / Advanced)
  7. `deck-alert` — transient inline banner
  Moved all legacy content into the `deckPanelAdvanced` panel so nothing is lost.
- `apps/extension-douyin-capture/public/popup.css` — added `deck-*` CSS block with gradient shell, chip styles, settings rows, bottom dock, panel visibility, and responsive helpers.
- `apps/extension-douyin-capture/src/popup.ts` —
  - Added `renderActionDeck`, `renderMetricRows`, chip helpers, and panel switching.
  - Replaced old compact-dashboard render path with Action Deck as the main render surface.
  - Wired `runWholeProfilePrimaryActionFromPopup` to the single primary-action button.
  - Added `saveDeckHarvestOptionsFromPopup`, `applyDeckHarvestOptionsSelection`, and `setDeckActivePanel`.
  - Bottom-dock buttons toggle `deckPanelResults` and `deckPanelAdvanced` visibility.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts` — added `getActionDeckViewModel(state)` to produce a display-only view model for the deck surface (title, subtitle, chips, steps, settings, backend readiness, actions, disabled reason).

### Test Files Updated
- `popupWorkflow.test.ts` — removed legacy production-button inventory loop; added negative assertions for removed ids; updated calibration heading to `data-feature="calibration-details"`; changed main heading to `Douyin Harvest`; changed calibration label to `Start Calibration`; removed stale `Resume`/`Stop` button expectations and replaced with source assertion on `runWholeProfilePrimaryActionFromPopup`.
- `phase18aPopupCleanup.test.ts` — removed `"Action Deck"`, `"Stop"`, `"Resume"` from product-text loop; fixed batch option order to `Next 10` before `Next 5`; replaced `/Review and run the next safe step\./` with `/Scan → Extract → Save/`; removed stale CSS assertions for `.summary__value--short`, `.summary__value--url`, and `panel[data-feature="progress"]...`; added `deckActionPanel` and dynamic-action source assertions.
- `wholeProfileHarvest.backendFlow.test.ts` — replaced old backend button ids with backend flow status row ids (`backendFlowSessionStatus`, `backendFlowPayloadStatus`, etc.).
- `wholeProfileHarvest.viewModel.test.ts` — replaced old compact-dashboard assertions with Action Deck markup assertions (`deckActionPanel`, `deckStepRail`, `deckKpiStrip`, etc.); updated CSS assertions to existing classes (`.compact-list-section`, `.deck-disabled-reason`) and removed missing ones (`.metric-value`, `.section-heading-row`, `.field-help`).
- `wholeProfileHarvest.wording.test.ts` — replaced `/Action Deck/` with `/id="deckActionPanel"/`; replaced `/Review and run the next safe step\./` with `/Scan → Extract → Save/`; changed `/Security check and troubleshooting/` to `/Troubleshooting/` and `/Safety tips/` to `/Safety Tips/`; replaced `/Debug Details/` with `/Maintenance/`; replaced `\.helper--lead` with `\.deck-header__tagline`.
- `extensionReset.test.ts` — updated reset button ids to current maintenance controls (`resetHarvestStateButton`, `resetCalibrationStateButton`, `factoryResetExtensionButton`).
- `wholeProfileHarvest.tabs.test.ts` — changed calibration heading assertion from `/Calibration<\/h2>/` to `/data-feature="calibration-details"/.

## Validation
- `npm test -- --runInBand` passes (all 24 test suites).
- `npm run build` succeeds.

## Decisions
- The Action Deck is a single-screen surface; legacy detailed content is preserved inside the Advanced panel so power users still have access.
- Primary action wiring uses the existing `runWholeProfilePrimaryActionFromPopup` dispatch so no new orchestration logic was introduced.
- Settings bar reuses existing `saveWholeProfileHarvestOptionsFromPopup` semantics; a thin `saveDeckHarvestOptionsFromPopup` wrapper was added for clarity.
- CSS width is set to `400px` with a `max-width: 420px` safety constraint to keep the popup stable across screens.

## Non-Goals (intentionally out of scope)
- No new crawling or video processing logic.
- No backend API changes.
- No database or queue changes.
- No multi-user or SaaS-specific features added yet.
