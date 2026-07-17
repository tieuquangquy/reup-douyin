# Phase 18I-J7 Popup Operator Flow Log

## Step
Finalize the Phase 18I-J7 popup cleanup so the main extension popup preserves only the canonical operator workflow, removes stale legacy noise from the production button contract, and verifies the Scan -> Test -> Extract -> Save flow remains operator-ready.

## Scope Lock
- Target only [`apps/extension-douyin-capture`](apps/extension-douyin-capture).
- Keep the visible popup focused on the canonical whole-profile operator path.
- Preserve access to diagnostics through Technical Details instead of restoring removed legacy controls.
- Do not change backend API contracts, Capture Inbox storage design, crawler behavior, or unrelated web app flows.

## Findings
- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html) already reflected the intended operator-first popup surface.
- A stale production button contract in [`PRODUCTION_BUTTON_IDS`](apps/extension-douyin-capture/src/popupWorkflow.ts:1) still treated `probeHarvestButton` as part of the visible operator surface.
- [`apps/extension-douyin-capture/dist/popup.html`](apps/extension-douyin-capture/dist/popup.html) was stale until the extension workspace build was rerun.
- Existing controller and view-model tests already covered the canonical flow and key operator safety behaviors:
  - verify / scan
  - dry-run sample
  - extraction
  - Save 1 verification
  - Save Batch verification
  - skip-complete behavior
  - stop / resume
  - captcha pause
  - safe defaults
  - Technical Details wording
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts:302) still contained dead selector reads for hidden modal/test controls that no longer exist in the production popup HTML.

## Changes Implemented
1. Removed the stale `probeHarvestButton` entry from the production button contract in [`apps/extension-douyin-capture/src/popupWorkflow.ts`](apps/extension-douyin-capture/src/popupWorkflow.ts).
2. Updated the popup workflow regression expectation in [`apps/extension-douyin-capture/src/popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts) so the canonical visible button count matches the J7 popup surface.
3. Rebuilt the extension workspace so [`apps/extension-douyin-capture/dist/popup.html`](apps/extension-douyin-capture/dist/popup.html) no longer carries the stale probe button.
4. Removed dead popup selector dependencies in [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts:302) and replaced hidden-control reads with explicit safe defaults:
   - dry-run specific ids default to an empty string
   - staged-harvest V2 limit defaults to `3`
5. Revalidated the extension tests to confirm the canonical workflow and popup wording remain correct.

## Files Touched
- [`apps/extension-douyin-capture/src/popupWorkflow.ts`](apps/extension-douyin-capture/src/popupWorkflow.ts)
- [`apps/extension-douyin-capture/src/popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`docs/phase18i-j7-popup-operator-flow-log.md`](docs/phase18i-j7-popup-operator-flow-log.md)

## Verification Notes
- Passed build:
  - `npm --workspace @reup-douyin/extension-douyin-capture run build`
- Passed tests:
  - `npm --workspace @reup-douyin/extension-douyin-capture run test`
- Audit confirmed existing regression coverage in:
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts)
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest.backendFlow.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.backendFlow.test.ts)
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)

## Status
Completed.
