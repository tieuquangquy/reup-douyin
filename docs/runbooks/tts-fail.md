# TTS Fail Runbook

## Symptoms

- `SYNTHESIZE_TTS` job fails.
- No joined narration asset.
- Subtitle endpoint works but TTS summary is missing.

## Common Causes

- Missing or empty `TranslationSegment`.
- TTS provider placeholder/engine failed.
- Generated clip failed validation.
- Narration assembly failed.
- Duration mismatch warnings are too large.

## Checks

- `GET /source-videos/{source_video_id}/translation-draft`.
- `GET /source-videos/{source_video_id}/tts-summary`.
- `GET /source-videos/{source_video_id}/render-prep-manifest`.
- Job step around `synthesize_segment_clips`, `assemble_narration_track`, `build_render_prep_manifest`.

## Immediate Handling

- Fix empty translation in transcript editor.
- Shorten translated text when `translation_too_long_for_slot` appears.
- Rerun TTS after text changes.

## Rerun / Decision

- Rerun if provider failure is transient.
- Mark needs_fix if the translation is too long or awkward.
- Reject if voice output cannot be made acceptable for alpha.
