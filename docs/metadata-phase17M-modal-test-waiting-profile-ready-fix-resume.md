# Phase 17M Modal Test Waiting Profile Ready Fix Resume

## Scope

Phase 17M is limited to the isolated Modal Whole Profile Test in `apps/extension-douyin-capture` plus tests and docs. It does not change backend behavior, Tile Gallery, modal metrics extraction, calibration, CDP/debug workflow, production Smart Capture, full-modal-harvest, or visible Capture Inbox writes.

## What changed

- Added a Phase 17M runtime schema marker for the isolated modal whole-profile test state.
- Added `running` as a modal test step status so profile scan fields can reflect pending, running, success, or failed.
- Added the explicit stuck-state reason `profile_grid_not_ready_or_state_machine_stuck`.
- Added a profile-ready predicate for no-reload modal close diagnostics.
- Added direct continuation from ready no-reload diagnostics into profile scanning.
- Added resume handling for `waiting_profile_ready` that scans immediately if stored diagnostics already prove readiness.
- Added a 20 second stale `waiting_profile_ready` timeout with clear diagnostics.
- Added stale global detector banner suppression during active same-context modal test runs.

## Profile ready condition

A no-reload close result is ready if the current page is the expected profile URL or matching `/user/{profile_id}` without `modal_id`, the page is a profile, the document is interactive or complete, and a grid/card signal exists. The live `profile_grid_candidate_count = 62` case is ready.

## Resume behavior

If the popup reopens or the button is clicked while the stored run is in `waiting_profile_ready`, the run is resumed rather than replaced. If stored diagnostics prove readiness, it continues to `scanning_profile` immediately. If they do not, it waits for profile readiness. If the phase has been waiting for more than 20 seconds, the run fails with `profile_grid_not_ready_or_state_machine_stuck` and includes URL, expected URL, modal flag, page type, candidate count, phase start, and elapsed time diagnostics.

## No-reload same-context behavior

Same-context no-reload success does not require detector reconnect. Reconnect is only used by the hard-navigation fallback path.

## Stale detector error suppression

When the active modal test diagnostics show same-context content script, profile page, and no modal ID, the global detector error banner is not allowed to overwrite the modal test phase status.

## Tests run

To be filled by the command run in this phase:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live retest steps

1. Start on `/user/{profile_id}?modal_id={aweme_id}`.
2. Click Test Modal → Whole Profile Harvest in verify-only mode.
3. Watch for `Closing modal...`, then immediate `Scanning profile...` if grid candidates already exist.
4. Confirm no top-level stale detector error appears while same-context profile diagnostics are present.
5. Confirm the run completes after harvest-plan verification and only `douyinModalWholeProfileTestRun` is written by the verify-only test.
