# Phase 22A-3 Cooperative Pause Runner Fix Log

## Scope

Phase 22A-3 fixes active Start Collecting pause behavior in the Douyin capture extension only. The change is scoped to the whole-profile scanner collection runner, popup controls, view-model state, diagnostics, and focused tests.

## Intent

Pause during an active collection run is now cooperative and visible immediately:

- The active Pause button records a pause request before waiting for the controller action to finish.
- The collection workflow enters `pausing` immediately.
- The UI renders `Pausing...` while the runner reaches a safe checkpoint.
- The runner does not close the tab or interrupt an in-progress extraction/checkpoint write.
- Resume continues from the next pending queue target after a paused checkpoint.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
  - Added canonical `pausing` workflow collection status support.
  - Added canonical pause fields under harvest state: `pause_requested`, `pause_requested_at`, `pause_acknowledged_at`, `pause_reason`, and related pause message/resume fields.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
  - Treats `pausing` as an active collection state.
  - Keeps Start Collecting unavailable while a pause is pending.
  - Presents Pause/Pausing/Resume readiness consistently.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - Added cooperative pause request handling via `requestPauseCollecting`.
  - Preserves pre-existing pause requests when Start Collecting begins.
  - Clears pause flags on resume so resumed runs do not immediately pause again.
  - Writes immediate pause diagnostics and the legacy runtime pause bridge.
  - Adds safe pause checks around target boundaries and checkpoint boundaries.

- `apps/extension-douyin-capture/src/popup.ts`
  - Force-wired the visible active pause/resume button with the marker `22A-3 ACTIVE SCANNER PAUSE BUTTON`.
  - Added immediate popup-side pause diagnostics and optimistic `pausing` state storage before async controller completion.
  - Routes the footer Pause/Resume button by canonical state rather than button text.

- `apps/extension-douyin-capture/public/popup.html`
  - Marked the active scanner pause button location with `22A-3 ACTIVE SCANNER PAUSE BUTTON`.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
  - Added `pausing` UI handling for header, primary action, footer button, safety state, alert, progress detail, and diagnostics rows.

- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
  - Added cooperative pause coverage for pre-requested pause during Start Collecting.
  - Verifies pause-request diagnostics and that the runner stops before completing the requested batch.

- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
  - Added view-model assertions for `Pausing...` state.
  - Added source-level assertions for active pause button marker, explicit state-based routing, and immediate pause diagnostics.

## Safe Checkpoints

The collection runner now checks for pause requests at safe boundaries:

1. Before a target is processed.
2. After opening or preparing the target/modal.
3. After extraction attempt boundaries.
4. After backend/local checkpoint persistence.
5. Before moving to the next target.

The pause acknowledgement writes a durable paused state and records checkpoint diagnostics. The current target is not interrupted mid-write.

## Diagnostics

Pause click and runner acknowledgement now expose stable diagnostics including:

- `last_action_clicked = "pause"`
- `last_action_result = "clicked"`
- `pause_requested = true`
- `pause_requested_at`
- `pause_source`
- `pause_acknowledged_at`
- `last_pause_check_checkpoint`
- `runner_location`

## Validation

Completed before this log was written:

```txt
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
```

Result: passed.

```txt
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Result: passed. The test command also executed the extension build step internally as part of the existing workspace test flow.

A standalone build command is still run separately for the Phase 22A-3 final checklist.
