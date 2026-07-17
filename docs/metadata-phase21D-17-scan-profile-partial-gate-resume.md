# Phase 21D-17 Scan Profile Partial-Scan Classification Gate Resume

## Completed
- Propagated scan completeness fields through [`scanWholeProfileTargets()`](apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts:20).
- Added `profile_scan_incomplete` to [`WholeProfileHarvestErrorCode`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:1).
- Gated [`completeProfileVerify()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:655) so incomplete scans fail before classification starts.
- Added incomplete-scan regression coverage in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:738).
- Preserved legacy low-count source-contract text in [`buildScanDiagnostics()`](apps/extension-douyin-capture/src/modalWholeProfileTest.ts:754).
- Passed targeted validation:
  - `npm exec -- tsx src/wholeProfileHarvest.test.ts`
  - `npm exec -- tsx src/modalWholeProfileTest.test.ts`
  - `npm run typecheck`
  - `npm run build`

## Current behavior
- A whole-profile scan that reports `partial_scan: true` or a positive `missing_expected_count` now fails verification with `profile_scan_incomplete`.
- Backend classification is skipped for incomplete scans.
- Successful complete scans continue through classification and queue preparation unchanged.

## If work resumes later
1. Re-check [`getDouyinScannerWorkflowReadiness()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:210) if product semantics change from "fail verify" to a softer "scan succeeded but incomplete" mode.
2. Re-check popup wording in [`successWholeProfileMessage()`](apps/extension-douyin-capture/src/popup.ts:505) if a dedicated incomplete-scan banner is needed.
3. If broader suite execution is required, run the full extension test script after confirming there are no unrelated failing tests.
