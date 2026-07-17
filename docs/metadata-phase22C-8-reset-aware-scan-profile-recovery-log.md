# Phase 22C-8 Reset-aware Scan Profile recovery log

## Scope

Phase 22C-8 updates the Douyin extension scanner reset and Scan Profile recovery path only. Backend, Capture Inbox, Review Board, Reup Score, calibration removal, and batch collection behavior are intentionally unchanged.

## Audit summary

Reset entry points found:

- `popup.ts`: reset modal dispatches `current_run`, `current_profile_rescan`, and `new_profile` through `resetWholeProfileHarvestStateFromPopup`.
- `wholeProfileHarvest/controller.ts`: `resetScannerWorkflowState` delegates to `resetHarvest`.
- `extensionReset.ts`: extension-level harvest/factory reset clears broader storage keys but is separate from the scanner workflow reset modal.
- `contentScript.ts`: full-modal harvest runtime reset handlers clear content-script harvest runtime state.

Stale state risks found:

- Current-run reset intentionally preserves scan/classification/queue/session state.
- Rescan/new-profile reset already rebuilt from idle state, but there was no named scan cleanup helper or explicit expected-count unknown diagnostic.
- Scan completeness guard lived in `completeProfileVerify`; `profile_scan_incomplete` was possible only after scan result evaluation, but the phase requirement now explicitly gates it behind `scan_rounds > 0`.

## Changes

- Added `clearProfileScanState(state, reason, at)` in `wholeProfileHarvest/controller.ts`.
- Applied the helper to non-current-run reset modes (`current_profile_rescan`, `new_profile`, `full_local_reset_dev_only`).
- The helper clears profile scan targets/details, classification, target status, dry-run state, queue, queue preview, planned total, current index/current aweme, saved/failed/skipped/pending counters, processed count, checkpoints, results, and failure summary.
- Reset diagnostics now include `expected_profile_video_count: null` and `expected_count_source: "unknown_after_reset"` so the next Scan Profile recomputes from the live page.
- Tightened completeness guard to require `scan.scan_rounds > 0` before `profile_scan_incomplete` can be raised.

## Validation added

- `wholeProfileHarvest.test.ts` imports and directly tests `clearProfileScanState`.
- Rescan reset assertions now verify scan rounds, targets, pending count, and expected count are cleared.
- Source-contract assertion confirms `profile_scan_incomplete` requires `scan.scan_rounds > 0`.
