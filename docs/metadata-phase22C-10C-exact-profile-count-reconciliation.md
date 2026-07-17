# Phase 22C-10C - Exact Profile Count Reconciliation

## Summary

Phase 22C-10A made Scan Profile use the canonical single-path route, but the recovered scanner could still stop at `max_rounds` with fewer videos than the visible Douyin Works tab count. In the reported case the page showed `作品 45`, while the extension finalized `40` queued targets as a verified scan.

## Audit Result

- Popup video display is derived in `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts` from `profileCount(...)`, which previously rendered only `40 videos`.
- `profile_queue_total_count` is set in `apps/extension-douyin-capture/src/background.ts` by `adaptCanonicalVerifiedTargets22C10C(...)` from the scanner response count.
- The canonical queue adapter does not hard-cap at 40. It preserves all unique `verified_targets` / `verified_target_details` returned by the scanner.
- The root stop condition was in `apps/extension-douyin-capture/src/contentScript.ts`, where the canonical content handler called `legacyVerifiedProfileScanner22C9ZNoGit({ max_rounds: 20 })`.
- `collectProfileCardsUntilStable(...)` already had partial expected-count diagnostics, but the canonical path did not pass expected count from the DOM probe and the background finalizer did not reconcile expected vs queued count.

## Implementation

- Upgraded active canonical Scan Profile diagnostics/message path to `22C-10C`.
- Added robust Works tab count parsing in `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`:
  - `作品 45`
  - count-before-label forms
  - compact counts such as `1.2万`
- DOM probe now includes expected count evidence:
  - `expectedProfileVideoCount`
  - raw text
  - selector
  - parse status/error
- Background passes `expectedProfileVideoCount` into `DOUYIN_SCAN_PROFILE_CANONICAL_22C10C`.
- Content script raises expected-count scan safety from fixed 20 rounds to `min(120, max(80, expected * 2))`.
- Scanner stop reason now becomes `max_rounds_before_expected_count` if max rounds are reached before a known expected count.
- Background reconciliation marks expected-count shortfall as incomplete:
  - `lastScannerResult = incomplete`
  - `lastScannerError = profile_scan_incomplete_expected_count_not_reached`
  - `profileScanReady = no`
  - `profile_scan_partial_ready = yes`
  - partial queue is preserved for diagnostics/rescan context.
- Readiness now blocks Start Collecting when `expected_profile_video_count > profile_queue_total_count`.
- Popup/view model renders `40 / 45 videos` when expected count is known and incomplete.

## Tests

Added or updated coverage for:

- parsing `作品 45`;
- parsing compact Chinese count text;
- passing `expectedProfileVideoCount` from DOM probe to the canonical scanner message;
- preserving a 40-item partial queue while blocking full readiness when expected is 45;
- emitting `profile_scan_incomplete_expected_count_not_reached`;
- 22C-10C canonical version/message markers.

## Manual Retest Checklist

1. Rebuild and reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the Douyin profile tab.
3. Confirm the page shows the Works tab count, for example `作品 45`.
4. Click Scan Profile.
5. Expected complete result:
   - `scanner_runtime_version = 22C-10C`
   - `expected_profile_video_count = 45`
   - `profile_queue_total_count = 45`
   - `profileScanReady = yes`
   - `lastScannerResult = success`
   - `scanStop = expected_count_reached`
6. Expected controlled incomplete result if only 40 are collected:
   - `profile_queue_total_count = 40`
   - `missing_profile_video_count = 5`
   - `lastScannerResult = incomplete`
   - `lastScannerError = profile_scan_incomplete_expected_count_not_reached`
   - popup shows `40 / 45 videos`
   - Start Collecting remains locked.

## Remaining Risk

If Douyin lazy-loads the last videos only after more interaction than scroll rounds can trigger, the scan will now fail clearly as incomplete instead of silently verifying a short queue. That remaining risk is observable through `scanStop`, per-round diagnostics, and missing count fields.
