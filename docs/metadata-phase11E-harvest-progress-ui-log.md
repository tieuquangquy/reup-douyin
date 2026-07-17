# Phase 11E Harvest Progress UI Log

## Scope

Phase 11E added live progress/loading UI for Smart Capture & Harvest in `apps/extension-douyin-capture` only. It did not change backend API, Capture Inbox, CDP/debug workflow, or calibrated point extraction logic beyond progress state updates.

## Progress Fields Added

`FullModalHarvestProgress` now carries popup-facing live fields:

- `current_state`
- `phase`
- `current_video_url`
- `failed_at_index`
- `failed_aweme_id`
- `last_flush_status`
- `next_flush_in_items`

Persisted harvest state now stores the same state needed to restore popup progress after popup close/reopen. Recent item summaries now include optional `index` and `reason`; `recent_items` remains capped to the last 5.

## Phases Shown In Popup

The popup maps these phases to compact operator labels:

- `starting` -> `Starting...`
- `capturing_profile` -> `Capturing profile...`
- `harvesting` -> `Harvesting...`
- `loading_next_video` -> `Loading next video...`
- `waiting_modal_change` -> `Waiting for modal change...`
- `extracting_metrics` -> `Extracting metrics...`
- `queued_item` -> `Queued item...`
- `flushing` -> `Flushing batch...`
- `completed` -> `Completed`
- `failed` -> `Failed`

## Progress Panel Layout

The popup now renders a top progress panel with:

- title: `Harvest running`, `Harvest completed`, or `Harvest failed`
- `Video X / Y`
- current aweme id
- phase pill
- progress bar based on `harvested_count / target_count`
- last metrics: Duration, Likes, Comments, Favorites, Shares
- counts: Harvested, Pending, Flushed, Updated, Failed, Duplicates
- time: Elapsed, Avg/video, ETA
- recent item list capped to 5
- failure details and next actions when stopped/failed

## Tests Run During Implementation

Initial focused check:

```bash
npm --workspace @reup-douyin/extension-douyin-capture exec tsx src/popupProgress.test.ts
```

Final required verification is recorded in the resume doc after the full command set is run.

## Live Retest Steps

1. Reload the unpacked extension in Chrome/Edge.
2. Open a Douyin profile and click a video so the URL includes `modal_id`.
3. Open the extension popup.
4. Click `Smart Capture & Harvest`.
5. Confirm the progress panel appears near the top with `Harvest running`.
6. Confirm it shows `Video X / Y`, current aweme id, phase label, progress bar, metrics, counts, elapsed/avg/ETA, and recent items.
7. Let a flush happen and confirm Pending decreases while Flushed/Updated change.
8. Stop or trigger a controlled failure and confirm stopped reason, failed index/aweme/error, and next actions are shown.
