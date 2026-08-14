# Core runtime frontend integration

The browser starts product actions, but the API and worker remain the runtime
authority. Every durable core job is stamped with `frontend_stage_runtime_v1`;
workers fail closed when a queued binding no longer matches the installed
runtime after a deploy.

## Current seven-stage contract

| Job type | Frontend stage version | Current recipe authority |
| --- | --- | --- |
| `DOWNLOAD_VIDEO` | `DOWNLOAD_V2` | `download-quality-policy-v2` + `post-download-qa-v1` |
| `ANALYZE_AUDIO` | `AUDIO_ANALYSIS_V5` | `audio-analysis-v5-selective-dialogue-validation1` |
| `BUILD_TRANSLATION_DRAFT` | `TRANSLATION_V5` | `translation-v3-contextual-semantic-utterance-ranking-5` |
| `SYNTHESIZE_TTS` | `TTS_TEMPORAL_V6` | `context-aware-tts-director-v2` + `gemini-whole-video-v1` + `whole-video-silence-alignment-v2` |
| `ANALYZE_OCR` | `OCR-V34` | official Analyze OCR immutable recipe |
| `RENDER_PREVIEW` | `QUALITY_LOCALIZATION_V24_1` | immutable pipeline recipe `V24.1` |
| `RENDER_FINAL` | `RENDER_PIPELINE_V1` | immutable pipeline recipe `V24.1` when quality workflow is active |

The browser expectations live in `apps/web/src/lib/coreRuntime.ts`. The server
contract is built from installed backend constants in
`apps/api/src/services/frontend_core_runtime.py`; it must not trust browser
implementation details.

## Upgrade rule

Do not copy an older route, schema, API client, or service file over a newer
version. Port behavior in this order:

1. core service behavior;
2. durable job payload and runtime binding;
3. API request/response contract;
4. TypeScript types and API client;
5. operator UI;
6. contract and behavioral regression tests.

The newer contract wins during conflicts. Existing optimized behavior is kept
only when its behavioral tests pass under the current runtime authority.

## Preserved optimized behavior

- Download remains cache-first, resumable, provenance-aware, no-logo strict,
  and post-download QA guarded.
- Analyze Audio retains canonical/target-speech authority, selective dialogue
  validation, semantic segmentation, and downstream invalidation.
- Translation retains source approval, contextual ranking, temporal budget,
  quality contract, and TTS readiness gates.
- TTS retains provider-neutral authority, one-voice continuity, capability-
  gated emotion planning, temporal fitting, caching, and waveform/prosody QA.
