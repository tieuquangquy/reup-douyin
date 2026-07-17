# Video Lifecycle

`source_videos.status` tracks the high-level lifecycle of a video from discovery through export and publish preparation. It is intentionally readable so API, worker, and UI code can share one vocabulary.

## Statuses

```text
DISCOVERED
FILTERED_IN
REJECTED
APPROVED_FOR_DOWNLOAD
DOWNLOADED
AI_ANALYZED
NEEDS_SCRIPT_REVIEW
NEEDS_OCR_REVIEW
READY_FOR_RENDER
RENDERING
READY_FINAL_REVIEW
EXPORTED
PUBLISH_READY
FAILED
```

## Expected Flow

```text
DISCOVERED
  -> FILTERED_IN
  -> APPROVED_FOR_DOWNLOAD
  -> DOWNLOADED
  -> AI_ANALYZED
  -> NEEDS_SCRIPT_REVIEW
  -> NEEDS_OCR_REVIEW
  -> READY_FOR_RENDER
  -> RENDERING
  -> READY_FINAL_REVIEW
  -> EXPORTED
  -> PUBLISH_READY
```

`REJECTED` can happen after discovery, filtering, scoring, or review. `FAILED` can happen from any processing state that cannot continue without intervention.

## Checkpoint Intent

- `NEEDS_SCRIPT_REVIEW`: transcript or translation needs operator review before render.
- `NEEDS_OCR_REVIEW`: detected text or overlays need operator review before render.
- `READY_FINAL_REVIEW`: rendered output exists and needs final operator approval before export/publish preparation.

## Related Tables

- `video_candidates.status` tracks review-board eligibility separately from the source video lifecycle.
- `video_review_decisions` stores checkpoint review history.
- `risk_flags` records safety and quality issues without forcing a terminal video state immediately.
- `media_assets` and `render_outputs` represent physical files and render attempts.

## Current Scope

This lifecycle is schema vocabulary only. Step 2 does not implement transition enforcement, crawler logic, scoring, review UI, rendering, export, or publishing.

