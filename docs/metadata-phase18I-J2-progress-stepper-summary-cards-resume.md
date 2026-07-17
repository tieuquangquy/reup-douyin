# Phase 18I-J2 Resume

## Goal

Replace the noisy Whole Profile Harvest Progress list with a compact operator-facing workflow view.

## Canonical view model

- `getWholeProfileHarvestProgressViewModel(state)`

File:

- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`

This view model depends only on canonical Whole Profile state plus J1 readiness selectors.

## Main UI

- Stepper with 4 steps
- Next Action card
- 5 summary cards
- collapsible Details block

## Details content

- shortened profile URL in main progress
- full URL available in Details
- raw status/phase moved out of main cards
- queue preview rendered as row list
- recent results rendered as row list

## Important constraint

No new harvest behavior was added.

This phase only changed presentation and view-model shaping.

## Tests run

- extension `typecheck`
- extension `test`
- extension `build`

## Manual retest

1. Verify a profile.
2. Run dry-run.
3. Confirm stepper advances to Verify done / Dry-run done.
4. Run extraction.
5. Confirm Extraction card shows mode, batch, speed, and counts.
6. Expand Details and confirm queue preview is row-based with `+N more`.
