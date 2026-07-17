# Phase 18G Profile Grid Not Ready Scanner Fix Resume

## What Was Completed
- Popup runtime warmup flow added and wired before verify scanner handoff.
- Verify preparation now logs warmup diagnostics and proceeds into scanner phase without pre-grid hard block.
- Typecheck/test/build pass after updates.

## Key Files
- [`popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`errors.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts)
- [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)

## Current Behavior Snapshot
- Verify now performs a warmup pass via [`warmupProfileBeforeScan()`](apps/extension-douyin-capture/src/popup.ts:3597).
- Warmup diagnostics are attached to readiness/debug state.
- Scanner remains the final authority for target extraction outcome.

## Next Follow-up (if needed)
- Tighten scanner failure-code normalization in [`scanWholeProfileTargets()`](apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts:16) if additional reason granularity is required beyond current passing contract.
