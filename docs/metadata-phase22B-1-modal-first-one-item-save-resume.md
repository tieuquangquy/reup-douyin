# Phase 22B-1 Modal-First One-Item Save Resume

## Current Status

Phase 22B-1 implementation is complete in the extension collector code path and is ready for validation.

## Files Touched

- `apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase22B-1-modal-first-one-item-save-log.md`
- `docs/metadata-phase22B-1-modal-first-one-item-save-resume.md`

## Validation Plan

Run these from the repository root on Windows:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

Backend validation is not required for this phase because backend files were not changed.

## Manual Retest

1. Open a Douyin profile modal URL containing `modal_id=AWEME_ID`.
2. Calibrate the four metric points in that profile modal layout.
3. Return to the profile and run Scan Profile.
4. Run Start Collecting.
5. Confirm Advanced diagnostics show `calibration_layout = profile_modal` and detail strategy uses a profile modal URL.
6. Confirm payload preview and guard both pass.
7. Confirm backend save succeeds and verify readback finds the item in the capture session.
8. Confirm Capture Inbox has the saved item without any Capture Inbox UI code changes.

## Key Guardrail

If current extraction context is a direct `/video/AWEME_ID` page while calibration expects `profile_modal`, extraction is blocked before metrics extraction and before backend save with `extraction_context_mismatch` diagnostics.
