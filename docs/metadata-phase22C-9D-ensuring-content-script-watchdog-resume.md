# Phase 22C-9D Ensuring Content Script Watchdog Resume

## Status
Phase 22C-9D hardens Scan Profile so `ensuring_content_script` cannot remain running indefinitely.

## Files Changed
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase22C-9D-ensuring-content-script-watchdog-log.md`
- `docs/metadata-phase22C-9D-ensuring-content-script-watchdog-resume.md`

## Manual Retest
1. Load the extension build.
2. Open a Douyin profile page and click Scan Profile.
3. Confirm the scan either reaches a verified queue or fails with a clear tab/content-script/timeout error.
4. Confirm diagnostics show scan run id, watchdog state, tab resolve result/strategy/URL, content-script ensure status, ping result, injection result, and finalization result.
5. Confirm scanner busy, active task, and action lock clear after success or failure.

## Expected Failure Behavior
- Missing Douyin tab: explicit tab resolution error.
- Content script unavailable: explicit content script error.
- Ping timeout: explicit `content_script_ping_timeout` diagnostics.
- Injection failure: explicit `scan_content_script_injection_failed` diagnostics.
- Controller watchdog: final failed state with `scan_profile_ensure_content_script_timeout` and cleared locks.
