# Phase 18I-G One-Item Backend Flush Log

## Scope

Implemented Phase 18I-G for the extension whole-profile harvest flow only: allow the operator to flush exactly one validated canonical payload preview to the backend, verify that the backend created or updated a Capture Inbox item for that aweme id, and preserve the no-batch-flush guardrail. This phase does not enable full queue backend flush, does not change API contracts, and does not switch to legacy or V2 staged harvest runtimes.

## Completed Changes

### Extension Runtime
- Added persisted one-item backend flush state in [`WholeProfileHarvestState`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:192) under [`harvest.backend.one_item_flush`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:267) for status, request/response summaries, verification status, Capture Inbox item id, and operator-visible error details.
- Added one-item flush request execution and verification flow in [`flushOneItemFromPayloadPreview()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:686).
- Added backend response classification in [`classifyOneItemFlushError()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:663) so one-item flush now distinguishes:
  - [`capture_session_not_found`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:93)
  - [`backend_finalized_metadata_required`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:95)
  - [`backend_secret_guard_rejected`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:107)
  - generic [`backend_schema_rejected`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:106)
- Added explicit payload-preview preflight errors in [`errors.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:94) so missing or stale validated preview state no longer collapses into generic verify-required wording.
- Reused existing readback support through [`listCaptureSessionItems()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:642) to verify that the flushed aweme id appears in the current capture session.

### Popup / Progress / Operator Messaging
- Added the operator action button [`#flushOneItemButton`](apps/extension-douyin-capture/public/popup.html:78) in [`popup.html`](apps/extension-douyin-capture/public/popup.html).
- Wired the popup action through [`flushOneItemFromPopup()`](apps/extension-douyin-capture/src/popup.ts:313) and the popup runtime in [`createWholeProfilePopupRuntime()`](apps/extension-douyin-capture/src/popup.ts:380).
- Added one-item flush progress rows in [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3):
  - `One-item flush`
  - `One-item verify`
  - `One-item flush error`
- Preserved the no-batch rule by only exposing a single-item action and by keeping the active harvest path in extraction-only mode until an explicit operator-triggered one-item flush is requested.

### Tests
- Expanded [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:153) to cover:
  - successful one-item backend flush + Capture Inbox verification
  - backend success without readback match
  - explicit finalized-metadata rejection mapping
  - continued no-batch behavior on the main harvest path

## API Impact

No API code changes were required.

Existing backend support was sufficient because the extension already targets:
- [`POST /douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/popup.ts:511)
- [`GET /douyin-extension/capture-sessions/{capture_session_id}/items`](apps/api/src/api/routes/capture_inbox.py:134)

Phase 18I-G therefore remains extension-scoped, with API todo items closed as not required for this step.

## Non-Goals Preserved
- No full batch backend flush.
- No queue-wide replay of extracted targets.
- No API schema changes.
- No worker orchestration changes.
- No migration to legacy runtime or V2 staged-harvest runtime.

## Validation Snapshot
- [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json)
- [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json)

## Notes
- The active harvest path still produces a validated preview first; backend submission only happens after operator-triggered [`Flush One Item`](apps/extension-douyin-capture/public/popup.html:78).
- Verification still depends on Capture Session readback, so backend success without a matching session item is treated as a failure state for operator visibility.
