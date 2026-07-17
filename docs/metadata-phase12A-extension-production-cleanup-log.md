# Phase 12A Extension Production Cleanup Log

## Scope

Phase 12A cleaned the Douyin Chrome extension production workflow under `apps/extension-douyin-capture` only. No backend, web app, database, Capture Inbox UI, or publishing workflow changes were made.

## Final production workflow

1. Operator opens a Douyin profile or modal page.
2. Operator clicks `Smart Capture & Harvest`.
3. The extension captures the current page and receives/persists the backend `capture_session_id`.
4. If the active page is a profile without `modal_id`, the workflow enters `modal_required` and asks the operator to open the first video modal.
5. Operator calibrates five points once:
   - `like_count`
   - `comment_count`
   - `favorite_count`
   - `share_count`
   - `next_video_button`
6. The popup requests the current Douyin page viewport from the content script.
7. The content script probes the current modal using calibrated points only.
8. Smart Capture & Harvest extracts:
   - `aweme_id` from `modal_id`/video URL detection.
   - `duration_seconds` from the active `HTMLVideoElement.duration`.
   - like/comment/favorite/share counts from calibrated points.
9. Harvest payloads flush to the backend with explicit `capture_session_id`.
10. The content script clicks the calibrated `next_video_button` point and waits for `modal_id` change before continuing.
11. Progress UI reports current phase, index, metrics, flushing, navigation, and stop/error state.

## Removed or disabled obsolete normal workflow paths

Normal production UI/path no longer exposes legacy debug buttons or uses these as PASS-producing paths:

- CDP attach/detach/status actions.
- CDP network extraction.
- CDP runtime extraction.
- CDP DOMSnapshot right-rail extraction.
- Accessibility-tree/OCR broad right-rail production extraction.
- DOM selector right-rail extraction as a normal PASS fallback.
- Icon-anchored extraction as a normal PASS fallback.
- Text-node cluster extraction as a normal PASS fallback.
- Combined modal text fallback as a normal PASS source.
- Profile-card fallback for modal metrics.
- Old direct Full Modal Harvest operator UI.
- Popup viewport-size stale recalibration blocking.

Legacy CDP test files/background utilities may remain for historical coverage, but the production popup/content-script workflow does not route Smart Capture & Harvest through CDP/debug buttons.

## Final popup buttons

Primary:

1. `Smart Capture & Harvest`

Calibration:

2. `Start Right Rail Calibration`
3. `Probe Current Modal Metrics`
4. `Show Calibration`
5. `Clear Calibration`

Control:

6. `Resume Harvest`
7. `Stop Harvest`
8. `Flush Pending`
9. `Show Progress`

Advanced:

10. `Capture current page only`

## Production functions

- `probeCurrentModalWithCalibratedPoints()` in the content script.
- `runSmartCaptureHarvest()` in the popup.
- `navigateNextByCalibratedPoint()` in modal harvest navigation.
- `getDouyinPageViewport()` in the content script.

## Five-point calibration contract

```ts
{
  version: "phase12a_calibrated_five_point_workflow",
  viewport_width,
  viewport_height,
  points: {
    like_count: { x, y, x_ratio, y_ratio },
    comment_count: { x, y, x_ratio, y_ratio },
    favorite_count: { x, y, x_ratio, y_ratio },
    share_count: { x, y, x_ratio, y_ratio },
    next_video_button: { x, y, x_ratio, y_ratio }
  }
}
```

Old four-point calibration remains readable for manual metric probing, but Smart Capture & Harvest blocks with `Next video point missing. Recalibrate with five points.`

## Smart Capture state machine

Production states are:

```text
idle
capturing_profile
capture_ready
calibration_required
modal_required
probe_required
probe_ready
harvesting
loading_next_video
waiting_modal_change
flushing
paused
completed
failed
```

## Backend payload evidence

`raw_dom_detail_metrics` now uses calibrated point source fields and active video duration. PASS sources are limited to:

- `calibrated_point_dom`
- `calibrated_point_ocr`
- `mixed_calibrated_point`

`raw_evidence_summary` uses:

```ts
{
  has_dom_detail_metrics: true,
  evidence_sources: [
    "calibrated_point_modal_counts",
    "smart_capture_harvest"
  ],
  evidence_collection_version: "phase12a_calibrated_five_point_workflow"
}
```

## Viewport source of truth

- The content script owns Douyin page viewport measurement via `getDouyinPageViewport()`.
- Popup requests page viewport from the content script.
- Popup does not use popup `window.innerWidth`/`window.innerHeight` as Douyin page viewport.
- If content-script viewport is unavailable, Smart Capture blocks with `content_script_viewport_unavailable` and retry guidance.
- Valid content-script viewport no longer produces stale `viewport_changed_significantly` blocking.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.

## Live retest steps

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Open a Douyin profile page.
3. Open the popup and confirm only the ten production buttons are visible.
4. Click `Smart Capture & Harvest` on the profile page.
5. Confirm the popup transitions to `modal_required` and asks to open the first video modal.
6. Open the first video modal.
7. Click `Start Right Rail Calibration`.
8. Click like, comment, favorite, share, then the next/down button.
9. Click `Probe Current Modal Metrics` and confirm PASS with all four counts and duration.
10. Click `Smart Capture & Harvest` or `Resume Harvest`.
11. Confirm the current item is extracted, flushed with explicit `capture_session_id`, and the calibrated next point is clicked.
12. Confirm harvest continues after `modal_id` changes.
13. Confirm `Show Progress` updates phase/current index/current metrics.
14. Stop or let harvest complete; confirm pending items flush safely.