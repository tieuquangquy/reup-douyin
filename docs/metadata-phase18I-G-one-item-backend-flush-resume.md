# Phase 18I-G One-Item Backend Flush Resume

## Current State

Phase 18I-G is implemented in the extension whole-profile harvest flow.

- The active harvest run still uses extraction-first mode and does not batch flush targets automatically.
- The run creates or reuses a canonical capture session before extraction through [`createCanonicalHarvestSession()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:545).
- Extracted targets still build a validated canonical payload preview with local guard evaluation before any backend write through [`checkpointLocalHarvestTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1423).
- The popup now exposes a dedicated [`Flush One Item`](apps/extension-douyin-capture/public/popup.html:78) action that calls [`flushOneItemFromPayloadPreview()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:686).
- One-item flush now verifies Capture Inbox creation by reading back the current capture session through [`verifyCaptureInboxItemCreated()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:642).
- No full batch backend flush was enabled.
- No API code changes were required.

## Files Touched

- [`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase18I-G-one-item-backend-flush-log.md`](docs/metadata-phase18I-G-one-item-backend-flush-log.md)
- [`docs/metadata-phase18I-G-one-item-backend-flush-resume.md`](docs/metadata-phase18I-G-one-item-backend-flush-resume.md)
- [`docs/metadata-phase18I-G-one-item-flush-operator-guide.md`](docs/metadata-phase18I-G-one-item-flush-operator-guide.md)

## Explicit Error Coverage

One-item flush now has dedicated operator-facing error codes in [`WholeProfileHarvestErrorCode`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:1):
- [`capture_session_not_found`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:32)
- [`payload_preview_missing`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:33)
- [`backend_finalized_metadata_required`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:34)

These are classified in [`classifyOneItemFlushError()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:663) and surfaced in progress/debug state.

## Validation Snapshot

Completed validation for the extension workspace:
- [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json)
- [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json)

## API Notes

Phase 18I-G did not require backend edits.

Existing endpoints were already sufficient:
- [`POST /douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/popup.ts:511)
- [`GET /douyin-extension/capture-sessions/{capture_session_id}/items`](apps/api/src/api/routes/capture_inbox.py:134)

Because no API code changed, the API-test todo is closed as not required for this step.

## Live Retest

1. Rebuild and reload the extension.
2. Open a Douyin profile page and run [`Verify Profile`](apps/extension-douyin-capture/public/popup.html:31).
3. Run a dry run and then [`Run Harvest`](apps/extension-douyin-capture/public/popup.html:76) until the popup shows a ready payload preview.
4. Confirm the progress panel shows payload-preview readiness and capture-session readiness from [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3).
5. Click [`Flush One Item`](apps/extension-douyin-capture/public/popup.html:78).
6. Confirm the progress panel shows a succeeded one-item flush and verified Capture Inbox item id.
7. If verification fails, inspect the persisted debug summaries from [`copyDebugState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1673) for request, response, and verify diagnostics.

## Guardrails

- Do not enable queue-wide backend flush.
- Do not add API changes unless a later validation run proves existing contracts are insufficient.
- Do not reuse legacy runtime or staged V2 runtime for this flow.
- Keep backend submission dependent on a validated preview plus explicit operator action.