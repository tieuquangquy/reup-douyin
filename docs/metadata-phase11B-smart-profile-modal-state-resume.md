# Phase 11B Smart Profile/Modal State Resume

## Current State

Smart Capture & Harvest now separates profile capture state from modal harvest readiness in the extension popup.

## Changed Files

- `apps/extension-douyin-capture/src/popupWorkflow.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
- `docs/metadata-phase11B-smart-profile-modal-state-log.md`
- `docs/metadata-phase11B-smart-profile-modal-state-resume.md`

## Root Cause

The stale red viewport banner and wrong Smart Capture next action came from mixing old persisted state with current operational state. The UI summary computed current viewport status independently from the status banner, while `last_error` and a previous modal probe PASS could remain in storage. The workflow also did not require a current `modal_id` match before considering a probe usable for harvest.

## Implemented Behavior

### Stale Viewport Banner

If the calibrated viewport and current popup viewport match, stale `viewport_changed_significantly` is cleared from smart state. The red recalibration banner is cleared when current viewport warning is `none`.

Actual viewport changes above the existing 15% threshold still set `calibration_required` and show the recalibration message.

### Profile URL Smart Capture

On `/user/...` with no `modal_id`, Smart Capture now:

1. captures the current profile page first
2. stores capture session/capture id/item count through the existing capture path
3. checks calibration and viewport
4. clears stale stored probe state
5. sets `current_state = modal_required`
6. shows the neutral instruction to open the first video modal and click Resume

### Modal Resume

On `/user/...?modal_id=...` or `/video/{aweme_id}`, Resume now:

1. detects the current modal/video id
2. runs `REUP_DOUYIN_PROBE_CURRENT_MODAL`
3. stores/renders the probe
4. validates PASS against the current id and calibrated point source
5. resumes harvest with the stored capture binding only after validation passes

## Probe Freshness Rule

A probe PASS is usable only for the current modal/video id and only when it came from calibrated point extraction. Profile pages mark old probes as not applicable and cannot start harvest from them.

## Tests Run

```text
npx tsx apps/extension-douyin-capture/src/popupWorkflow.test.ts
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
```

## Verification Result

Passed final full verification commands:

```text
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Steps

1. Open a Douyin profile URL `/user/...` without `modal_id`.
2. Open the extension popup.
3. Confirm viewport summary says `Viewport warning: none` and no red viewport recalibration banner appears when current and calibrated viewport match.
4. Click Smart Capture & Harvest.
5. Confirm state becomes `modal_required` and next action says to open the first video modal and click Resume.
6. Confirm Last probe is `none` or `not applicable`, not an old PASS.
7. Open the first video modal so the URL includes `modal_id`.
8. Click Resume Smart Capture & Harvest.
9. Confirm it probes the current modal id.
10. Confirm harvest starts/resumes only after the probe PASS aweme id matches the current `modal_id`.
