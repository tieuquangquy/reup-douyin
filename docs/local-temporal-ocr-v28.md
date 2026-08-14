# Analyze OCR V28

`OCR-V28` is the official local-only Analyze OCR recipe used by the frontend
durable `ANALYZE_OCR` job. It keeps `v58_candidate` as Phase 1 authority and
does not enable Authority V3.6 full-duration.

## Production path

```text
Frontend -> POST /ocr -> durable ANALYZE_OCR job -> worker
-> QualityLocalizationService.run_phase12 -> MasterPhase1Extractor
```

The production job builds audio candidate windows from current persisted
`TranscriptSegment` rows. Rejected, empty, and invalid-timing rows are excluded.
The seed is hash-bound to transcript content, Analyze Audio version and
fingerprint, and persisted VAD speech state.

If VAD confirms speech but no usable transcript timing exists, Analyze OCR
fails closed and asks the operator to re-run Analyze Audio. A verified
no-dialogue source is the only normal path to `VISUAL_ONLY` mode.

## Scheduling policy

- Every source frame is inspected using an FFmpeg proxy with a 512-pixel long
  edge; a 720x1280 source therefore uses a 288x512 raster.
- Expensive local text detection runs at 4 FPS inside audio windows.
- Outside audio windows, visual completeness runs at 2 FPS, with 0.5 FPS safety
  heartbeat and bounded 8 FPS transition bursts.
- Ordinary local texture change respects a 900 ms cooldown. Only a strong text
  appearance/disappearance boundary may bypass it for one-frame CJK recall.
- Coverage closure continues to inspect every frame with its lightweight
  384-pixel proxy; it does not run full OCR on every frame.

## Frontend evidence

The OCR summary exposes `analysis_mode`, `audio_window_count`,
`visual_trigger_count`, `all_frame_proxy_size`, detector frame count and elapsed
time. For a normal 720x1280 video with speech, the expected evidence is:

```text
analysis_mode = AUDIO_GUIDED_VISUAL
audio_window_count > 0
all_frame_proxy_size = [288, 512]
analysis_decode_backend = ffmpeg_two_pass_selected_rawvideo
network_calls = 0
fallback_used = false
```

The recipe is content-addressed at
`docs/pipeline-recipes/analyze_ocr_recipe_8c48ed0bb10faa73d1cea6534ddf3f07877bd08a50a3177d7d18ba5410323040.json`.
