# Phase 22B-11 Resume

## Completed

- Fixed Session Ribbon count drift by recomputing session counters from the actual `CapturedItem` store on session list/detail reads.
- Fixed same-transaction one-item session reconciliation by keeping `session.items` coherent after finalized item creation.
- Expanded posted extraction fallback in the extension modal path to read:
  - visible relative posted text
  - visible direct publish-time text
  - embedded aweme script time fields
- Expanded backend response mapping so posted provenance survives into Capture Inbox item responses.

## Files Touched

- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/tests/test_capture_inbox_metadata_status.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Why Ribbon Was Wrong

`GET /douyin-extension/capture-sessions/{session_id}/items` read the real item store and showed the created item, but `/capture-inbox/sessions` could still return stale `CaptureSession` counters because it did not recompute them from items before serializing the session list.

## Why Posted Was Missing

The extension modal fallback only used a narrow text match and could stop before preserving posted metadata into the backend payload. The fallback now searches both visible modal text and aweme-scoped script evidence, then preserves `posted_text` even if timestamp parsing stays uncertain.

## Validation Commands

- Extension:
  - `npm --workspace @reup-douyin/extension-douyin-capture run test`
  - `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
  - `npm --workspace @reup-douyin/extension-douyin-capture run build`
- Backend:
  - `cd apps/api`
  - `python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status`
  - `python -m compileall src scripts`

## Next Check

Retest one-item `Start Collecting`, then refresh Capture Inbox:

- Session Ribbon should show `captured >= 1`
- `ready` and `needs action` should reflect the saved item metadata
- Item `Posted` should no longer show `Not captured` when visible publish text exists in the modal
