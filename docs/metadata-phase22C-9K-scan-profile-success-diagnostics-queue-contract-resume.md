# Phase 22C-9K - Scan Profile Success Diagnostics and Queue Contract Resume

## Status
- Phase 22C-9K implemented for diagnostics and queue count clarity only.
- Active scan path versions are expected to report 22C-9K.
- DOM probe display should report completed for ok plus completed_at, not none.

## Key Files
- apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts
- apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts
- apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts
- apps/extension-douyin-capture/src/background.ts
- apps/extension-douyin-capture/src/popup.ts
- apps/extension-douyin-capture/src/contentScript.ts
- apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts
- apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts

## Manual Retest
1. Reload the extension build.
2. Open a Douyin profile page with visible videos.
3. Click Scan Profile.
4. Confirm status verified, phase verified, profile scan ready yes, last scanner result success, active task none, action lock none.
5. Confirm Scanner runtime version 22C-9K, state machine version 22C-9K, scan controller version 22C-9K-scan-controller, and scan action trace version 22C-9K.
6. Confirm Profile DOM probe status completed when message is ok and completed_at exists.
7. Confirm diagnostics show discovered, normalized, duplicate, invalid, already collected, eligible, queue total, batch limit, batch pending, batch mode, and queue limit reason.
8. Confirm Primary action remains Start Collecting when profile scan, calibration, and extraction are ready.

## Queue Semantics
- Canonical queue behavior is intentionally preserved.
- Batch pending is calculated from the current queue using the same next actionable selection semantics as Start Collecting.
- A lower queue/pending number than discovered is explained by profile_queue_limit_reason rather than changing collection behavior.
