# TTS Temporal V4

`TTS_TEMPORAL_V4` is the production dialogue-dubbing path used by both frontend Generate TTS and the auto queue. Both entry points bind the same single Ops setup that is visibly `On`; the Ops Preview action remains a non-authoritative provider probe.

## Runtime flow

1. Resolve only current Translation rows linked to current Transcript timing and bind both translation input/authority hashes into the job.
2. Bind `tts_active_profile_authority_v1` to the one enabled setup; fail if zero or multiple setups are On and ignore stale legacy active pointers.
3. Run the provider-free `tts-input-preflight-v1` admission gate, then revalidate the immutable translation snapshot in the worker before provider construction.
4. Repair safe micro-boundaries and preserve speaker/source phrase evidence.
5. Rank only the approved text and alternatives carrying `tts_eligible=true`.
6. Build separate subtitle display text and Vietnamese provider speech text, including the profile-bound pronunciation glossary.
7. Plan a bounded initial speaking rate from quality-filtered, voice/model-specific calibration.
8. Try the exact fitted cache, then the raw acoustic cache, then the one bound provider.
9. Detect provider transport audio and normalize compressed formats locally to mono PCM WAV 48 kHz.
10. Trim provider edge silence, measure the WAV and synthesize an alternative/correction only after a measured miss, capped at three provider attempts per segment.
11. Apply pitch-preserving `atempo` only up to 1.15, a 6 ms edge fade and local waveform QA.
12. Assemble a full-duration narration timeline and retain the verified original music/SFX/ambient stem reference.
13. Persist subtitles, manifest, single-provider provenance, temporal QA and runtime-performance artifacts atomically.

## Cache authority

- `tts_segment_cache_v2`: display/speech text, duration slot, effective voice rate, provider/model, timing policy and V4 pipeline version.
- `tts_acoustic_cache_v1`: normalized speech text, provider/model and voice only; it deliberately excludes timeline duration and local fitting policy.
- WAV is written before JSON. JSON is the completion marker; hash or schema mismatch is a cache miss.
- Normal frontend generation is cache-first. `force_refresh=true` bypasses both layers intentionally.

## Performance artifact

`phase3_tts_performance.json` includes:

- fitted and acoustic cache hit counts;
- provider-generated clips, provider calls and batch calls;
- provider, local fit/QA and total elapsed milliseconds;
- warm-engine status and device when supported;
- provider-avoidance ratio.

## Quality gates

- Current transcript timing is physical authority.
- More than 15% post-provider overrun is blocked.
- Near-silent/invalid waveform is blocked.
- Clipping, DC offset and low peak remain explicit warnings for review/output QA.
- Subtitles always use display text; pronunciation expansion never leaks into rendered text.
- Every clip must match the bound provider, model and voice; fallback or mixed provenance is blocked.
- Render refuses legacy or stale narration after the active setup changes.
- Original music/SFX is referenced only from a verified separated background stem.

## Non-goals

- No full-video lip-sync model.
- No provider migration without measured local A/B evidence.
- No OCR, render or publish behavior changes in this release.
