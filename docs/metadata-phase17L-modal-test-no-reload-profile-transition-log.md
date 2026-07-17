# Phase 17L Modal Test No-Reload Profile Transition Log

## Root cause

Phase 17K made the Modal Whole Profile Test leave `/user/{profile_id}?modal_id={aweme_id}` by hard navigation to `/user/{profile_id}` and then reconnect the detector/content script. On the live site this can unload the old content script and leave the popup runtime repeating a reconnect status without a deterministic completion or failure path.

## No-reload modal close strategy

Phase 17L makes no-reload de-modal transition the primary path for the isolated beta test. The popup now persists the test run in `closing_modal_without_reload`, executes `closeModalToProfileWithoutReload(profileUrl, sourceModalAwemeId)` in the active tab, and tries:

1. `history.pushState({}, "", profileUrl)` plus `PopStateEvent("popstate")` and a custom transition event.
2. `history.back()` when history exists.
3. synthetic Escape keydown/keyup events.
4. detectable visible close/back controls.

Success requires the active URL to match the expected `/user/{profile_id}` path with no `modal_id`, the inferred page type to be profile, and diagnostics to show the same execution context remained available.

## Profile readiness behavior

After no-reload close succeeds, the test enters `waiting_profile_ready`, waits for a URL without `modal_id`, ensures the content script responds, and runs the existing profile-grid scanner. It then enters `scanning_profile` and `building_harvest_plan` using the existing verify-only harvest-plan request path.

## Hard navigation fallback

Hard navigation is now fallback-only. If all no-reload close strategies fail, the popup persists `hard_navigating_to_profile`, records `hard_navigation_started_at`, calls `chrome.tabs.update(tabId, { url: profileUrl })`, waits for a `tabs.onUpdated` complete signal when available, and then enters `reconnecting_after_hard_navigation`.

## Reconnect timeout behavior

Fallback reconnect is bounded to 3 attempts and 10 seconds total. Profile load waits are bounded to 20 seconds, and stale resume phases fail by phase age. Failures persist `failed` with `reconnect_timeout` or `content_script_reconnect_failed_after_hard_navigation`; the UI shows a precise red message instead of looping forever.

## Diagnostics fields

Failure diagnostics include `current_url`, `expected_profile_url`, `tab_id`, `reconnect_attempts`, `last_ping_error`, `last_injection_error`, `content_script_status`, `detector_status`, and `phase_elapsed_seconds`. No-reload diagnostics include attempted strategies, document ready state, current URL, modal presence, profile page type, and card candidates.

## Tests run

Planned command set for this phase:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live retest steps

1. Open Douyin to `/user/{profile_id}?modal_id={aweme_id}`.
2. Open the extension popup.
3. Expand Advanced / Beta.
4. Click Test Modal → Whole Profile Harvest.
5. Confirm status changes through Closing modal..., Waiting for profile grid..., Scanning profile..., and Building harvest plan... without a hard page reload when SPA de-modal succeeds.
6. If no-reload close fails, confirm fallback shows Hard navigating to profile... and Reconnecting content script... Attempt 1/3 through at most Attempt 3/3.
7. Confirm the run completes or fails with a precise red reason and never remains indefinitely at reconnecting detector.
