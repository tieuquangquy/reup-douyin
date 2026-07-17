# Filter Presets

Filter presets bundle default thresholds and score weights. They are defined in a registry, not in route handlers.

## `viral_discovery`

Use when the operator wants high-upside recent videos.

Prioritizes:

- recent videos
- views
- like/share quality
- broad discovery

Defaults include recent date range, minimum views, minimum like/share rate, and score sorting.

## `safe_reup`

Use when the operator wants fewer editing and compliance surprises.

Prioritizes:

- speech availability
- manageable duration
- lower text density
- no heavy watermark
- no high copyright risk
- lower processing complexity

## `affiliate_priority`

Use when the operator wants videos that may convert better for product or affiliate workflows.

Prioritizes:

- medium duration
- comment/share signal
- lower text density
- low watermark/copyright risk
- content that is easier to localize

## Adding A Preset

1. Add a `FilterPreset` entry in `filter_presets.py`.
2. Set clear thresholds and sort mode.
3. Tune `ScoreWeights` only if the preset has a different ranking intent.
4. Add tests if behavior differs meaningfully.

## Phase 1 Note

Presets can use content signals before all analysis pipelines exist. Missing signals do not crash evaluation; they produce warnings and conservative scoring.

