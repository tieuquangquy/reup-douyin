# Phase 13D Profile Modal State Detector Fix Resume

## Current Phase

Phase 13D fixes profile-vs-modal state priority and detector reconnect behavior in the Douyin capture extension only.

## Implemented Files

- `apps/extension-douyin-capture/src/types.ts`
  - Added `DouyinPageContext` and page-context response support.
  - Added ping and page-context message types.
  - Added explicit popup workflow states for unavailable detector/content script and profile capture.
- `apps/extension-douyin-capture/src/contentScript.ts`
  - Added `REUP_DOUYIN_PING` handling.
  - Added `REUP_DOUYIN_DETECT_PAGE_CONTEXT` handling.
  - Added `detectDouyinPageContext()` as the content-script source of truth for profile, modal, video, and unknown page contexts.
- `apps/extension-douyin-capture/src/popupWorkflow.ts`
  - Added page context, content-script status, detector status, and detector error to operational snapshots.
  - Added `Reconnect Douyin tab` guidance constants.
  - Reordered state priority so backend/tab/content-script/detector failures appear before calibration.
  - Added profile-first reconciliation with `profile_capture_required` and `modal_required`.
  - Prevented stale modal probes from applying on profile pages.
  - Preserved existing legacy viewport-unavailable behavior while supporting explicit reconnect states.
- `apps/extension-douyin-capture/src/popup.ts`
  - Added the reconnect button handler.
  - Added active-tab validation, content-script ping, optional script injection, re-ping, and page-context detection.
  - Added popup diagnostics for page type, content script, detector, capture session, calibration, current state, and next action.
  - Updated Smart Capture behavior so profile capture happens before modal calibration/probe guidance.
- `apps/extension-douyin-capture/public/popup.html`
  - Added the `Reconnect Douyin tab` button.
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
  - Added Phase 13D assertions for page classification, detector priority, profile/modal state, stale probe handling, reconnect source behavior, and diagnostics rendering.
- `docs/metadata-phase13D-profile-modal-state-detector-fix-log.md`
  - Phase implementation log.
- `docs/metadata-phase13D-profile-modal-state-detector-fix-resume.md`
  - This resume document.
- `docs/metadata-phase13D-operator-workflow.md`
  - Operator workflow guide.

## Verification Status

Already passed from repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Still run before final handoff:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Checklist

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist` after build.
2. Open a supported Douyin profile URL such as `https://www.douyin.com/user/...` without `modal_id`.
3. Open the extension popup.
4. Confirm diagnostics show `Page type: profile` and content script/detector status.
5. Confirm the next action is profile capture, not calibration.
6. Click Smart Capture & Harvest or Capture current page.
7. Confirm the popup moves to `modal_required` when targets exist.
8. Open the first target modal/video.
9. Confirm missing calibration now appears only on modal/video pages.
10. If content script detection fails, click `Reconnect Douyin tab` and confirm the popup re-detects page context.

## Non-Goals Preserved

No backend, web app, metric extraction changes, calibrated point concept changes, CDP/debug workflow changes, queue implementation, crawler implementation, or auto-publish integration were introduced in Phase 13D.
