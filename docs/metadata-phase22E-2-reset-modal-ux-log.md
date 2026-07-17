# Phase 22E-2 Reset Modal UX Log

Date: 2026-05-10

## Scope

Implemented Phase 22E-2 only: replaced the Douyin Scanner native reset options prompt with a custom in-popup Reset scanner modal.

## Changes

- Added a hidden `role="dialog"` reset modal in `apps/extension-douyin-capture/public/popup.html`.
- Added three reset option cards:
  - `current_run` — Reset current run, marked Safe.
  - `current_profile_rescan` — Rescan this profile, marked Update.
  - `new_profile` — Start new profile, marked Switch.
- Added copy that backend Capture Inbox data, backend sessions, and items are not deleted.
- Added polished popup-friendly modal/card styling in `apps/extension-douyin-capture/public/popup.css`.
- Rewired footer Reset and Advanced maintenance Reset Scanner State to open the modal instead of using the browser reset-options prompt.
- Added Escape, backdrop, Cancel, focus restore, and running/disabled handling.
- Preserved reset execution through existing `resetScannerWorkflowState` modes.
- Added reset diagnostics for mode/result/timestamp and keep/clear flags.
- Updated source-inspection tests in `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`.

## Native Prompt Removal

The scanner reset-options flow no longer calls `window.prompt("Reset options:...")`. The reset choice is now made by selecting one of the in-popup option cards.

`window.confirm` remains only in unrelated maintenance/legacy or destructive flows, not as the primary scanner reset UI.

## Mode Behavior

- `current_run`: keeps profile, queue, session, calibration, and settings; clears active task/locks through existing reset semantics.
- `current_profile_rescan`: keeps profile/session semantics from existing controller behavior and refreshes the scan plan.
- `new_profile`: clears local profile queue/session state while keeping calibration and settings.

## Validation

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed and includes extension build.
