# Export Strategy Phase 1

Phase 1 render export is intentionally conservative.

## Audio Strategy

`audio_strategy = replace_with_vietnamese_narration`

The source Chinese audio is not kept as the main track. The render engine uses the joined Vietnamese narration from the render-prep manifest.

No background music mixing is attempted in this step. If a background stem is introduced later, it should be added through render-prep manifest extensions.

## Subtitle Burn Strategy

Subtitles are Vietnamese hard-burn subtitles.

The pipeline prefers the `SUBTITLE_SRT` export for ffmpeg because it is directly consumable by the subtitles filter. `SUBTITLE_JSON` remains the canonical render-facing data shape for future custom renderers.

Default styling is basic and stable:

- bottom safe area
- simple line wrapping from subtitle generation metadata
- no OCR-aware placement yet

## Output Profile

Default output:

- `mp4`
- video encoder: `libx264`
- audio encoder: `aac`
- keep source resolution and FPS where probe data is available
- preserve source aspect ratio

## Validation

After export:

- output path must exist
- file size must be greater than zero
- output probe must not fail
- duration mismatch is checked when both source and output duration are available

## Limits

- No multi-variant export.
- No OCR overlay.
- No inpainting.
- No lip-sync.
- No publish preparation.
