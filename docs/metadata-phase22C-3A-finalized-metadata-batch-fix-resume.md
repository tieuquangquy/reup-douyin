# Phase 22C-3A Resume

## Implemented

- item-scoped transient state clearing before every batch item
- forced batch target handoff from batch runner to one-item runner
- item-scoped finalized metadata object for commit validation
- local finalized commit guard before backend save
- one extraction retry when finalized/data-integrity state is missing or mismatched
- recoverable item checkpointing instead of stale backend finalized rejection
- additional diagnostics for item lifecycle, aweme identity, retry count, and local commit blocking

## Important behavior

- backend save is blocked when finalized metadata is missing or mismatched
- payload aweme must match target aweme before commit
- `current_aweme` / `selected_aweme` are reset per item
- stale request/response fields are cleared per item
- batch still uses the canonical one-item save/verify pipeline
- no Capture Inbox frontend UI files were modified

## Main files

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Verification focus

Re-test Batch Next 10 with at least one intentionally bad modal/open mismatch and confirm:

- no backend save call happens for the bad item
- retry runs once for the same aweme
- checkpoint is written for the failed item
- later items still use isolated per-item state
- `current_aweme`, `selected_aweme`, `payload_aweme`, and finalized metadata diagnostics stay aligned for the active item
