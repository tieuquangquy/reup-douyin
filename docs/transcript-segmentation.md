# Transcript Segmentation

`TranscriptSegment` is the canonical transcript unit for review and later TTS/subtitle work.

## Segment Fields

Important fields:

- `source_video_id`
- `segment_index`
- `version`
- `start_ms`
- `end_ms`
- `text`
- `normalized_text`
- `language_code`
- `confidence`
- `speaker_label`
- `difficulty_flags_json`
- `analysis_version`
- `created_by_job_id`
- `is_current`

The older `start_ms`, `end_ms`, and `text` fields remain the canonical timing/text columns. New fields add review and trace context without replacing them.

## Builder Rules

`TranscriptBuilder` converts provider transcription units into rows:

- Drops empty text and invalid timing.
- Sorts by start time.
- Normalizes whitespace.
- Assigns stable zero-based `segment_index`.
- Copies confidence and speaker label when available.
- Adds difficulty flags.

## Difficulty Flags

Current flags:

- `low_confidence`
- `overlapping_speech`
- `background_too_loud`
- `too_short`
- `too_long`
- `likely_mistranscribed`
- provider-specific flags such as `caption_fallback`

Flags are review hints, not final judgments. The editor should surface them so the operator knows where to spend time.

## Timing

Segments persist millisecond timing in DB. API responses expose those fields directly. UI can derive seconds as:

```text
start_time_seconds = start_ms / 1000
end_time_seconds = end_ms / 1000
duration_seconds = (end_ms - start_ms) / 1000
```

## Phase 1 Limits

- No real speaker diarization is implemented.
- Merge/split is basic and deterministic.
- Segment quality depends on the configured STT provider.
- The caption fallback provider is for pipeline continuity, not production-grade STT.
