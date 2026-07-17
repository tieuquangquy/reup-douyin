# Render Output Model

`RenderOutput` is the canonical DB record for a generated video output.

## Important Fields

- `source_video_id`
- `media_asset_id`
- `status`
- `render_type`
- `output_format`
- `width`
- `height`
- `fps`
- `duration_seconds`
- `video_codec`
- `audio_codec`
- `subtitle_burned`
- `audio_strategy`
- `render_version`
- `created_by_job_id`
- `warning_summary_json`
- `render_settings_json`
- `metadata_json`
- `started_at`
- `finished_at`
- `error_message`

The final video file is registered as `MediaAsset` type `FINAL_RENDER_VIDEO`. Render logs and manifests are registered as `RENDER_LOG` and `RENDER_MANIFEST`.

## Current Strategy

The newest render is read by ordering `RenderOutput.created_at` descending. Phase 1 keeps older render outputs for trace/debug instead of deleting or overwriting them.

Render assets are versioned through `MediaAsset.version` and marked current/non-current with `is_current`.

## Failure Strategy

If rendering fails after a `RenderOutput` row is created:

- `RenderOutput.status = FAILED`
- `error_message` stores the stable error code and message
- `finished_at` is set

This gives the final review and operations screens a clear failure state.

## Final Review Contract

Step 12 should use:

- latest `RenderOutput`
- linked `FINAL_RENDER_VIDEO` asset
- `metadata_json.manifest`
- `warning_summary_json`

It should not reconstruct render inputs from transcript, subtitle, or TTS rows.
