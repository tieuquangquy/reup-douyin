# Phase 17M Modal Test Waiting Profile Ready Fix Log

## Root cause

Phase 17L correctly made no-reload modal close the primary transition path, but the popup state machine still persisted `waiting_profile_ready` before checking whether the no-reload diagnostics already proved that the profile page was ready. In the live case, the close result already had same-context profile diagnostics and `profile_grid_candidate_count = 62`, but the run could remain parked at `waiting_profile_ready` and the top-level detector banner could show a stale global detector error.

## Profile ready condition

The Phase 17M readiness predicate treats the profile as ready after modal close when all of the following are true:

1. `current_url` matches the expected profile URL, or is the same `/user/{profile_id}` URL without `modal_id`.
2. `modal_id_present === false`.
3. `page_type === "profile"`.
4. `document_ready_state` is `interactive` or `complete`.
5. At least one profile-grid signal is present: `profile_grid_candidate_count > 0`, `candidate_card_count > 0`, `video_aweme_candidate_count > 0`, or `grid_container_count > 0`.

The reported live case with `content_script_status = "same_context"`, `page_type = "profile"`, no `modal_id`, `document_ready_state = "complete"`, and `profile_grid_candidate_count = 62` is ready.

## No-reload same-context behavior

When no-reload modal close succeeds and the readiness predicate passes, the modal whole-profile test now moves directly from `waiting_profile_ready` into `scanning_profile`. It sets profile navigation/grid statuses to success, sets scan statuses to running, and continues into harvest-plan building without requiring detector reconnect. Detector reconnect remains reserved for hard-navigation fallback.

## Stale detector error suppression

The popup tracks the latest isolated modal whole-profile test run. If an active run has same-context profile diagnostics with no modal ID, the top-level stale detector banner text `Could not execute the Douyin detector in this tab.` is suppressed and replaced with the current modal test phase label.

## Tests run

To be filled by the command run in this phase:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live retest steps

1. Open a Douyin modal URL in the active tab: `/user/{profile_id}?modal_id={aweme_id}`.
2. Open the extension popup.
3. In Advanced / Beta, keep Modal Whole Profile Test in verify-only mode.
4. Click Test Modal → Whole Profile Harvest.
5. Confirm the modal closes without hard navigation when same-context transition works.
6. Confirm the run does not remain at `waiting_profile_ready` when diagnostics show profile page, no `modal_id`, and non-zero grid candidates.
7. Confirm the phase advances through `scanning_profile` and `building_harvest_plan` to `completed` without creating visible Capture Inbox items or starting full-modal-harvest.
