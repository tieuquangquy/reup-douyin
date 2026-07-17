# Phase 22C-9M Reuse Legacy Verified Target Scanner Log

## Scope
- Reused the legacy verified-target full-scroll scanner as the normal Scan Profile engine after DOM Probe preflight.
- Kept DOM Probe candidate queue construction as fallback only.
- Did not change Start Collecting, Pause, Resume, Reset, backend flush, modal extraction, Capture Inbox, Review Board, or Reup Score.

## Old Scanner Location Found
- Schema producer: `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`, `MODAL_WHOLE_PROFILE_TEST_SCHEMA_VERSION = "phase17s_dry_run_reuse_verified_targets"`.
- Full-scroll engine: `collectProfileCardsUntilStable(...)`, including the `stable_no_new_ids` stop path.
- Scanner wrapper: `scanModalWholeProfileCardsInPage(...)` and the content-script `runModalTestProfileScan(...)` message route.
- Verified targets/detail persistence in the legacy popup flow: `completeModalWholeProfileTestRun(...)`.
- Candidate validation: `validateDouyinAwemeCandidate(...)` rejects `no_video_context`; `addValidatedCard(...)` rejects `duplicate`.

## Integration Notes
- Background Scan Profile now sends both `run_id` and `scan_run_id` to `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE`.
- Content script accepts `run_id` or `scan_run_id`, so the background-owned route reaches the old scanner instead of failing before scan start.
- Current canonical adapter remains `scanWholeProfileTargets(...)`, which converts legacy cards/classifications into current `targets`, `target_details`, and rejected samples.
- Normal success diagnostics now stamp `scan_engine_used: "legacy_verified_target_scanner"`, `legacy_verified_scanner_version: "phase17s_dry_run_reuse_verified_targets"`, and `scan_queue_builder_used: "legacy_verified_target_scanner_22C9M"`.

## Fallback Behavior
- `completeProfileVerifyFromDomProbe22C9J(...)` remains the DOM Probe fallback finalizer.
- Fallback diagnostics still use `scan_queue_builder_used: "dom_probe_known_good_fallback_22C9K"` and `scan_fallback_used: "yes"`.
- Normal legacy-scanner success reports `scan_fallback_used: "no"`.

## Tests
- Updated version-marker tests from 22C-9L to 22C-9M.
- Added 22C-9M assertions that normal Scan Profile success uses the legacy verified-target scanner and preserves `stable_no_new_ids` rounds/stop diagnostics.
