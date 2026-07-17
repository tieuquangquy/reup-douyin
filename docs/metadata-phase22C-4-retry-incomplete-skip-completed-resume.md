# Phase 22C-4 Retry / Incomplete / Skip Completed Resume

## Implemented

- Canonical queue model now includes actionable statuses: `new`, `pending`, `retry`, `incomplete`, `needs_metadata`, `failed_recoverable`.
- Canonical queue model now includes non-actionable statuses: `backend_verified`, `complete`, `already_collected`, `duplicate`, `skipped`, `failed_permanent`, `extracted`, `saved`.
- Queue entries now carry retry/backend metadata fields required for checkpointing and future reconcile.
- `selectNextActionableTargets` is exported from the controller for focused tests and diagnostics.
- Safe Batch Next 10 uses canonical selection and never selects more than 10 targets per user click.
- Recoverable safe-batch item failures increment retry count and stop automatic retry after two attempts.
- Safe Batch completion now distinguishes “idle with more actionable targets” from `profile_collection_complete`.
- Safe Batch actionable remaining counts now use the full queue, while selected IDs remain capped to the chunk size.
- Saved/backend-verified skip diagnostics are counted separately from complete skips.
- Counters now derive from canonical queue and capture statuses.

## Validation Completed

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Remaining Recommended Follow-up

- Add deeper backend session-item reconcile tests when backend item list shapes are finalized.
- Expand focused test assertions around duplicate precheck/update behavior if backend update endpoint semantics become explicit.

## Manual Retest

1. Scan a profile.
2. Start Batch Next 10.
3. Confirm completed/backend-verified queue items are skipped.
4. Force a recoverable per-item failure and confirm status changes to `retry` with `retry_count = 1`.
5. Retry the same item and confirm `retry_count = 2` then `failed_permanent` after the second recoverable failure.
6. Confirm another Batch Next 10 click continues remaining actionable queue items without auto-running the next chunk.
7. Confirm profile collection completes only when no actionable targets remain.
