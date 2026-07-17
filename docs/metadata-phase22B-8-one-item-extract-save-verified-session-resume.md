# Phase 22B-8 One-Item Extract + Save Verified Session Resume

## Completed
- Audited the active Start Collecting path in [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts:731) and [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:628).
- Confirmed the narrow one-item path already flows through [`runStartCollectingPreflight()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:329) into [`runOneItemCollectAndSave()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2388).
- Confirmed backend session proof is handled by [`ensureBackendCaptureSession()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1568).
- Confirmed backend item save uses [`flushOneCanonicalHarvestPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1645) and readback verification uses [`verifyCaptureInboxItemCreated()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1655).
- Confirmed focused regression coverage already exists in [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:680).
- Added the phase log in [`docs/metadata-phase22B-8-one-item-extract-save-verified-session-log.md`](docs/metadata-phase22B-8-one-item-extract-save-verified-session-log.md).

## Key Findings
- No Capture Inbox UI files required changes.
- No batch runner rewrite was needed; the one-item path is already isolated from [`runRealModalExtractionHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2481) through the `one_item_backend_proof` / `one_item_smoke_test` gate.
- Modal-first behavior is already implemented by [`buildModalDetailUrl()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2351).
- Extraction guardrails are already implemented by [`validateExtractionContext()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2357) and [`guardCaptureInboxPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts).

## Remaining Validation
- Run [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json).
- Run [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json).

## Files Touched In This Phase
- [`docs/metadata-phase22B-8-one-item-extract-save-verified-session-log.md`](docs/metadata-phase22B-8-one-item-extract-save-verified-session-log.md)
- [`docs/metadata-phase22B-8-one-item-extract-save-verified-session-resume.md`](docs/metadata-phase22B-8-one-item-extract-save-verified-session-resume.md)
