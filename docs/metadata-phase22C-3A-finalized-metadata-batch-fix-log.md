# Phase 22C-3A Log

## Scope

Fix Batch Next 10 item isolation so a batch item cannot reuse stale modal identity or stale per-item diagnostics when committing to backend Capture Inbox.

## Why backend rejected finalized metadata

The safe batch runner already called the canonical one-item flow, but the one-item flow still selected its own pending target from live state and reused item-scoped diagnostics across items. In batch mode this allowed:

- selected target drift between batch loop and one-item runner
- stale `current_aweme` / `selected_aweme` diagnostics
- stale item-scoped request/response fields
- backend commit attempts after identity/finalization mismatch

Backend correctly rejected these cases with `finalized_metadata_required`.

## Current/selected aweme drift root cause

The batch loop selected a target, then `runOneItemCollectAndSave()` selected the first pending queue item again from state. After a recoverable item failure this could point back at the wrong aweme. The batch runner now passes `batch_target_aweme_id`, and the one-item runner must honor that exact target.

## Per-item lifecycle

Each batch item now emits item-scoped lifecycle diagnostics:

- `transient_cleared`
- `target_set`
- `modal_opening`
- `extracting`
- `metadata_finalized`
- `payload_guarded`
- `backend_saving`
- `backend_saved`
- `backend_verified`
- `done`

Failures also record:

- `item_stage_failed`
- `item_stage_error`
- `item_stage_aweme`

## Finalized metadata guard

Before backend save, the one-item runner now checks:

- finalized metadata exists
- finalized metadata is marked finalized
- finalized metadata aweme matches target aweme
- current/selected/payload aweme all match target aweme
- actual modal URL still matches target aweme
- required fields passed local checks
- payload guard passed

If any check fails, backend save is blocked locally and diagnostics record the block reason.

## Retry-once behavior

When finalized metadata is missing or mismatched for the current target:

1. backend save is blocked locally
2. the modal is reopened for the same aweme
3. extraction runs once more
4. finalized guard runs again

If retry still fails, the item is checkpointed as a recoverable failure for the batch loop to handle by policy.

## Batch recovery policy

Recoverable finalized/data-integrity item failures do not go through the legacy whole-profile runner and do not silently call backend save. The batch runner:

- preserves queue/session/checkpoint state
- records the failed item as recoverable
- stops on repeated failure policy instead of stale backend rejection

## Tests run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
