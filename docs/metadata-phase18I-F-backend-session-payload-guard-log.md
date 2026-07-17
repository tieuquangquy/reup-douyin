# Phase 18I-F Backend Session + Payload Guard Log

## Scope
Implemented Phase 18I-F for the extension whole-profile harvest flow only: create or reuse a canonical backend capture session, build a sanitized payload preview from extracted harvest results, persist local guard/preview diagnostics, and keep the active run path preview-only. This phase does not perform real backend item flush, does not create Capture Inbox items, does not call [`/douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/popup.ts), and does not reuse legacy or V2 staged runtime flows.

## Completed Changes

### Extension Runtime
- Extended persisted whole-profile harvest backend state in [`state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts) with nested preview/session tracking under [`WholeProfileHarvestState`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:192):
  - [`harvest.backend.capture_session`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:288) stores status, session id, request/response summaries, error metadata, and last update time.
  - [`harvest.backend.payload_preview`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:299) stores preview status, target aweme id, removed fields, local guard result, payload snapshot, summary, and update time.
- Strengthened normalization/defaulting in [`createWholeProfileHarvestIdleState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:339) and [`normalizeWholeProfileHarvestState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:472) so older saved states upgrade safely into the new backend-preview shape.
- Added sanitized preview helpers in [`canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts):
  - [`sanitizeProfileCardEvidenceForBackend()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:131)
  - [`buildRawEvidenceSummaryForCanonicalHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:150)
  - [`buildCanonicalFullModalPayloadPreview()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:180)
  - [`guardCanonicalHarvestPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:256)
  - [`selectLatestExtractedResultForPayloadPreview()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:123)
- Updated [`createCanonicalHarvestSession()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:521) so capture-session preflight persists canonical request/response diagnostics into local whole-profile state before any item-write step.
- Updated the active extraction path in [`runRealModalExtractionHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:627) to:
  - create or reuse a canonical capture session before target processing
  - persist the session id in top-level state and backend nested state
  - keep execution on the extraction-only path with no backend item writes
- Updated [`checkpointLocalHarvestTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1097) so each extracted result builds a local payload preview, runs the local disallowed-field guard, and stores preview/guard summaries without flushing the payload.
- Reset payload-preview state when preparing a new queue in [`prepareHarvestQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:969).

### Popup / Progress / Operator Messaging
- Expanded [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3) to expose:
  - capture-session status from nested backend state
  - payload-preview status with target aweme id and removed-field count
  - payload-guard status including offending paths when guard fails
- Updated popup wording in [`runWholeProfileHarvestProductFromPopup()`](apps/extension-douyin-capture/src/popup.ts:304), [`resumeWholeProfileHarvestFromPopup()`](apps/extension-douyin-capture/src/popup.ts:339), [`resetWholeProfileHarvestStateFromPopup()`](apps/extension-douyin-capture/src/popup.ts:343), and [`copyWholeProfileDebugJsonFromPopup()`](apps/extension-douyin-capture/src/popup.ts:350) so operator messaging reflects canonical session + payload preview behavior while still promising no backend item writes.

### Tests
- Expanded [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) to cover:
  - canonical capture-session creation on the active extraction path
  - no real flush during Phase 18I-F
  - persisted payload-preview state and guard success
  - richer guard result shape with `offending_paths`
  - direct preview-builder output via [`buildCanonicalFullModalPayloadPreview()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:180)

## Non-Goals Preserved
- No real backend item flush.
- No Capture Inbox item creation.
- No call to [`flushCanonicalHarvestPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:549) from the active Phase 18I-F path.
- No legacy state/runtime reuse.
- No V2 staged-harvest adoption.

## Validation Runs
- Ran [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json) successfully.
- Ran [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json) successfully after aligning [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) with the sanitizer allowlist behavior.

## Notes
- Top-level [`capture_session_id`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:200) remains present for compatibility, but Phase 18I-F state now treats nested backend state as the detailed source of truth.
- Payload preview remains local-only and is intended to prove payload cleanliness before a later phase reintroduces actual backend submission.
