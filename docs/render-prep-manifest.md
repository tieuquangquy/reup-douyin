# Render Prep Manifest

The render-prep manifest is the contract between TTS/subtitle generation and the future render engine. Render should consume this manifest instead of guessing which assets are current.

## Manifest Strategy

The manifest is stored as a current `RENDER_PREP_MANIFEST` media asset. DB rows remain canonical, but the manifest packages the current render inputs into a single render-facing document.

## Shape

```json
{
  "manifest_version": "RENDER_PREP_MANIFEST_V1",
  "pipeline_version": "TTS_PIPELINE_V1",
  "source_video": {
    "id": "source-video-id",
    "external_id": "douyin-video-id"
  },
  "current_outputs": {
    "tts_clips": [],
    "joined_narration": [
      {
        "storage_key": "workspace/video/audio/v1_joined_narration.wav",
        "mime_type": "audio/wav",
        "metadata_json": {
          "timing_map": []
        }
      }
    ],
    "subtitle_json": [],
    "subtitle_srt": [],
    "cleaned_video": [],
    "ocr_events": []
  },
  "subtitle_version": "TTS_PIPELINE_V1_RUN_1",
  "timing_fit_summary": {
    "fits_well": 8,
    "slightly_long": 2
  },
  "provider_summary": {
    "tts_provider": "placeholder_tone_tts"
  },
  "warnings": [],
  "render_contract": {
    "source_video_asset_type": "CLEANED_VIDEO",
    "narration_asset_type": "TTS_AUDIO_JOINED",
    "subtitle_asset_type": "SUBTITLE_JSON",
    "subtitle_track_kind": "vietnamese_hard_burn"
  }
}
```

`source_video_asset_type` is `CLEANED_VIDEO` when a current cleaned plate exists at TTS prep time; otherwise `SOURCE_VIDEO_RAW`. `RenderInputResolver` also prefers live `CLEANED_VIDEO` at render time.

## Render Usage

Render step should:

1. Prefer current `CLEANED_VIDEO`, else `SOURCE_VIDEO_RAW`.
2. Load `TTS_AUDIO_JOINED` from render-prep manifest.
3. Load `SUBTITLE_SRT` (preferred) or `SUBTITLE_JSON`.
4. Use `timing_map` and subtitle segment timing.
5. Surface `timing_fit_summary` and warnings before final render.

## Phase 1 Limits

- Manifest is JSON-only.
- No render preset selection.
- No OCR overlay references yet (VI burn uses TTS subtitle assets; hard-sub removal is a separate `CLEANED_VIDEO` plate — see `docs/ocr-hardsub-pipeline.md`).
