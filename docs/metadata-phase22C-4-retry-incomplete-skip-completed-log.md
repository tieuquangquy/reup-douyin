# Phase 22C-4 Retry / Incomplete / Skip Completed Log

## Scope

Implemented Phase 22C-4 queue reliability within the Douyin capture extension only. The work keeps Safe Batch Next 10 capped at one user-triggered chunk and keeps Capture Inbox UI/frontend behavior out of scope.

## Changes

- Added canonical queue statuses for retry, incomplete, backend verified, duplicate, already collected, and failed permanent states.
- Added queue item fields for retry count, backend item id, metadata status, last attempt timestamp, saved timestamp, thumbnail, and caption.
- Added `selectNextActionableTargets` with priority ordering and a max retry cap of 2.
- Updated Safe Batch selection to derive targets from canonical actionable statuses instead of broad pending filters.
- Updated recoverable failure handling to mark retry targets with retry count and failed permanent once max retry is reached.
- Updated finish behavior so a batch returns to idle when actionable targets remain and completes the profile only when no actionable targets remain.
- Updated actionable remaining counts to count the full queue instead of the capped display/selection window.
- Updated saved/complete skip diagnostics so saved/backend-verified items are not double-counted as completed skips.
- Updated popup counter derivation to use canonical queue and capture statuses, including failed and processing items.
- Updated canonical queue builders to preserve backend item metadata on queue entries.
- Updated whole-profile harvest tests for Phase 22C-4 safe-batch chunk semantics and backend verification reconciliation.

## Validation

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.

## Notes

Backend implementation files were not changed. Duplicate prevention remains based on extension-side skip/reconcile behavior and existing backend idempotent save verification contracts; no new backend endpoint was introduced in this scoped extension-only pass.
