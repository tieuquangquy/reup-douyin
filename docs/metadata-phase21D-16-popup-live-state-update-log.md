# Phase 21D-16 Popup Live State Update Log

## Scope

Implemented Phase 21D-16 only: fix the Douyin extension popup so the currently open popup updates immediately after the operator clicks Scan Profile.

## Problem

The active popup read canonical Whole Profile Harvest state from `chrome.storage.local`, but rendered snapshots only on popup init or after an awaited controller action completed. `runScanProfileWorkflow` already persisted running and progress states, but the open popup did not subscribe to those changes, so the operator saw no visual transition until closing and reopening the popup.

## Changes

- Added a popup-local live state cache for `WholeProfileHarvestState`.
- Added a render-from-state path so storage/message updates can re-render without another storage read or popup reopen.
- Added optimistic Scan Profile state on click:
  - `status: "verifying"`
  - `phase: "ensuring_content_script"`
  - `workflow.scan.status: "running"`
  - `workflow.active_task: "scan_profile"`
  - `workflow.action_lock: "scan_profile"`
  - debug action fields set to running
- Persisted the optimistic patch to the canonical scanner state key.
- Added `chrome.storage.onChanged` subscription for `WHOLE_PROFILE_HARVEST_STATE_KEY`.
- Added optional runtime message support for `douyinScanner:stateChanged`.
- Added listener cleanup on popup unload.
- Added double-click protection using a local in-flight flag and canonical busy-state checks.
- Added stale running recovery using the existing two-minute scanner stale policy from the readiness selector.
- Extended local Chrome typings for storage and runtime listener cleanup.
- Added tests for popup live-state source wiring, optimistic update behavior, storage/message subscriptions, listener cleanup, stale recovery, duplicate-click guard, and controller progress persistence.

## Non-goals Honored

- No backend API contract changes.
- No UI redesign.
- No classification endpoint changes.
- No modal extractor rewrite.
- No Capture Inbox UI changes.
- No V2 or legacy runtime activation.
- No fake successful scan.

## Validation

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- The test command also ran the extension build as part of the workspace test script.
- Separate typecheck/build commands are still tracked for final Phase 21D-16 validation.
