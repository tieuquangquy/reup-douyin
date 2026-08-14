# TTS Temporal V5

> Superseded by `TTS_TEMPORAL_V6` for whole-video timing recovery. V5 remains
> documented as the original one-request Gemini architecture.

`TTS_TEMPORAL_V5` replaces sentence-by-sentence Gemini Expressive synthesis
with a low-call narration lane while preserving the provider-neutral TTS path
for every other configured provider.

## Gemini production strategy

- `whole_video`: one provider request when the narration fits the configured
  180-second/6000-character admission boundary.
- Oversized input: deterministic 45-second blocks with durable acoustic cache.
- `auto_blocks`: force bounded blocks for provider experiments.
- `segment`: legacy behavior, retained only as an operator fallback.

Only `google_gemini` with `single_voice_mode=required` can enter this lane.
Google Classic and every other provider continue through the segment pipeline.

Before synthesis, dense rows may select the shortest token-safe candidate that
Translation Draft already approved. No new translation is invented in TTS.
Provider audio is cached before local fit, so a retry does not pay again for a
successful block. Timing overflow is terminal and never retries the whole job.

After a whole-video response, `whole-video-silence-alignment-v1` searches for
low-energy boundaries around each expected source timestamp. Natural pauses
become exact per-segment clips; a weak boundary falls back to the monotonic
expected cut and records `whole_video_alignment_low_confidence`. Every slice is
then subject to the existing 1.15 pitch-preserving timing gate.

## Frontend contract

Ops TTS settings expose the strategy and its bounds. Transcript TTS reports
show the installed V5 runtime, provider request count, narration block count,
strategy, cache hits, total elapsed time, and whether the video was generated
in one provider request. Queue progress uses
`synthesize_narration_block|current|total`.
