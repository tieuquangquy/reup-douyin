# Phase 22C-9M Reuse Legacy Verified Target Scanner Resume

## Status
Implementation in progress/completed pending validation.

## What Changed
- `apps/extension-douyin-capture/src/contentScript.ts`
  - `runModalTestProfileScan(...)` accepts `message.run_id ?? message.scan_run_id`.
- `apps/extension-douyin-capture/src/background.ts`
  - Background scanner message includes both `run_id` and `scan_run_id`.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - Normal full-scroll success diagnostics identify the engine as `legacy_verified_target_scanner`.
  - Normal queue diagnostics identify the builder as `legacy_verified_target_scanner_22C9M`.
  - DOM Probe queue builder remains fallback-only.
- Tests updated in `modalWholeProfileTest.test.ts`, `wholeProfileHarvest.test.ts`, and `wholeProfileHarvest.viewModel.test.ts` for 22C-9M markers and legacy scanner diagnostics.

## Old Scanner Audit
- Old scanner still exists in `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`.
- Main scanner: `collectProfileCardsUntilStable(...)`.
- Schema version: `phase17s_dry_run_reuse_verified_targets`.
- Rejections: `validateDouyinAwemeCandidate(...)` for `no_video_context`; `addValidatedCard(...)` for `duplicate`.
- No removal commit needed because the scanner still exists in the workspace.

## Validation To Run
1. `npm --workspace @reup-douyin/extension-douyin-capture run test`
2. `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
3. `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Manual Retest Focus
- Open a Douyin profile and click Scan Profile.
- Confirm diagnostics show `scan_engine_used: legacy_verified_target_scanner`.
- Confirm `scan_fallback_used: no` on normal success.
- Confirm `scan_queue_builder_used: legacy_verified_target_scanner_22C9M` on normal success.
- Confirm scan rounds and stop reason come from the old full-scroll scanner, e.g. `stable_no_new_ids`.
- Confirm DOM Probe fallback is only used when the legacy scanner fails or returns zero usable targets.
