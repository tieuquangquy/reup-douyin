# Phase 12A Extension Production Cleanup Resume

## Current status

Phase 12A production cleanup is implemented for `apps/extension-douyin-capture`.

## Completed changes

- Production popup now renders only normal workflow buttons.
- Legacy CDP/debug button section was removed from normal popup HTML.
- Smart Capture orchestration is named `runSmartCaptureHarvest()`.
- Content script production probe is named `probeCurrentModalWithCalibratedPoints()`.
- Calibration saves new `phase12a_calibrated_five_point_workflow` version.
- Five-point calibration includes `next_video_button`.
- Old four-point calibration blocks Smart Capture & Harvest with `Next video point missing. Recalibrate with five points.`
- Production probe PASS is restricted to calibrated point sources.
- Active video duration remains sourced from `HTMLVideoElement.duration`.
- Harvest navigation uses `navigateNextByCalibratedPoint()` and calibrated next-point clicking.
- Backend evidence summary was simplified to Phase 12A calibrated workflow metadata.
- Popup viewport-size stale recalibration blocking was removed from normal workflow.
- Content-script viewport remains the source of truth.
- Tests were updated for Phase 12A expectations.

## Remaining work

No known code work remains for Phase 12A after verification. If future cleanup continues, keep it scoped and do not reintroduce CDP/debug extraction as a normal PASS source.

## Key files touched

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupActions.test.ts`
- `apps/extension-douyin-capture/src/popupSmartWorkflow.test.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
- `apps/extension-douyin-capture/src/types.ts`

## Verification status

Completed:

- `npm --workspace @reup-douyin/extension-douyin-capture run test`

Pending at the time this resume note was written:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Important guardrails

- Do not add backend/web/database/Capture Inbox UI changes for this phase.
- Do not reintroduce CDP/debug buttons into normal popup UI.
- Do not allow old extractors to produce normal Probe PASS.
- Do not use popup viewport as Douyin page viewport.
- Do not fake metrics.

## Live retest checklist

1. Reload unpacked extension from `apps/extension-douyin-capture/dist`.
2. On a Douyin profile page, confirm only production buttons render.
3. Run Smart Capture on a profile and confirm `modal_required`.
4. Open a modal and calibrate five points.
5. Probe current modal and confirm calibrated PASS.
6. Start/resume harvest and confirm calibrated next navigation.
7. Confirm progress panel updates.
8. Confirm flush includes explicit `capture_session_id`.
9. Confirm no stale `viewport_changed_significantly` appears when content-script viewport is valid.