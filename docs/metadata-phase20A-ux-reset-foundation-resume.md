# Phase 20A UX Reset Foundation Resume

## Current Status
- Phase 20A popup UX reset foundation is in progress for the Douyin Profile Harvester popup.
- The new `Run` / `Results` / `Advanced` tab split is implemented in [`popup.html`](apps/extension-douyin-capture/public/popup.html).
- Foundation tokens and button variants are implemented in [`popup.css`](apps/extension-douyin-capture/public/popup.css).
- Popup tab wiring has been updated in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts) to persist `advanced` instead of `technical` in local UI prefs.
- Multiple popup-related test files have been updated to the new Phase 20A information architecture and wording.
- [`docs/metadata-phase20A-ux-reset-foundation-log.md`](docs/metadata-phase20A-ux-reset-foundation-log.md) has been created.

## Files Touched So Far
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
- [`docs/metadata-phase20A-ux-reset-foundation-log.md`](docs/metadata-phase20A-ux-reset-foundation-log.md)

## Key Decisions
- Keep Run strictly operator-facing and compact.
- Keep save flow, queue preview, extraction results, and save outcomes in Results.
- Keep connection/configuration, calibration, diagnostics, troubleshooting, safety, and debug in Advanced.
- Preserve existing ids or compatibility hooks when they avoid logic churn, including [`#wholeProfileOpenTechnicalButton`](apps/extension-douyin-capture/public/popup.html).
- Preserve quick-start preference compatibility while hiding the expanded guide in the compact Run flow.
- Avoid harvest logic changes.

## Completed Work
- [`docs/metadata-phase20A-ui-component-inventory.md`](docs/metadata-phase20A-ui-component-inventory.md) created.
- Final search sweep for stale UI-facing `Technical` wording completed: remaining references are only in test assertions that reject the old label or in comments describing friendly error copy.
- Verification commands run and passed:
  - `npm --workspace @reup-douyin/extension-douyin-capture run test` — all 24 extension test suites passed.
  - `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` — no errors.
  - `npm --workspace @reup-douyin/extension-douyin-capture run build` — succeeded (`dist/contentScript.js` 188.1kb).
- Final Phase 20A report delivered in 9-section format inside [`docs/metadata-phase20A-ux-reset-foundation-log.md`](docs/metadata-phase20A-ux-reset-foundation-log.md).

## Resume Point
- Phase 20A is complete. Proceed to next planned phase or pause for operator review.
