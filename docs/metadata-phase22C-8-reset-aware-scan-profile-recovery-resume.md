# Phase 22C-8 Reset-aware Scan Profile recovery resume

## What changed

Phase 22C-8 makes Rescan current profile and Start new profile reset paths explicitly clear stale Scan Profile state before the next scan starts.

Key files:

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Operator behavior

After Reset:

- Rescan current profile keeps the profile URL and calibration/settings, but clears old scan targets, classification, queue, session linkage, expected count, pending count, current index, and current aweme.
- Start new profile uses the detected current profile URL when available, preserves calibration/settings, and starts with an empty scan plan.
- Current-run reset keeps the existing queue/session by design and only clears transient running/lock state.

## Diagnostics to check

In copied scanner diagnostics after rescan/new-profile reset, expect:

- `reset_mode` is `current_profile_rescan` or `new_profile`.
- `profileScanReady` is `false`.
- `classificationReady` is `false`.
- `collectQueueReady` is `false`.
- `queueCount` is `0`.
- `profile_scan.diagnostics.expected_profile_video_count` is `null`.
- `profile_scan.diagnostics.expected_count_source` is `unknown_after_reset`.

## Regression guard

`profile_scan_incomplete` now requires at least one completed scan round. A zero-round scan failure should surface as `profile_scan_runner_not_started` or an earlier preflight/navigation/readiness error instead of `profile_scan_incomplete`.

## Suggested manual QA

1. Open a Douyin profile with visible videos.
2. Run Scan Profile successfully.
3. Open Reset and choose Refresh profile.
4. Run Scan Profile again without reloading the extension.
5. Confirm it starts from a clean state and does not immediately fail with `profile_scan_incomplete` while scan rounds are `0`.
6. Repeat from a modal/video URL and confirm navigation/preflight still moves back to the profile page before scanning.
