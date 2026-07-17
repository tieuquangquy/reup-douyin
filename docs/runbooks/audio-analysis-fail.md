# Audio Analysis Fail Runbook

## Symptoms

- `ANALYZE_AUDIO` job fails.
- Transcript endpoint returns no segments.
- Translation draft is empty.

## Common Causes

- Missing `SOURCE_VIDEO_RAW` or `SOURCE_AUDIO_EXTRACT`.
- Audio extraction placeholder/provider failed.
- STT provider returned empty units.
- Translation provider failed.
- Segment timing validation failed.

## Checks

- `GET /source-videos/{source_video_id}/asset-manifest`.
- `GET /source-videos/{source_video_id}/audio-analysis-summary`.
- `GET /source-videos/{source_video_id}/transcript`.
- Job step around `resolve_assets`, `extract_audio_if_needed`, `transcribe`, `build_translation_draft`.

## Immediate Handling

- If source asset is missing, run download first.
- If transcript exists but translation is missing, rerun translation draft only if supported.
- If confidence flags are high, use transcript editor instead of hiding warning.

## Rerun / Decision

- Rerun audio analysis after source asset is fixed.
- Mark needs_fix if transcript quality is poor but editable.
- Reject if audio is unusable for localization.
