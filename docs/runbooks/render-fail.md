# Render Fail Runbook

## Symptoms

- `RENDER_FINAL` job fails.
- `RenderOutput.status = FAILED`.
- Final review has no playable output.

## Common Causes

- Missing render-prep manifest.
- Missing source video, narration, or subtitle asset.
- ffmpeg unavailable or command failed.
- Output validation failed.
- Duration mismatch exceeded tolerance.

## Checks

- `GET /source-videos/{source_video_id}/render-prep-manifest`.
- `GET /source-videos/{source_video_id}/renders`.
- `GET /renders/{render_id}`.
- `GET /source-videos/{source_video_id}/assets`.
- Render log asset in `RenderOutput.metadata_json.render_log_asset_id`.

## Immediate Handling

- If input asset is missing, rerun the upstream step.
- If export failed, check ffmpeg availability and command metadata.
- If validation failed, inspect output probe summary.

## Rerun / Decision

- Rerun render after input assets are fixed.
- Mark needs_fix if subtitles or narration need editing first.
- Reject if repeated render output remains unusable.
