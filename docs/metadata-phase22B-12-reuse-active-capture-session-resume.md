# Phase 22B-12 Reuse Active Capture Session Per Profile Resume

## Completed
- Added same-profile active-session reuse in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1886).
- Enriched the extension/backend capture-session request contract in [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts:1275) and [`apps/api/src/schemas/douyin_extension.py`](apps/api/src/schemas/douyin_extension.py:575).
- Persisted friendly session-label metadata in [`apps/api/src/services/douyin_extension_capture_service.py`](apps/api/src/services/douyin_extension_capture_service.py:228).
- Updated Session Ribbon label selection in [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1408).
- Updated focused regression coverage in [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py:1137), [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts), and [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts).

## Key Findings
- The existing one-item Start Collecting flow did not need redesign; the Phase 22B-12 behavior belongs inside [`ensureBackendCaptureSession()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1886) and session metadata persistence.
- Session reuse is safest when matched on both normalized profile URL and normalized profile identifier instead of technical session ID alone.
- Capture Inbox can present friendlier session labels without API contract changes because the needed values already fit in persisted session metadata.
- Posted extraction fallback remained within current payload/evidence composition and did not require a Capture Inbox UI redesign.

## Remaining Validation
- Run [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json).
- Run [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json).
- Run [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json).
- Run backend tests for [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py).

## Files Touched In This Phase
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts)
- [`apps/api/src/schemas/douyin_extension.py`](apps/api/src/schemas/douyin_extension.py)
- [`apps/api/src/services/douyin_extension_capture_service.py`](apps/api/src/services/douyin_extension_capture_service.py)
- [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx)
- [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py)
- [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase22B-12-reuse-active-capture-session-log.md`](docs/metadata-phase22B-12-reuse-active-capture-session-log.md)
- [`docs/metadata-phase22B-12-reuse-active-capture-session-resume.md`](docs/metadata-phase22B-12-reuse-active-capture-session-resume.md)
