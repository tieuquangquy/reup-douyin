# Phase 22C-8C-Revised Scan Before Calibration Resume

## Completed
- Primary action selector keeps `scan_profile` before calibration when profile scan or classification is missing.
- Missing calibration now routes to `calibrate` only after scan/classification/queue readiness exists.
- Start Collecting remains gated by calibration readiness.
- Zero-round scan failures normalize away from `profile_scan_incomplete` and expose guard diagnostics.
- Expected count diagnostics now include value, source, current profile URL, and update timestamp.

## Key Files
- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Validation
- Run `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`.
- Run `npm --workspace @reup-douyin/extension-douyin-capture run test`.
- Run `npm --workspace @reup-douyin/extension-douyin-capture run build`.
