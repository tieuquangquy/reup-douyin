# Phase 18I-G One-Item Flush Operator Guide

## Before Running

1. Open the target Douyin profile page in the active tab.
2. Click [`Verify Profile`](apps/extension-douyin-capture/public/popup.html:73) and confirm verified targets are present.
3. Complete calibration and dry-run checks before starting a real harvest.
4. Click [`Run Harvest`](apps/extension-douyin-capture/public/popup.html:76) and allow at least one target to finish extraction.
5. Confirm the popup progress panel shows a ready payload preview and a ready capture session from [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3).
6. Expect this phase to allow exactly one backend write at a time through explicit operator action. It does not enable full batch backend flush.

## What Phase 18I-G Adds

Phase 18I-G keeps the main harvest path extraction-first, but adds a new operator action: [`Flush One Item`](apps/extension-douyin-capture/public/popup.html:78).

That action uses the latest validated canonical payload preview from [`flushOneItemFromPayloadPreview()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:686) to:
- submit exactly one aweme payload to the backend
- require an existing canonical capture session
- verify that the Capture Inbox item appears in capture-session readback

The popup help text in [`popup.html`](apps/extension-douyin-capture/public/popup.html:79) intentionally warns that only the current validated preview target is flushed.

## Standard Operator Flow

1. Click [`Verify Profile`](apps/extension-douyin-capture/public/popup.html:73).
2. Run a dry run if needed.
3. Click [`Run Harvest`](apps/extension-douyin-capture/public/popup.html:76).
4. Wait until one target has been extracted and the payload preview becomes ready.
5. Click [`Flush One Item`](apps/extension-douyin-capture/public/popup.html:78).
6. Watch the progress panel for:
   - `One-item flush`
   - `One-item verify`
   - `One-item flush error`
7. Confirm the flush result includes a Capture Inbox item id and verified readback match.

## What the Progress Panel Means

The progress rows from [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3) now expose one-item backend state:

- `One-item flush`
  - `idle`: no one-item submission attempted yet
  - `running`: backend request is in progress
  - `succeeded · item <id>`: backend returned a Capture Inbox item id
  - `failed`: backend request or verification failed
- `One-item verify`
  - `idle`: verification has not started yet
  - `verified · created_or_updated=yes|no`: readback found the aweme id in the capture session
  - `not_found`: backend returned success, but readback did not show the item
  - `failed`: verification endpoint or state failed for another reason
- `One-item flush error`
  - shows the current structured error code plus operator-facing message

## Common Failure States

Structured one-item errors are defined in [`errors.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:1).

Important Phase 18I-G failures include:
- [`payload_preview_missing`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:94)
  - Meaning: there is no validated preview ready to flush.
  - Operator action: run harvest until a target is extracted and preview state is ready.
- [`capture_session_not_found`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:93)
  - Meaning: backend no longer recognizes the canonical capture session.
  - Operator action: rerun harvest to recreate the session, then flush again.
- [`backend_finalized_metadata_required`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:95)
  - Meaning: backend rejected the payload because required finalized modal metadata is missing.
  - Operator action: rerun extraction for the target before retrying.
- [`backend_secret_guard_rejected`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:107)
  - Meaning: a guarded field leaked into the payload.
  - Operator action: do not retry until payload construction is fixed.
- [`backend_success_but_no_capture_inbox_item`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:109)
  - Meaning: backend returned success, but the extension could not verify the created item in capture-session readback.
  - Operator action: inspect debug state and backend logs before trying again.

## Copying Diagnostics

If the one-item flush fails, use the popup debug workflow backed by [`copyDebugState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1673).

Inspect at least:
- `debug.last_request_summary`
- `debug.last_response_summary`
- `harvest.backend.one_item_flush`
- `harvest.backend.payload_preview`

These records show the selected aweme id, request path, response status, backend error code, and verification result.

## Guardrails

- Do not treat [`Flush One Item`](apps/extension-douyin-capture/public/popup.html:78) as a queue-wide publish control.
- Do not click it before the payload preview is ready.
- Do not assume backend success is enough; always confirm readback verification.
- Do not use this phase to enable batch flushing or broader automation.