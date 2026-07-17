# Render Engine Overview

The render engine is the only step that assembles media into a final video file. It consumes the current render-prep manifest from step 10 and should not rediscover TTS/subtitle inputs from raw translation rows.

## Inputs

- Current `RENDER_PREP_MANIFEST`
- Current `CLEANED_VIDEO` when available (hard-sub cleaned plate), else `SOURCE_VIDEO_RAW`
- Joined narration asset from render-prep manifest
- Subtitle export from render-prep manifest, preferring `SUBTITLE_SRT` for ffmpeg burn and falling back to `SUBTITLE_JSON` for non-ffmpeg runners

## Pipeline Layers

- `RenderInputResolver`: validates and resolves current input assets.
- `VideoProbeService`: inspects source/output media metadata. Phase 1 uses storage metadata fallback; ffprobe can replace it later.
- `ExportRunner`: abstraction for render command execution.
- `FfmpegRenderRunner`: default runner for local phase 1.
- `CopyMockRenderRunner`: test runner only.
- `RenderService`: orchestrates output registration, `RenderOutput`, media assets, and render manifest.

## Job Flow

`RENDER_FINAL` steps:

1. `validate_input`
2. `resolve_render_prep`
3. `probe_source_video`
4. `prepare_audio`
5. `prepare_subtitle_burn`
6. `export_video`
7. `validate_output`
8. `persist_render_output`
9. `finalize`

The worker executes the real render service at `persist_render_output`.

## Phase 1 Strategy

- Replace source audio with Vietnamese joined narration.
- Burn Vietnamese subtitle using the render-prep subtitle export.
- Preserve source ratio/resolution/FPS by default where the runner can inspect it.
- Export final video as MP4 with H.264-style video encoding and AAC audio.

## Limits

- Prefer `CLEANED_VIDEO` (hard-sub band blurred via OCR pipeline) when present; otherwise fall back to `SOURCE_VIDEO_RAW` with warning `no_cleaned_video_fallback_raw`.
- No OCR overlay burn of Chinese text (VI burn uses TTS subtitle export only).
- No final review publish gate beyond existing checklist.
- No lip-sync.
- Probe is currently metadata fallback unless a richer runner/probe is introduced.
