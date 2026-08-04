# Render Prep Manifest V2

`RENDER_PREP_MANIFEST_V2` is the immutable boundary between TTS/subtitle generation and Phase 4 render. Render consumes this contract instead of rediscovering current assets from translation rows or guessing local file paths.

## Authority rules

- The manifest is stored as the current `RENDER_PREP_MANIFEST` media asset.
- Only current media assets are included, deduplicated by asset ID.
- Every renderable asset carries `storage_key`, MIME type, SHA-256 and size.
- Only safe metadata is exported; absolute paths are excluded.
- `input_authority.translation_input_sha256` binds outputs to the locked translation.
- Final render requires exactly one valid joined narration and `audio_review.status = AUDIO_APPROVED`.

## Shape

```json
{
  "manifest_version": "RENDER_PREP_MANIFEST_V2",
  "pipeline_version": "TTS_PIPELINE_V2",
  "source_video": {
    "id": "source-video-uuid",
    "external_id": "douyin-video-id",
    "duration_seconds": 27.0
  },
  "input_authority": {
    "translation_input_sha256": "64-hex-sha256"
  },
  "current_outputs": {
    "tts_clips": [],
    "joined_narration": [
      {
        "id": "media-asset-uuid",
        "storage_key": "workspace/video/audio/v2_joined_narration.wav",
        "mime_type": "audio/wav",
        "sha256": "64-hex-sha256",
        "size_bytes": 2592044,
        "duration_seconds": 27.0,
        "audio_format": {
          "codec": "pcm_s16le",
          "sample_rate_hz": 48000,
          "channels": 1,
          "sample_width_bytes": 2
        },
        "metadata": {
          "assembly_strategy": "full_duration_timeline_mix",
          "timing_map": []
        }
      }
    ],
    "subtitle_json": [],
    "subtitle_srt": [],
    "cleaned_video": [],
    "ocr_events": [],
    "background_audio": []
  },
  "timing_fit_summary": {
    "fits_well": 1
  },
  "duration_gate_summary": {
    "fits_budget": 1
  },
  "audio_review": {
    "status": "PENDING_AUDIO_REVIEW",
    "approved_at": null,
    "operator_id": null
  },
  "render_contract": {
    "source_video_asset_type": "SOURCE_VIDEO_RAW",
    "narration_asset_type": "TTS_AUDIO_JOINED",
    "subtitle_asset_type": "SUBTITLE_JSON",
    "subtitle_track_kind": "vietnamese_hard_burn",
    "audio_strategy": "replace_with_timeline_aligned_vietnamese_narration"
  }
}
```

`source_video_asset_type` is `CLEANED_VIDEO` when a current cleaned plate exists at TTS preparation time; otherwise it is `SOURCE_VIDEO_RAW`.

Each `tts_clips[]` item may expose safe `metadata.speech_budget` evidence: estimated spoken units and fit range, calibration source/sample count, observed provider duration, observed speech rate, actual timing ratio and timing quality band. `duration_gate_summary` counts the advisory pre-synthesis statuses (`fits_budget`, `too_long`, `too_short`) across clips. Render and final approval must still use the measured clip/joined-audio duration and hashes as authority.

## Operator staging and approval

Staging verifies the source WAV hash, copies it into the Phase 4 artifact root, rewrites only the staged storage reference and keeps the review state pending. Identical duplicate references are collapsed by `(storage_key, sha256)`; distinct competing narration references fail closed.

Approval creates a separate `phase4_audio_approval.json` and records operator ID, approval time and narration hash. The approval does not overwrite Phase 1, Phase 2 or Phase 3 timeline artifacts.

## Render usage

Phase 4 must:

1. Validate manifest version and translation/hash authority.
2. Require `AUDIO_APPROVED` for final render.
3. Resolve and re-hash `phase4_joined_narration.wav` before muxing.
4. Optionally resolve and re-hash one `background_audio` no-vocals stem.
5. Use narration-only when no verified background stem exists.
6. Run encoded-output audio QA before declaring `FINAL_RENDERED`.

The manifest is a contract, not a cache hint. A missing file, hash mismatch, invalid MIME type, multiple distinct narration refs or unapproved audio blocks final handoff.
