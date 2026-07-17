# Phase 18I-J1 Resume

## Goal

Make Whole Profile Harvest readiness and popup action gating deterministic.

## Canonical selectors

- `getWholeProfileHarvestReadiness(state)`
- `getWholeProfileHarvestActionState(state)`
- `getNextRecommendedAction(state, readiness)`

File:

- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`

## Key fix

Do not trust persisted `state.layer.dry_run_ready` for UI rendering.

Use:

- dry-run status
- dry-run pass/fail counts
- extracted results
- backend session state
- payload preview state
- payload guard state

## Popup behavior

- `renderWholeProfileHarvestProductState()` now computes readiness once and uses it for:
  - progress summary
  - button enable/disable
  - stop/resume visibility
  - next action helper

## Minimal new controls

- `Prepare Backend Session`
- `Build Payload Preview`

These are wired through controller helpers so the popup can gate backend-preparation steps explicitly.

## Tests run

- extension `typecheck`
- extension `test`
- extension `build`

## Manual retest focus

1. Verify profile.
2. Run a dry-run sample.
3. Confirm `Dry-run ready = yes` when pass count is positive.
4. Confirm Flush buttons stay disabled until session / payload preview / guard prerequisites are ready.
5. Confirm Resume is hidden while idle and shown only for paused states.
