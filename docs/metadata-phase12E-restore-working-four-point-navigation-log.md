# Phase 12E Restore Working Four-Point Navigation Log

## Scope

Phase 12E is limited to `apps/extension-douyin-capture` plus extension tests and documentation. No backend, web app, database schema, CDP/debug workflow, crawler, broad metric extraction, or fake metric changes were made.

## Git/history audit result

The required git-history audit was attempted first with `git log --oneline -- apps/extension-douyin-capture` and targeted `git grep` searches, but the workspace is not currently recognized as a Git repository by the terminal. The audit therefore used the available phase logs and current extension source/tests:

- `docs/metadata-phase11G-calibrated-next-navigation-log.md`
- `docs/metadata-phase12C-recover-working-four-point-harvest-log.md`
- `docs/metadata-phase12D-four-point-navigation-loop-fix-log.md`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`

No commit hash could be recovered because `.git` is unavailable in the working directory. The closest documented working function lineage is Phase 12C's automatic navigation order, which preserved existing next-control discovery before keyboard/scroll fallback. Phase 12D then inverted that behavior to keyboard-first navigation.

## Exact regression root cause

The live Phase 12E timeout was caused by Phase 12D changing `navigateNextModalAutomatically()` to keyboard-first behavior. On the user's Douyin modal page, keyboard/wheel events did not reach the same handlers that the earlier four-point workflow depended on, and the visible next-control heuristic was only attempted last. The result was a real modal that extracted and flushed successfully but stayed on the same aweme until `modal_id_change_timeout`.

The regression is not metric extraction, backend flushing, capture-session binding, or four-point calibration. It is the automatic next-video dispatch path after `queued_item` / flush.

## Restored production four-point contract

Production calibration remains exactly four metric points:

1. `like_count`
2. `comment_count`
3. `favorite_count`
4. `share_count`

`next_video_button` remains optional legacy/debug compatibility only. It is not required for Smart Capture & Harvest, Probe PASS, resume, or normal progress UI.

## Restored automatic navigation behavior

`navigateNextModalAutomatically()` now restores the documented working order from Phase 12C:

1. Existing modal next-control discovery/click.
2. Focus page/video and send `ArrowDown`.
3. Send `PageDown`.
4. Send wheel down.
5. Focus again and retry `ArrowDown`.

The keyboard and wheel events are now dispatched to multiple Douyin-observable targets instead of only the current active element:

- `window`
- `document`
- `document.activeElement`
- active modal video
- `document.body`
- `document.documentElement`

This restores compatibility with pages where Douyin listens globally for modal-feed navigation. The function still waits for the detected aweme/modal id to change after each attempt and only succeeds when the current id differs from the previous id.

## Modal ID detection

The existing detection remains unchanged:

- `URLSearchParams(location.search).get("modal_id")`
- `/video/{aweme_id}` path fallback

`waitForModalIdChange()` continues polling every 300 ms and succeeds only when a non-empty aweme id differs from the previous aweme id.

## Duplicate handling

The current harvested item is not counted as a duplicate immediately after extraction. Duplicate count only increments when a same aweme is observed after a navigation attempt has been recorded.

## Posted and view fields

No posted-field extraction behavior was changed. No fake `view_count` behavior was added.

## Tests updated

`apps/extension-douyin-capture/src/modalHarvest.test.ts` now verifies the restored automatic navigation path:

- existing modal next-control click happens before keyboard fallbacks
- `ArrowDown` is dispatched to `window`
- `ArrowDown` is dispatched to `document`
- wheel fallback remains present
- navigation timeout happens only after restored attempts

Existing four-point tests remain in place for calibration validity, Probe PASS, no `next_video_button` requirement, no normal `Next point` display, state transitions, timeout flushing, resume, and duplicate source guards.

## Tests run

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

The `test` script also runs the extension build and dist module resolution check.

## Live retest steps

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Open a Douyin profile/search grid and open a video modal with `modal_id` in the URL.
3. Confirm calibration is four points only: like, comment, favorite, share.
4. Click Probe Current Modal Metrics and confirm PASS.
5. Click Smart Capture & Harvest with a target greater than 1.
6. Confirm Video 1 extracts duration and all four counts.
7. Confirm backend flush increments `updated_count` / `flushed_count` when flush runs.
8. Confirm progress moves through `queued_item`, `loading_next_video`, and `waiting_modal_change`.
9. Confirm the extension advances automatically to a different `modal_id` / aweme id.
10. Confirm Video 2 becomes `extracting_metrics` and `current_index` advances.
11. Confirm the popup does not show `Next point missing` and does not ask for five-point calibration.
