# Phase 22C-9Z-NOGIT Restore Last-Known-Good Scan Engine Log

## No-git audit completed

This workspace is not a git checkout, so recovery used only local files in the project folder. A prechange file list was created at `docs/metadata-phase22C-9Z-NOGIT-prechange-file-list.md` before production-code edits.

## Search locations

Searched source, compiled extension output, release output, and docs under `apps` and `docs` for old Scan Profile clues: `stable_no_new_ids`, `expected_count_reached`, `verified_targets`, `verified_target_details`, `phase17s_dry_run_reuse_verified_targets`, `candidate_validation`, `no_video_context`, `duplicate`, `target_count`, `total_candidates`, `total_cards_found`, `refresh_all_target_count`, `selected_mode_target_count`, `profile_card_scan_status`, `harvest_plan_status`, `wholeProfileHarvest`, `runProfileScan`, `scanProfile`, `queue`, `modal_id`, and `/video/`.

## Files with old scanner clues

- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts` - source scanner exists. Contains `MODAL_WHOLE_PROFILE_TEST_SCHEMA_VERSION = "phase17s_dry_run_reuse_verified_targets"`, `collectProfileCardsUntilStable(...)`, `scanModalWholeProfileCardsInPage(...)`, `stable_no_new_ids`, `expected_count_reached`, verified target cache types, candidate validation, duplicate rejection, and profile-card evidence.
- `apps/extension-douyin-capture/src/contentScript.ts` - production content-script message handler imports and calls `collectProfileCardsUntilStable(...)` for Scan Profile.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts` - adapter converts scanner cards/diagnostics into canonical whole-profile targets via `scanWholeProfileTargets(...)`.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts` - current Scan Profile controller routes normal success through the legacy verified scanner wrapper; DOM Probe queue builder remains fallback-only.
- `apps/extension-douyin-capture/src/popup.ts` - older Modal Whole Profile verify path stores `verified_targets`, `verified_target_details`, `verified_target_count`, and scan diagnostics.
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts` - tests assert the old scanner schema, stable full-profile collection loop, selected scroll container diagnostics, verified cache fields, and no verified target failures.
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` - tests assert the current controller uses the legacy verified scanner as the main Scan Profile engine and preserves scan rounds/stop reason.
- `apps/extension-douyin-capture/dist/modalWholeProfileTest.js` - compiled copy of the old scanner source.
- `apps/extension-douyin-capture/dist/contentScript.js` - compiled content-script copy calling the old scanner.
- `apps/extension-douyin-capture/dist/wholeProfileHarvest/controller.js` - compiled current controller diagnostics for legacy scanner use.
- `apps/extension-douyin-capture/dist/wholeProfileHarvest/targetValidation.js` - compiled target validation clues, including rejection accounting.
- `apps/extension-douyin-capture/dist/popup.js` - compiled old verified target queue persistence path.
- `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0/modalWholeProfileTest.js` - release copy of old scanner.
- `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0/contentScript.js` - release copy of content-script scanner use.
- `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0/popup.js` - release copy of verified target queue persistence.
- `docs/metadata-phase17S-dry-run-reuse-verified-targets-log.md` - documents verified target cache creation and dry-run reuse.
- `docs/metadata-phase17S-dry-run-reuse-verified-targets-resume.md` - documents runtime cache shape and resume rules.
- `docs/metadata-phase17U-whole-profile-staged-production-harvest-log.md` - documents staged production harvest using verified targets.
- `docs/metadata-phase17U-whole-profile-staged-production-harvest-resume.md` - documents missing verified target failure mode.
- `docs/metadata-phase17V-isolated-staged-harvest-v2-log.md` - documents V2 reading only `verified_targets` and `verified_target_details`.
- `docs/metadata-phase22C-9L-restore-full-profile-scroll-scan-log.md` - identifies `scanModalWholeProfileCardsInPage(...)` and `collectProfileCardsUntilStable(...)` as old working functions and documents old stop conditions/selectors/diagnostics.
- `docs/metadata-phase22C-9M-reuse-legacy-verified-target-scanner-log.md` - documents current source scanner reuse.
- `docs/metadata-phase22C-9M-reuse-legacy-verified-target-scanner-resume.md` - documents current baseline.

## Audit decision

Old engine source exists locally. It is not only compiled dist. The most likely last-known-good scanner is `collectProfileCardsUntilStable(...)` in `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`, with the legacy wrapper `legacyVerifiedProfileScanner22C9ZNoGit(...)`. It can be reused directly with a named Phase 22C-9Z wrapper/adapter rather than reconstructing logic from dist.

## Restore path

Use the source scanner unchanged, expose a named `legacyVerifiedProfileScanner22C9ZNoGit(...)` wrapper, and lock production Scan Profile diagnostics to `legacy_verified_profile_scroll_scanner_22C9Z_NOGIT`. Keep DOM Probe as diagnostic/preflight and fallback-only. Keep Reset behavior around scanner state without replacing scanner internals.

## Phase 22C-9Z-1 production-path wiring

- Exact branch fixed: `runScanProfileWorkflow(...)` runs ping and `runtime.runPostPingProfileDomProbe22C9I(...)`, then `completeProfileVerify(...)` calls the background runtime `scanProfile(...)`, which now sends `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z1` to `contentScript.ts`.
- Content-script scanner invocation now calls `legacyVerifiedProfileScanner22C9ZNoGit(...)`, which wraps `collectProfileCardsUntilStable(...)`, after DOM Probe succeeds instead of treating DOM Probe candidates as the production queue.
- Runtime/version diagnostics are stamped as `22C-9Z-1`, `22C-9Z-1-scan-controller`, and scan run ids use the `scan_profile_22C9Z1_` prefix.
- Legacy invocation sentinels include attempted/function/wrapper/start/result/completion/rounds/stop reason/candidate and rejection counts, plus failure-stage fields for missing handler or throw cases.
- Queue adapter diagnostics stamp `legacy_verified_target_queue_adapter_22C9Z1`, input/output/duplicate counts, adapter sample, and `legacy_queue_adapter_zero_output` when no queue can be produced.
- Production success diagnostics stamp `scan_engine_used` and `production_profile_scan_engine` as `legacy_verified_profile_scroll_scanner_22C9Z1`, `scan_fallback_used: "no"`, and `scan_queue_builder_used: "legacy_verified_target_queue_adapter_22C9Z1"`.

## Phase 22C-9Z-1 validation

- `npm --workspace @reup-douyin/extension-douyin-capture run test` completed successfully and also ran the workspace build as part of the test script.

## Phase 22C-9Z-2 exact post-DOM-probe patch

- Exact branch fixed: `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts` `verifyProfile(...)` runs the post-ping DOM Probe, then `completeProfileVerify(...)` immediately calls `runLegacyVerifiedProfileScrollScan22C9ZNOGIT(...)` for the production scanner path.
- The branch now uses `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z2` through the background/content-script route and stamps `22C-9Z-2`, `22C-9Z-2-scan-controller`, and `scan_profile_22C9Z2_` run ids.
- Hard invariant: when diagnostics show `profile_dom_probe_status == completed`, `profile_grid_ready == true`, and `aweme_id_count > 0`, controller finalization cannot surface generic no-round/failed/zero-queue outcomes; it emits the legacy scanner-specific error family instead.
- Legacy invocation diagnostics now include `legacy_route_invoked`, `legacy_scanner_route_invoked`, attempted/result/function/wrapper/message type/trace version, scan rounds, stop reason, candidate counts, and failure-stage details.
- Queue adapter diagnostics stamp `legacy_verified_target_queue_adapter_22C9Z2`, `discovery_source: legacy_verified_profile_scroll_scanner_22C9Z2`, `profile_queue_total_count`, `profileScanReady`, `scanRounds`, and `scanStop`.
