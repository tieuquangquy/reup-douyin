# Phase 22B-8 One-Item Extract + Save Verified Session Log

## Scope
- Audit the active [`runStartCollectingWorkflow()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:628) path before any edits.
- Keep the Phase 22B-8 change narrow to the extension controller path only.
- Do not modify Capture Inbox frontend UI or rewrite batch flush flow.
- Ensure Start Collecting verifies or creates a backend capture session, extracts exactly one modal item, saves it, verifies session readback, and stops.

## Active Start Collecting Path
- Popup dispatch still enters [`runWholeProfileHarvestProductFromPopup()`](apps/extension-douyin-capture/src/popup.ts:731), which calls [`runStartCollectingWorkflow()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:628).
- [`runStartCollectingWorkflow()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:628) records click diagnostics, runs [`runStartCollectingPreflight()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:329), then advances into [`runOneItemCollectAndSave()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2388).
- [`runStartCollectingPreflight()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:329) now proves session readiness through [`ensureBackendCaptureSession()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1568), validates the first pending target, builds a modal-first detail URL, and confirms the runner is available.
- [`runOneItemCollectAndSave()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2388) performs the one-item smoke path only: prepare queue with `batch_limit: 1`, reopen the selected modal, validate extraction context, extract real metrics, build a guarded payload, call [`flushOneCanonicalHarvestPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1645), then verify the item through [`verifyCaptureInboxItemCreated()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1655).

## Behavior Confirmed
- Session verification happens before modal open and before backend save.
- Modal-first opening uses [`buildModalDetailUrl()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2351), preferring the target source modal URL and otherwise falling back to `profile_url?modal_id=...`.
- Extraction is blocked when the current page context does not match the expected profile modal.
- Guarding is local via [`guardCaptureInboxPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts), before backend write.
- Backend item save uses `/douyin-extension/full-modal-harvest` with one-item headers from [`flushOneCanonicalHarvestPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1645).
- Verification reads `/douyin-extension/capture-sessions/{session_id}/items` via [`verifyCaptureInboxItemCreated()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1655).
- The flow stops after one saved item by returning a completed state from [`runOneItemCollectAndSave()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2388).

## Regression Coverage Present
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) covers:
  - successful one-item save + verify
  - stale local session replacement
  - blocked unverified session path
  - context mismatch blocking before extraction/save
  - payload guard protection

## Validation
- [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json)
- [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json)
- [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json)
