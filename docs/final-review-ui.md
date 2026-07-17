# Final Review UI

The final review screen is the last operator checkpoint before publish draft preparation. It is intentionally focused on fast inspection, not deep editing.

## Route

Phase 1 uses:

- `/source-videos/[id]/final-review`

The route loads the latest render output for the source video. If no render exists, the screen shows an empty state and sends the operator back to the review board.

## Screen Responsibilities

The screen shows:

- final rendered video
- original source video or raw source asset fallback
- render status, version, and publish-ready status
- render warnings and error summary
- risk warning summary and operator risk decisions
- render metadata such as format, resolution, FPS, codecs, duration, audio strategy, and subtitle burn flag
- a short operator checklist
- actions to approve export, mark publish-ready, rerender, or jump back to transcript review

It does not edit transcript, subtitles, OCR, render settings, or publish scheduling.

## Compare Modes

Phase 1 supports three compare modes:

- `side_by_side`: final and original are visible together.
- `final_only`: the operator focuses on final output playback.
- `original_only`: the operator checks the original source quickly.

The quick switch cycles through those modes. Playback sync is intentionally simple in Phase 1: both players are available, but frame-accurate synced playback is deferred.

## Review Checklist

The checklist is a local UI helper:

- Vietnamese narration is clear.
- Subtitle display is acceptable.
- Timing has no obvious drift.
- No obvious render artifacts.
- Final video plays normally.
- Warnings have been checked.

The checklist is not persisted in Phase 1. Approval and publish-ready state are persisted through API actions.

## Decision Actions

`Approve export` means the current `RenderOutput` is accepted as technically usable. It sets `RenderOutput.status = APPROVED`.

`Mark publish-ready` means the source video should move to publish draft preparation. It sets the current render approved if needed and marks the owning `SourceVideo.status = PUBLISH_READY`.

If risk scan reports blocking warnings, the operator must resolve/waive the warnings or record an explicit accepted-with-warning decision before continuing.

`Rerender` creates a new `RENDER_FINAL` job using the current render-prep manifest. When a new render completes, it becomes the latest output and the operator should review it again.

## Data Flow

Frontend calls:

- `GET /source-videos/{source_video_id}/latest-render`
- `GET /source-videos/{source_video_id}/asset-manifest`
- `GET /media-assets/{asset_id}/content`
- `POST /renders/{render_id}/approve`
- `POST /renders/{render_id}/mark-publish-ready`
- `POST /renders`

The final video player uses the `RenderOutput.media_asset_id`. The original player prefers the current `SOURCE_VIDEO_RAW` asset from the asset manifest and falls back to the original source URL if needed.

## Phase 1 Limits

- No persisted checklist.
- No multi-user approval history.
- No frame-accurate synced playback.
- No publish connector or scheduler.
- No OCR editor or render setting editor from this screen.
