# Transcript Editing Flow

This document describes how transcript editor actions map to API and persisted rows.

## Load

The editor loads three API resources:

- `GET /source-videos/{source_video_id}/transcript`
- `GET /source-videos/{source_video_id}/translation-draft`
- `GET /source-videos/{source_video_id}/audio-analysis-summary`

Frontend state joins `TranslationSegment` by `transcript_segment_id`.

## Save Draft

Changed rows are sent to:

```text
PUT /source-videos/{source_video_id}/transcript-draft
```

The payload includes:

- `transcript_segment_id`
- `translation_segment_id`
- `start_ms`
- `end_ms`
- `source_text`
- `translated_text`
- `status`

The API validates timing, updates current `TranscriptSegment` and `TranslationSegment` rows, and marks metadata with `edited_in_transcript_editor`.

Timing validation happens on the full current segment timeline after applying the submitted edits. The API rejects negative time, `end_ms <= start_ms`, and overlaps between current segments.

## Merge

```text
POST /source-videos/{source_video_id}/transcript-draft/merge
```

The API merges two current transcript rows:

- earlier segment keeps current status
- text and translated text are concatenated
- timing spans both segments
- flags are merged and `merged_segment` is added
- second transcript and translation rows become `is_current = false`

## Split

```text
POST /source-videos/{source_video_id}/transcript-draft/split
```

The API splits one current segment:

- original row becomes the left segment
- a new current row becomes the right segment
- translation draft is split the same way
- both rows are marked `NEEDS_REVIEW`

Phase 1 uses midpoint split and manual cleanup by the operator.

## Rerun

```text
POST /source-videos/{source_video_id}/translation-draft/rerun
```

This creates a new `ANALYZE_AUDIO` job with the requested translation preset. It does not run TTS or subtitle generation.

## Step 10 Contract

TTS/subtitle generation should use current edited rows only:

- `TranscriptSegment.is_current = true`
- `TranslationSegment.is_current = true`
- sort by transcript timing
- use `duration_budget_ms` and warning flags before synthesis
