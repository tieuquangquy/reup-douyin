# Phase 15B Resume — Extracted Item Commit Watchdog

## Current State
- Core Phase 15B scaffolding is active in [`modalHarvest.ts`](apps/extension-douyin-capture/src/modalHarvest.ts).
- Progress contract fields are present in [`types.ts`](apps/extension-douyin-capture/src/types.ts).
- Popup phase rendering has stage-aware extracting/committing labels in [`popupProgress.ts`](apps/extension-douyin-capture/src/popupProgress.ts).

## What Is Confirmed Working
- [`tsc --noEmit`](apps/extension-douyin-capture/tsconfig.json) passes.
- Targeted tests for modal harvest, popup progress, and runtime v2 pass.

## Remaining Work To Complete Phase 15B
1. Finish runtime diagnostics mapping in [`runtimeV2ToProgress()`](apps/extension-douyin-capture/src/harvestRuntimeV2.ts:367) so fallback/runtime paths emit stable values for all new progress fields.
2. Add or adjust explicit assertions in:
   - [`modalHarvest.test.ts`](apps/extension-douyin-capture/src/modalHarvest.test.ts)
   - [`harvestRuntimeV2.test.ts`](apps/extension-douyin-capture/src/harvestRuntimeV2.test.ts)
   - [`popupProgress.test.ts`](apps/extension-douyin-capture/src/popupProgress.test.ts)
3. Run final verification commands:
   - `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
   - `npm --workspace @reup-douyin/extension-douyin-capture run build`
   - `npm --workspace @reup-douyin/extension-douyin-capture run test` (currently expected to fail on legacy popup workflow maintenance label assertion unless separately updated).

## Notes
- Existing repo baseline includes a non-Phase-15B test expectation mismatch around maintenance label wording in [`popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts).
