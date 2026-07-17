# Phase 22B-8A Continue After Session Verified Resume

## Current phase

Phase 22B-8A connects the verified Capture Inbox session handoff to the one-item collect/save runner.

## What changed

- `runStartCollectingWorkflow()` no longer returns after `session_verified`.
- It calls `runOneItemCollectAndSave()` with `collect_mode = "one_item_backend_proof"` and `batch_limit = 1`.
- One-item diagnostics now record stage transitions from target selection through backend readback verification.
- The final Start Collecting state stops after one item with `phase = "stopped_after_one_item"` when the item is saved and verified.

## One-item behavior

- Selects the first pending collect target.
- Builds a profile-modal URL with `modal_id`.
- Opens the modal through the existing runtime modal opener.
- Extracts real calibrated modal metrics.
- Builds and guards the Capture Inbox item payload.
- Saves one item to backend.
- Verifies the saved aweme id appears in the session items list.
- Stops after the first target.

## Failure behavior

If any stage fails, diagnostics retain the stage:

- `opening_target`
- `extracting_metadata`
- `building_payload`
- `guarding_payload`
- `saving_item`
- `verifying_item`

No silent stop at `session_verified` remains.

## Retest focus

1. Run Scan Profile and ensure pending targets exist.
2. Ensure calibration is ready.
3. Click Start Collecting.
4. Confirm diagnostics advance past `session_verified`.
5. Confirm one modal opens with `profile_url?modal_id=<aweme_id>`.
6. Confirm one item is saved or an exact stage error is shown.
7. Confirm Capture Inbox session items contain exactly the saved aweme id.
8. Confirm a second target is not processed in this phase.

## Tests

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.
