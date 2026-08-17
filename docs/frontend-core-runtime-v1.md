# Frontend core runtime binding v1

The real frontend buttons and Reup Queue `Start auto` share one
server-authoritative durable-job path. The browser sends an expected product
version, the API rejects a stale bundle with HTTP 409, and every new job stores
the exact installed runtime in `payload_json`, `context_json`, and
`metadata_json.frontend_stage_runtime`.

| Frontend stage | Product version | Installed recipe/components |
| --- | --- | --- |
| Download Video | `DOWNLOAD_V2` | `download-quality-policy-v2`, `post-download-qa-v1` |
| Analyze Audio | `AUDIO_ANALYSIS_V5` | `audio-analysis-v5-selective-dialogue-validation1` |
| Build Translation Draft | `TRANSLATION_V5` | `translation-v3-contextual-semantic-utterance-ranking-6` |
| Synthesize TTS | `TTS_TEMPORAL_V6` | `context-aware-tts-director-v2` + `gemini-whole-video-v1` + `whole-video-silence-alignment-v2` plus the single enabled Ops voice authority |
| Analyze OCR | `OCR-V34` | `audio_visual_temporal_v1`, `audio_visual_temporal_policy_v12_epoch_complete_cover`, zero network calls |

The worker verifies the complete hash-bound contract before the first executable
step. A persisted stale binding fails closed as
`INVALID_FRONTEND_RUNTIME_BINDING`; it is never silently upgraded. A legacy
queued job with no binding may be pinned exactly once before execution. This
compatibility rule does not apply to a job that already contains a different
version.

OCR-V34 is content-addressed by
`analyze_ocr_recipe_9a9f3fab0e5b8ca6a7966e9de0fdfba702b55b62fb90e905d6d838d7dcec2f86.json`.
Its promotion evidence is the local encoded-output QA run under
`apps/api/tmp_ocr_v34_generic_temporal_panel_fix`: 5,140 frames, zero residual
CJK, zero missing edit frames, zero residual-stroke frames, zero protected-source
damage, and maximum added flicker 4.3495 below the blocking threshold 12.
