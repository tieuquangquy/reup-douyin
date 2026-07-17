# Phase 22C-9A Resume Notes

## Active Scan Path Found

Popup Scan Profile dispatches `runScanProfileWorkflow()`, which resolves the active/profile tab and calls `completeProfileVerify()`. That calls `scanWholeProfileTargets()`, which delegates to runtime `scanProfile()`. The popup runtime sends `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE` to the content script. The content script calls `runModalTestProfileScan()`, which runs `collectProfileCardsUntilStable()`.

## Changes Made

- Added a 22C-9A DOM probe in `modalWholeProfileTest.ts`.
- Added preflight polling before scan round 1.
- Added selector hit diagnostics and scroll-container diagnostics.
- Added aweme extraction from `/video/`, `modal_id`, `aweme_id`, and data/attribute fallback text.
- Added explicit failure reasons for grid timeout, aweme extraction failure, login, checkpoint, and empty profile.
- Exposed profile DOM probe status in progress and advanced diagnostics.
- Updated scanner runtime/state-machine markers to `22C-9A`.

## Behavioral Contract

If profile video links/cards are visible, scan round 1 starts and the queue can be built. If no candidates appear before preflight timeout, the scanner reports `profile_grid_not_ready_timeout` with DOM probe details. If login/captcha/checkpoint is detected, the scanner reports that specific blocker instead of `profile_scan_no_round_started`.

## Tests Added

Focused regression coverage was added for:

- aweme extraction from `/video/<id>`
- aweme extraction from `modal_id`
- aweme extraction from `aweme_id`
- aweme extraction from data attributes
- one `/video/` link making the grid ready
- empty profile as terminal state
- scanner source diagnostics for probe/preflight/error classification
- controller zero-round diagnostics carrying `profile_dom_probe`

## Files Touched

- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- this document pair

## UI/Backend Scope

Capture Inbox UI, Review Board, Reup Score, backend APIs, modal metadata extraction, and Start Collecting batch behavior were untouched.

## Next Manual Check

Run Scan Profile on the failing Douyin profile and inspect diagnostics. A failure should now show concrete probe values: `scan_preflight_status`, `scan_grid_ready`, `profile_grid_selector_hits`, `video_link_count`, `awemeIdCount`, `scrollContainerFound`, and `scan_no_round_reason`.
