# Phase 18I-D Real Modal Extraction Queue Resume

## Current State
Phase 18I-D is implemented for the requested extension-only scope:
- Whole-profile harvest now runs in `real_modal_extraction_no_backend` mode.
- The active run path opens real Douyin modal URLs and extracts real metrics per queued target.
- Each processed target is checkpointed locally before the next target continues.
- Stop/resume remains durable through persisted queue and result state.
- Captcha or checkpoint detection pauses the harvest instead of bypassing it.
- No capture session is created.
- No backend flush is performed.
- No Capture Inbox items are created by this Phase 18I-D run path.
- Extension [`typecheck`](apps/extension-douyin-capture/package.json), [`build`](apps/extension-douyin-capture/package.json), and full extension [`test`](apps/extension-douyin-capture/package.json) pass in the current environment.

## What Was Delivered
- State/result schema updates in [`state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts) for extraction-only checkpointed results.
- Real modal extraction queue execution in [`runHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:189) and [`resumeHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:209) via [`runRealModalExtractionHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:514).
- Local checkpoint persistence after each target through [`checkpointLocalHarvestTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:829).
- Captcha pause handling through [`pauseHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:490) and runtime detection in [`createWholeProfilePopupRuntime()`](apps/extension-douyin-capture/src/popup.ts:369).
- Extraction-only popup/debug/progress messaging in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts) and [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3).
- Updated extension tests in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) plus compile-safe canonical helpers in [`canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts).

## Validation Snapshot
- `npx tsc -p apps/extension-douyin-capture/tsconfig.json --noEmit` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run build` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run test` ✅
- Direct [`node --test`](package.json) execution against [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) is not the project runner and fails because the file imports compiled `.js` module specifiers; workspace [`tsx`](apps/extension-douyin-capture/package.json) test execution is the correct validation path.

## Follow-up (if continuing)
1. Keep future work scoped to backend attachment only when a later phase explicitly allows capture-session creation and flush.
2. Preserve the explicit operator-facing wording that this mode is extraction-only and does not create backend records.
3. Maintain local checkpoint durability and captcha pause semantics if additional retry or resume behavior is added later.
