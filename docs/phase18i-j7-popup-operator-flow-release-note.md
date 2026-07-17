# Phase 18I-J7 Popup Operator Flow Release Note

## Summary
Phase 18I-J7 completes the popup cleanup for [`apps/extension-douyin-capture`](apps/extension-douyin-capture). The main extension popup now presents the canonical whole-profile operator workflow without the stale legacy probe button being treated as part of the production surface.

## Operator Impact
- The main popup now emphasizes one guided flow:
  - reconnect
  - calibrate
  - scan profile
  - dry-run test
  - extract batch
  - save one verified item
  - save remaining batch
- `Technical Details` remains available for diagnostics and maintenance, but no longer competes with the main workflow.
- Save guidance remains operator-safe by preserving the `Save 1 Video` before `Save Batch` progression.

## Cleanup Included
- Removed the stale `probeHarvestButton` production-contract expectation from [`apps/extension-douyin-capture/src/popupWorkflow.ts`](apps/extension-douyin-capture/src/popupWorkflow.ts).
- Updated popup workflow regression coverage in [`apps/extension-douyin-capture/src/popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts).
- Removed dead hidden-selector reads from [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts:302) and replaced them with explicit safe defaults.
- Rebuilt popup assets so [`apps/extension-douyin-capture/dist/popup.html`](apps/extension-douyin-capture/dist/popup.html) reflects the cleaned production popup.

## Validation
- Passed: `npm --workspace @reup-douyin/extension-douyin-capture run build`
- Passed: `npm --workspace @reup-douyin/extension-douyin-capture run test`
- Existing whole-profile regression coverage already verifies the canonical Scan -> Test -> Extract -> Save path plus stop/resume, captcha, save verification, and Technical Details wording.

## Non-Goals Confirmed
- No backend API redesign.
- No crawler or video-processing implementation.
- No Capture Inbox model changes.
- No broader web app UX changes outside the extension popup scope.

## Status
Released for the current local operator-ready extension baseline.
