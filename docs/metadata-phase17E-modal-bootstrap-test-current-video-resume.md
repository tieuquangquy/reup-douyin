# Phase 17E Modal Bootstrap and Test Current Video Resume

## Current Status

Phase 17E implementation is complete in the extension package. The latest full extension test command passed.

## Changed Areas

- apps/extension-douyin-capture/src/modalStart.ts
- apps/extension-douyin-capture/src/contentScript.ts
- apps/extension-douyin-capture/src/popupWorkflow.ts
- apps/extension-douyin-capture/src/popup.ts
- apps/extension-douyin-capture/src/modalStart.test.ts
- apps/extension-douyin-capture/src/popupWorkflow.test.ts
- apps/extension-douyin-capture/src/popupActions.test.ts
- docs/metadata-phase17E-modal-bootstrap-test-current-video-log.md
- docs/metadata-phase17E-modal-bootstrap-test-current-video-resume.md
- docs/metadata-phase17E-modal-operator-guide.md

## Behavior to Preserve

### Test Current Video

On a Douyin modal page with content script ready, detector ready, and four-point calibration saved, Test Current Video must work even when capture_session is missing. It must not require harvest_plan, target queue, backend flush, or Capture Inbox writes.

It uses the active modal_id as the temporary target_aweme_id, waits for the modal id to be stable, extracts duration/like/comment/favorite/share from calibrated points, validates IDs, and displays the result in the popup.

### Smart Capture on Modal

When Smart Capture & Harvest starts on a modal page without a known target queue, it resolves the profile URL by removing modal_id, builds a harvest plan through /douyin-extension/harvest-plan, persists targets/evidence, returns to the original modal URL, and starts modal harvest using the target queue.

A zero-target harvest plan is recorded as completed_noop and displays the no-new-items message.

## Validation Commands

Run before handing off future changes:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Notes for Future Work

Do not reintroduce capture_session as a hard prerequisite for modal Test Current Video or modal Smart Capture bootstrap. Capture session remains relevant when backend plan responses provide it, but Phase 17E intentionally supports sessionless modal bootstrap and sessionless metric testing.
