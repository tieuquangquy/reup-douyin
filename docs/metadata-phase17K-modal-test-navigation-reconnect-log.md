# Phase 17K Modal Test Navigation Reconnect Log

## Root cause

The Modal Whole Profile Test resolved the modal URL to the profile URL correctly, but the popup kept executing scan and capture work in the same JavaScript call stack immediately after `chrome.tabs.update()`. During a real Douyin modal-to-profile navigation, the previous content-script context is destroyed and the new profile document may not have a ready content script yet. The old flow could therefore surface the generic detector/direct-execution failure before reconnect/injection had a chance to run.

## Two-phase flow

Phase 17K changes the isolated `douyinModalWholeProfileTestRun` runtime to schema `phase17k_modal_test_navigation_resume` and records explicit phases:

- `starting`
- `navigating_to_profile`
- `waiting_profile_load`
- `reconnecting_content_script`
- `detecting_profile`
- `scanning_profile`
- `building_harvest_plan`
- `completed`
- `failed`

On first click, the popup now saves `source_modal_url`, `source_modal_aweme_id`, `resolved_profile_url`, `expected_profile_url`, `navigation_started_at`, status `running`, and phase `navigating_to_profile`, then navigates to the resolved profile URL and stops that handler. It does not scan the profile in that call stack.

## Resume after navigation

Resume runs from popup open, Reconnect Douyin Tab, or pressing the modal test button again while the run is in a waiting/reconnect phase. It reads the stored run, verifies the active tab is on the expected Douyin profile path, accepts harmless query/hash differences, and treats a lingering `modal_id` as stale modal state that triggers one re-navigation to the expected profile URL.

## Reconnect retry behavior

After navigation, resume calls `ensureDouyinContentScriptReady(tabId, { forceInject: true, tabUrl })`, retrying with backoff values of 500 ms, 1200 ms, and 2500 ms. When ready, it reruns the detector with `runDetectorWithReconnect(false)` and requires the detector page context to be `profile` before scanning.

## Diagnostics

The stored run tracks `reconnect_attempts`, `last_reconnect_error`, and failure diagnostics including `tabId`, `current_url`, `expected_profile_url`, `last_chrome_error`, `content_script_status`, and `detector_status`. During navigation/reconnect phases the UI shows `Profile page is loading. Reconnecting detector...`; only after retries fail does it show `Could not reconnect content script after navigating to profile.` with reason `content_script_reconnect_failed_after_profile_navigation`.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`

## Live retest steps

1. Reload the unpacked extension.
2. Open the Douyin modal URL containing `modal_id`.
3. Open the extension popup.
4. Click `Test Modal → Whole Profile Harvest`.
5. Confirm the tab navigates to the profile URL without `modal_id`.
6. Reopen the popup if it closed during navigation, or click `Resume Modal Profile Test`.
7. Confirm the panel advances through waiting, reconnecting, detector ready, scanning, and building harvest plan phases.
8. Confirm verify-only completion does not create visible Capture Inbox items and does not flush full-modal-harvest.
