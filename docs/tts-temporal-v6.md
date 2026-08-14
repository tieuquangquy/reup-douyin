# TTS Temporal V6

`TTS_TEMPORAL_V6` keeps the V5 one-request Gemini Expressive architecture and
replaces its local timing recovery with `whole-video-silence-alignment-v2`.

V6 performs three local operations after the provider WAV is safely cached:

1. Apply the already-calculated block-level atempo correction before locating
   sentence boundaries.
2. Select the complete monotonic boundary sequence from stable 160 ms acoustic
   valleys, using the source timeline and approved text density only as weak
   priors. Brief intra-word or intra-phrase minima are rejected.
3. Fit each recovered sentence using its source slot plus only the real empty
   gap before the next segment. If necessary, one bounded block refinement
   spreads a small residual correction across the narration instead of heavily
   accelerating a single emotional sentence.
4. If provider variability still leaves unsafe sentences, synthesize their
   shortest already-approved Translation Draft candidates together in one
   compact repair batch. This adds at most one request for the affected block,
   preserves the configured Voice ID, and never invents replacement wording.

The combined block correction remains capped by the existing 1.15
pitch-preserving safety limit. Provider audio, approved text, segment order,
voice ID, and emotion plan are unchanged. Retries reuse the acoustic cache and
do not create another paid Gemini request unless the provider input itself has
changed.

Runtime QA exposes block fit/refit counts, borrowed gap count and milliseconds,
alignment confidence, boundary shift, original source slot, effective fit slot,
and the combined atempo factor. The frontend handshake is
`SYNTHESIZE_TTS=TTS_TEMPORAL_V6`.
