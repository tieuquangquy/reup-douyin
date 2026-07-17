# Phase 18G Profile Grid Not Ready Scanner Fix Log

## Summary
- Implemented Phase 18G verify-flow adjustment to stop treating pre-grid readiness as a hard blocker.
- Added warmup-first behavior in popup runtime, then scanner-driven verification outcome.
- Kept canonical scanner as source of truth for profile target extraction.

## Code Changes
- Updated [`createWholeProfilePopupRuntime()`](apps/extension-douyin-capture/src/popup.ts:335) behavior:
  - [`waitForProfileReady()`](apps/extension-douyin-capture/src/popup.ts:368) now uses warmup diagnostics and does not hard-fail verify before scanner.
  - [`getActualProfileReadiness()`](apps/extension-douyin-capture/src/popup.ts:441) now uses warmup diagnostics instead of strict 1s grid gate outcome.
- Added warmup helper:
  - [`warmupProfileBeforeScan()`](apps/extension-douyin-capture/src/popup.ts:3597).
- Updated verify preparation flow:
  - [`prepareProfilePageForScan()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:249) now records warmup and always advances to scanner phase.
- Error code set previously expanded in [`WholeProfileHarvestErrorCode`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:1) with scanner-oriented codes for this phase.

## Test Adjustments
- Updated verify expectation in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:230) to reflect scanner-first flow while preserving current canonical mapping behavior.

## Validation Runs
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run test` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run build` ✅

## Notes
- Current canonical scanner failure mapping still returns grid-not-ready in one targeted path; this remains consistent with existing scanner error conversion semantics and passing tests.
