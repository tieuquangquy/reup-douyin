# Phase 17L Modal Test No-Reload Profile Transition Resume

## Scope

Phase 17L is scoped to the Modal Whole Profile Test in `apps/extension-douyin-capture` plus tests and docs. It does not alter backend flows, Tile Gallery, modal metrics extraction, calibration, CDP/debug behavior, production Smart Capture state, or full-modal-harvest execution.

## State machine

The isolated runtime key remains `douyinModalWholeProfileTestRun`. Phase 17L normalizes the state machine to:

- `starting`
- `closing_modal_without_reload`
- `waiting_profile_ready`
- `scanning_profile`
- `building_harvest_plan`
- `hard_navigating_to_profile`
- `reconnecting_after_hard_navigation`
- `detecting_profile`
- `completed`
- `failed`

Resume Modal Test continues `closing_modal_without_reload`, `waiting_profile_ready`, `hard_navigating_to_profile`, and `reconnecting_after_hard_navigation`. If a phase is stale, resume fails the run with `reconnect_timeout` instead of retrying forever.

## Primary path

The popup saves the run before attempting de-modal. It then calls `closeModalToProfileWithoutReload(profileUrl, sourceModalAwemeId)` in the tab. On success, the same tab/context waits for profile readiness and scans the profile grid before building the harvest plan. This avoids the Phase 17K detector loss caused by making hard reload the primary path.

## Fallback path

Hard navigation is used only when no-reload close returns failure. The fallback persists `hard_navigating_to_profile`, records the expected profile URL and hard navigation timestamp, performs `chrome.tabs.update`, waits for a completion signal or bounded URL wait, then runs content-script ping/inject/ping retries.

## Timeout and diagnostics

Reconnect attempts are limited to 3 and 10 seconds total. Profile load wait is limited to 20 seconds. Failure diagnostics persist enough detail for live debugging: active/current URL, expected profile URL, tab id, reconnect attempts, ping and injection errors, content-script status, detector status, and elapsed phase seconds.

## UI expectations

No-reload flow shows:

- Closing modal...
- Waiting for profile grid...
- Scanning profile...
- Building harvest plan...

Fallback flow shows:

- Hard navigating to profile...
- Reconnecting content script... Attempt 1/3
- Reconnecting content script... Attempt 2/3
- Reconnecting content script... Attempt 3/3

Failure shows a precise red reason such as: No-reload modal close failed; hard navigation reconnect failed after 3 attempts.

## Guardrails

The beta test writes only `douyinModalWholeProfileTestRun`, does not create visible Capture Inbox items in verify-only mode, does not call full-modal-harvest, does not reset calibration, and does not mutate production Smart Capture state.

## Live retest checklist

1. Start from a modal profile URL with `modal_id`.
2. Run Test Modal → Whole Profile Harvest.
3. Verify the URL changes to profile without `modal_id` without a full reload when no-reload close succeeds.
4. Verify the profile grid appears and scanning starts.
5. Verify harvest-plan building completes with beta runtime summary.
6. If fallback is triggered, verify at most 3 reconnect attempts and then completed or failed state.
7. Verify Reset Modal Test clears only the isolated beta runtime.
