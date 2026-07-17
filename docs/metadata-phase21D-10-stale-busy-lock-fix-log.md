# Phase 21D-10 — Stale busy/running lock fix log

Date: 2026-05-07

## Scope

Phase 21D-10 fixes stale scanner busy/running state that could disable the new scanner UI even when the next recommended action was correctly `Scan Profile`.

## Problem

The popup could show `Next action: Scan Profile` while still disabling the button with `Wait for the current step to finish.` This meant primary action selection was correct, but action gating still trusted stale workflow locks from earlier scanner or harvest state.

## Changes

- Added canonical scanner busy evaluation in `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`.
- Replaced broad action gating checks that treated top-level or stale running states as blocking.
- Wired canonical busy state into scanner view models in `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`.
- Wired popup settings disabling to the same canonical busy selector in `apps/extension-douyin-capture/src/popup.ts`.
- Expanded tests in:
  - `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
  - `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
  - `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Busy selector behavior

`getScannerBusyState(state)` now returns:

```ts
{
  isBusy: boolean,
  busyReason: string | null,
  busySource: string | null,
  isStale: boolean
}
```

Busy is only true for canonical active running sources such as scan/verify, classification, collect, and save states with a non-stale timestamp.

Paused, failed, completed, completed_with_warnings, cancelled/stopped-like idle states, and stale running locks are not treated as blocking.

## Stale lock behavior

A running source is stale when its latest `updated_at` or `started_at` timestamp is older than two minutes. Running sources without timestamps are also treated as stale popup-reload locks.

Stale state returns:

```text
Previous task looks stale. You can start again.
```

and does not disable Scan Profile.

## Reset behavior

Reset continues to preserve calibration while replacing workflow state with an idle scanner state. Tests now verify reset clears scan/classification/collect/save running locks, current target, last error, queue processing flags, and makes Scan Profile enabled again.

## Legacy blocking removed

The new scanner action gate and view model no longer rely on old V2, safe runner, smart capture, or legacy progress state. Stale legacy `harvest.status === "running"` without active timestamps no longer blocks the new scanner UI.

## Validation

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed and included the extension build as part of the test script.
