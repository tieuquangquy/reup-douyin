# Phase 21D-17 Scan Profile Partial-Scan Classification Gate Log

## Scope
- Finish the active [`Scan Profile`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:219) pipeline work for Phase 21D-17.
- Preserve scanner-side multi-round scan hardening already implemented in [`collectProfileCardsUntilStable()`](apps/extension-douyin-capture/src/modalWholeProfileTest.ts:494).
- Block backend classification when the whole-profile scan is incomplete.

## Files changed
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`apps/extension-douyin-capture/src/modalWholeProfileTest.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.ts)

## Implemented changes
1. [`scanWholeProfileTargets()`](apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts:20) now propagates completeness metadata from scan diagnostics:
   - `partial_scan`
   - `expected_profile_video_count`
   - `final_found_count`
   - `missing_expected_count`

2. [`WholeProfileHarvestErrorCode`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:1) now includes `profile_scan_incomplete` with operator-facing messaging for retry after the profile finishes loading.

3. [`completeProfileVerify()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:655) now throws [`wholeProfileHarvestError()`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:123) with `profile_scan_incomplete` when either of these conditions is true:
   - `scan.partial_scan`
   - `scan.missing_expected_count > 0`

4. [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:738) now covers the incomplete-scan case and verifies that classification does not start.

5. [`buildScanDiagnostics()`](apps/extension-douyin-capture/src/modalWholeProfileTest.ts:754) kept the low-count warning contract while preserving the newer partial-scan warning path so existing source-contract tests still pass.

## Validation completed
- [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) via `npm exec -- tsx src/wholeProfileHarvest.test.ts`
- [`modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts) via `npm exec -- tsx src/modalWholeProfileTest.test.ts`
- [`tsconfig.json`](apps/extension-douyin-capture/tsconfig.json) typecheck via `npm run typecheck`
- extension build via `npm run build`

## Notes
- The repository test script still chains all extension tests and then build; the targeted Phase 21D-17 validation was run directly to avoid unrelated sequencing noise.
- No queue, backend contract, or popup workflow semantics were expanded beyond the requested incomplete-scan gating behavior.
