# Phase 17K Modal Test Navigation Reconnect Resume

## Summary

Phase 17K makes Modal Whole Profile Test resilient to modal URL to profile URL navigation by persisting an isolated run before navigation, stopping the current popup handler, and resuming only after the profile page can reconnect the Douyin detector/content script.

## Changed areas

- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`
  - Runtime schema updated to `phase17k_modal_test_navigation_resume`.
  - Added explicit modal test phases.
  - Added navigation and reconnect fields: `expected_profile_url`, `navigation_started_at`, `reconnect_attempts`, and `last_reconnect_error`.
  - Added failure reason `content_script_reconnect_failed_after_profile_navigation`.
- `apps/extension-douyin-capture/src/popup.ts`
  - Initial modal test click persists run state before profile navigation.
  - The initial click does not scan after `chrome.tabs.update()`.
  - Added `resumeModalWholeProfileTestAfterNavigation()`.
  - Reconnect button and popup initialization can resume waiting runs.
  - Test button changes to `Resume Modal Profile Test` for navigation/reconnect phases.
  - Resume reconnects/injects the content script, reruns detector, confirms profile context, then scans/builds the harvest plan.
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
  - Added source assertions covering state-before-navigation, no same-call scan, resume wiring, reconnect retry/backoff, profile URL matching, stale `modal_id` re-navigation, reset isolation, and verify-only guardrails.

## Non-goals preserved

- No backend changes.
- No Tile Gallery changes.
- No modal metrics extraction changes.
- No calibration changes.
- No CDP/debug workflow reintroduction.
- Verify-only still does not start production harvest, create visible Capture Inbox items, or flush full-modal-harvest.

## Operational behavior

If a stored run is in `navigating_to_profile`, `waiting_profile_load`, or `reconnecting_content_script`, the popup treats the modal test action as resume rather than creating a conflicting new run. The reconnect flow retries three times with backoff before marking the isolated run failed.

## Required verification

Run these commands from the repository root:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live verification

Use the known modal URL, click `Test Modal → Whole Profile Harvest`, allow navigation to the profile URL, then resume from the popup. The expected success path is navigation state saved, detector reconnect, detector rerun as profile, profile scan, harvest-plan build, and verify-only completion.
