# Phase 22B-8A Continue After Session Verified Log

## Scope

- Extension Start Collecting flow only.
- No Capture Inbox frontend changes.
- No batch collection.
- No scanner, calibration, or backend API contract changes.

## Why Start Collecting stopped at `session_verified`

Phase 22B-7A intentionally isolated the Capture Inbox session handoff. The active controller path was:

`runStartCollectingWorkflow()` -> `runStartCollectingPreflight()` -> `ensureBackendCaptureSession()`

After the session was verified, `runStartCollectingWorkflow()` wrote:

- `phase = "session_verified"`
- `status = "harvest_ready"`
- `last_scanner_result = "session_ready"`

and returned. That left the backend session created and verified, but no one-item modal extraction or backend item save was called.

## Active stop point fixed

The stop point was in:

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- function: `runStartCollectingWorkflow()`

The function now persists the verified session handoff, checks the one-item runner is connected, then calls:

`runOneItemCollectAndSave(runtime, { collect_mode: "one_item_backend_proof", batch_limit: 1, scanner_start_collecting: true })`

## One-item runner path

The connected path is:

1. `session_verified`
2. `target_selected`
3. `opening_target`
4. `extracting_metadata`
5. `building_payload`
6. `guarding_payload`
7. `saving_item`
8. `verifying_item`
9. `one_item_saved`
10. `stopped_after_one_item`

Each stage updates Start Collecting diagnostics through the canonical scanner debug summaries.

## Modal-first URL behavior

The runner uses `buildModalDetailUrl()`:

- If a target source URL is already a `/user/...?...modal_id=<aweme>` URL, it is reused.
- Otherwise it builds `profile_url + "?modal_id=" + aweme_id`.
- Direct `/video/<aweme_id>` URLs are not used for Start Collecting profile-modal calibration.

## Payload, save, and verify behavior

- Metadata is extracted from the calibrated profile modal.
- Required fields are checked before payload build: aweme id, duration, likes, comments, favorites, shares.
- Payload preview is built for the verified `capture_session_id`.
- `guardCaptureInboxPayload()` must pass before backend save.
- Backend save uses the existing one-item full modal harvest transport.
- After save succeeds, the runner verifies the item through `GET /douyin-extension/capture-sessions/{session_id}/items`.
- If readback does not find the aweme id, the run ends as `saved_unverified` instead of falsely marking the item verified.

## Capture Inbox UI

Capture Inbox frontend files were not modified.

## Tests run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
