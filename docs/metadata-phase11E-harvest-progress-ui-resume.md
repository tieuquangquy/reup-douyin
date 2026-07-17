# Phase 11E Harvest Progress UI Resume

## Status

Phase 11E implementation adds live Smart Capture & Harvest progress UI/state in `apps/extension-douyin-capture`.

## Files Changed

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popupProgress.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupProgress.test.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/package.json`
- `docs/metadata-phase11E-harvest-progress-ui-log.md`
- `docs/metadata-phase11E-harvest-progress-ui-resume.md`

## Progress Fields Added

- `current_state`
- `phase`
- `current_video_url`
- `failed_at_index`
- `failed_aweme_id`
- `last_flush_status`
- `next_flush_in_items`
- recent item `index`
- recent item `reason`

## Phase Update Points

- popup renders a synthetic `capturing_profile` progress panel while profile capture is running
- popup renders `starting` before harvest handoff
- controller sets `harvesting` when harvest starts
- controller sets `extracting_metrics` when a modal aweme is detected before extraction
- controller sets `queued_item` after successful metrics extraction and queueing
- controller sets `flushing` during backend flush
- controller sets `completed` when harvest reaches completion/target
- controller sets `failed` on extraction or flush failure
- controller sets `loading_next_video` before moving to the next modal video

## Popup Behavior

- progress panel appears near the top while running or after completed/failed state
- progress bar uses `harvested_count / target_count`
- last extracted metrics are formatted compactly
- duration/time values use `MM:SS` or `HH:MM:SS`
- counts and recent items render compactly
- Smart Capture, Start Calibration, and Clear Calibration are disabled/de-emphasized while running
- Stop Harvest, Flush Pending, and Show Progress remain enabled while running

## Verification Commands

Focused test already passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture exec tsx src/popupProgress.test.ts
```

Required final commands passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Steps

1. Reload the unpacked extension.
2. Open Douyin profile, then open a video modal.
3. Open popup and verify viewport remains `content_script` from Phase 11D.
4. Click `Smart Capture & Harvest`.
5. Verify `Harvest running` panel appears near the top.
6. Verify `Video X / Y`, current aweme, phase label, progress bar, metrics, counts, elapsed/avg/ETA, and recent items update.
7. Wait for a flush and verify Pending decreases while Flushed/Updated update.
8. Click `Show Progress` while running and verify panel refreshes without hiding Stop/Flush/Show Progress.
9. Click `Stop Harvest` and verify stopped reason/last error/next actions render.
10. Reopen popup and verify restored progress state is still visible.
