# Phase 18I-K1 Resume

## Scope

- App: `apps/extension-douyin-capture`
- Focus:
  - readiness/gating fixes
  - compact professional popup layout
  - wording and visual hierarchy
- Non-goals:
  - scanner logic
  - dry-run logic
  - extraction logic
  - backend/session/flush logic

## What changed

- Readiness:
  - introduced canonical `calibration_ready`
  - dry-run gating now respects actual calibration state
  - next action no longer misfires to calibration when 4-point calibration already exists
- Main popup:
  - compact `Ready status` header with status chips
  - compact 4-step stepper
  - one primary action button
  - compact settings row for `Mode / Batch / Speed`
  - save flow stays locked until extraction results exist
  - queue preview collapsed by default
- Details:
  - raw connection and technical rows moved down to Technical/Debug Details

## Key files

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`

## Verification

- typecheck passed
- extension test suite passed
- extension build passed

## Manual retest

1. Reload the unpacked extension.
2. Open a Douyin profile with existing calibration.
3. Confirm:
   - `Calibration: Ready`
   - Next step is not calibration.
4. After profile scan:
   - Quick Start collapses
   - stepper shows `Scan Done`, `Test Next`, `Extract Locked`, `Save Locked`
5. Before dry-run:
   - `Extract Next 10` remains locked
6. Before extraction results:
   - Save section shows locked message
   - guided save rows remain hidden
7. After extraction:
   - Save rows appear
   - primary action advances to `Create Save Session`
