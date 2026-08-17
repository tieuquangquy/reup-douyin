# TTS Pipeline V4

The TTS pipeline converts the current, operator-locked Vietnamese translation into timeline-aligned narration and subtitle assets. It is local-first, but provider, storage and job boundaries remain replaceable for a future SaaS runtime.

## Input authority

- Current `TranslationSegment` rows (`is_current = true`).
- Linked source timing from `TranscriptSegment`.
- Source video duration.
- Exactly one Ops TTS setup visibly enabled (`On`); a legacy `active_profile_id` pointer has no production authority.
- A secret-free `profile_id + config_fingerprint` snapshot persisted on every durable Generate/auto job.
- The exact `translation_input_sha256` and `translation_authority_sha256` persisted in the durable job payload and revalidated by the worker before provider construction.

The service rejects missing text, invalid timing, overlapping segments and segments outside the source-video timeline. A local `tts-input-preflight-v1` manifest also checks remaining CJK, protected-token preservation, review flags, normalized speech text, approved alternatives and predicted timing fit before a paid/provider boundary. Only `READY` and `AUTO_FIT` rows are admitted; `NEEDS_REVIEW` and `BLOCKED` rows do not create a job.

## Provider boundary

The core pipeline calls a `TtsProvider` interface. A provider receives text, language, voice configuration and an optional duration target, and returns audio bytes plus duration, MIME type, metadata and warnings.

Production provider selection comes only from the setup visibly `On` in Ops. There is no ENV, recipe, disabled-profile or provider fallback for durable TTS. If zero or multiple setups are On, the API returns `tts_active_setup_required` and does not synthesize. Preview may still probe an unsaved/disabled draft, but Preview never becomes render authority.

Provider transport audio may be WAV, MP3, OGG, Opus, WebM, FLAC, M4A or AAC. Production detects the actual payload and normalizes it locally with FFmpeg to mono 48 kHz 16-bit PCM WAV before silence trimming, measured-duration fitting, cache persistence and narration assembly. A compressed or malformed payload is reported as `tts_provider_failed`; it is never mislabeled and persisted as WAV.

## Cloud and HTTP catalog discovery in Ops

`/ops/tts-ai` can discover selectable provider metadata from draft credentials without requiring the operator to save them first. **Refresh catalog** calls `POST /ops/tts-ai/test` with `probe_mode=catalog`; the API resolves the saved or draft key server-side and performs bounded, read-only catalog requests. Providers with a curated catalog return it without a paid synthesis request.

- OpenAI and OpenAI-compatible endpoints load `/models`; official OpenAI voices use reviewed presets because OpenAI does not expose a voice-list endpoint.
- ElevenLabs loads its model and voice catalogs with `xi-api-key` authentication.
- Google Cloud TTS and Azure Speech load voice catalogs. Their classic APIs select the synthesis family through the voice, so they do not expose a separate model list.
- `http_custom` tries the common `/models`, `/voices`, and `/languages` shapes. Because there is no universal TTS catalog standard, manual Model ID, Voice ID, and Language code entry remains available when discovery is partial or unsupported.

Choose `openai_compatible` only when the vendor documents the compatible `/models` and synthesis contracts. A proprietary service such as GenMax may accept Bearer authentication without exposing `/models`, `/voices`, or `/languages`; use the versioned `options_json.http_connector` mapping and manual IDs instead of inventing those endpoints.

The manifest contract, independent authentication/catalog/synthesis stages, no-catalog workflow, examples, and security requirements are documented in [Universal HTTP TTS Connector V1](./tts-universal-connector.md).

When vendors return richer metadata, the catalog also carries display labels, model/voice compatibility, language codes, gender, descriptions, and capability/modality tags. The web form uses that metadata to narrow dependent choices without discarding an operator-entered custom ID.

Remote discovery is separate from synthesis readiness. A provider may return a valid catalog while its `reup-douyin` synthesis adapter is still planned; Preview and durable jobs must continue to fail closed until that adapter is implemented and tested.

Catalog requests use a short capped timeout, bounded JSON responses, same-origin redirects, and public HTTP(S) endpoint validation. API keys and raw vendor response bodies must never appear in returned catalog metadata, runtime warnings, or logs. The last safe catalog snapshot is persisted under the profile's `runtime.last_probe` so the UI can reopen the saved choices and mark them stale when the endpoint or key changes.

### Google Cloud Text-to-Speech authentication

Google Cloud Text-to-Speech requires OAuth 2.0. An Agent Platform key or a regular API key is not accepted by `texttospeech.googleapis.com`; the provider returns `API keys are not supported by this API` when such a key is used.

The Google setup supports three explicit credential modes:

- **Service Account JSON** (recommended for the local operator): upload the downloaded JSON once. The API validates the service-account type, Google token URI, client email, project ID, and RSA private key before encrypting the normalized JSON with the platform credential envelope. Public API responses expose only the configured flag, client email, and project ID.
- **Application Default Credentials**: the API and worker use credentials configured on their runtime host. No secret is uploaded through the web app.
- **Temporary OAuth access token**: retained only for short diagnostics. It expires and is not suitable for durable automation.

At runtime, `google-auth` obtains and refreshes a short-lived access token using the Cloud Platform scope. Tokens are cached in process only until shortly before expiry; they are never persisted or returned. Voice discovery calls `GET /v1/voices`, synthesis calls `POST /v1/text:synthesize`, and the response reads Base64 audio from `audioContent` with `Authorization: Bearer <token>`.

Cloud Text-to-Speech does not currently expose a dedicated predefined `roles/texttospeech.user` role. For a standalone Service Account in this local setup, enable the API and grant the project-level **Service Usage Consumer** role (`roles/serviceusage.serviceUsageConsumer`) so the identity can consume the enabled API without receiving Editor/Owner access. Never commit the downloaded JSON file. API and worker deployments must share the same `PLATFORM_CREDENTIAL_ENCRYPTION_KEY_REF`; local development uses the existing server-only local credential key store.

### Google Cloud Agent Platform TTS

`google_cloud_tts` is an additive Gemini expressive provider and does not replace the legacy `google_gemini` AI Studio/Vertex OAuth profile. It uses `google-genai` with `vertexai=True` and an Agent Platform Express Mode API key. API-key mode is global and therefore does not accept a project/location pair.

The curated model catalog contains `gemini-2.5-flash-tts`, `gemini-3.1-flash-preview-tts`, `gemini-2.5-pro-tts`, and `gemini-2.5-flash-lite-preview-tts`; new profiles default to Gemini 2.5 Flash TTS with the Achernar voice because it has broader regional availability. The catalog is curated because Vertex `models.list` requires OAuth2 even when audio generation accepts an Express Mode API key. Refresh Catalog is offline for this provider. Ops Test Connection validates credentials and model access with one short real audio generation call. Preview and durable jobs use the same native SDK adapter. If a configured model returns a publisher-model 404, the provider tries the curated fallback order once, records requested/resolved model IDs and reuses the resolved model for the rest of that job; authentication, quota and transient failures do not trigger this fallback.

The provider participates in the existing text-conditioned emotion planner, provider instruction lowering, whole-video/auto-block strategy, single-voice enforcement, timing QA, and normalized WAV boundary. Chirp 3 HD remains in the classic Google Cloud TTS lane because it does not implement the same Gemini text-conditioned expressive contract.

## Timing policy

Every clip is normalized to mono PCM s16le at 48 kHz before persistence and assembly.

- Clip duration less than or equal to its slot: keep the clip and leave tail silence.
- Overrun from 0% through 7%: use FFmpeg `atempo` in the natural adjustment band.
- Overrun above 7% through 15%: use FFmpeg `atempo`, emit `timing_adjustment_review_recommended`, and expose the review quality band.
- Overrun greater than 15%: fail closed with `TIMING_FIT_BLOCKED`.

Synthesized audio duration is always the final timing authority. A pre-synthesis speech-budget estimate is advisory: it improves translation review and diagnostics, but never bypasses the measured-audio gate or silently changes operator-approved text.

## Duration-aware speech budget

Before synthesis, Vietnamese text is counted as spoken units rather than raw characters. Common numbers and units such as `510 kcal`, `22.9 g`, `kg`, `ml` and `%` receive approximate spoken costs. The budget:

- reserves 250 ms for each punctuation pause, capped at 40% of the slot;
- keeps a 400 ms minimum speech window for very short slots;
- defaults to 4.5 spoken units per second with a +/-20% fit range;
- calibrates by provider, model ID, voice ID and speaking rate from matching prior clips after at least three valid samples;
- learns only from clips with valid waveform QA and natural/no speed adjustment, excluding heavily trimmed or acoustically unsafe clips;
- uses a robust median/MAD filter, ignores implausible samples outside 2-9 units per second and exposes low/medium/high confidence.

Each clip persists the estimate, calibration source, observed duration, observed speech duration, observed units per second, actual timing ratio and `timing_quality_band` under `speech_budget`. Punctuation pause is subtracted from observed total duration when learning the rate so future estimates do not double-count pauses.

The assembler places each clip at its exact `start_ms` on a full-duration silent timeline. It rejects overlap, spill and out-of-range placement. The joined WAV therefore has the same duration as the source video and no downstream renderer needs to reconstruct timing from concatenated clips.

## Durable execution and idempotency

The stable idempotency key covers TTS pipeline version, source video ID, translation input hash and the active setup fingerprint. Active-job reuse additionally requires both translation snapshot fields to match; legacy/stale active jobs are not reused. A worker that observes a changed Translation Draft fails with `tts_authority_changed` before constructing/calling the provider. Legacy direct requests without snapshot fields remain runnable for compatibility. An identical rerun reuses the existing result; `force_refresh=true` intentionally creates a new current version.

Automatic retry remains bounded. After that budget is exhausted, an explicit operator Retry or Generate TTS action grants one additional attempt so a corrected decoder/provider configuration can resume the durable job without deleting database state.

The provider-free handoff can be measured locally without credentials or paid calls:

```powershell
python -m scripts.benchmark_tts_handoff --iterations 200 --segments 100
```

The `SYNTHESIZE_TTS` lifecycle is:

1. Validate the source and resolve current translation segments.
2. Synthesize each Vietnamese clip.
3. Normalize audio format and apply the safe timing policy.
4. Persist versioned `TTS_AUDIO_CLIP` assets.
5. Assemble the full-duration `TTS_AUDIO_JOINED` timeline.
6. Build subtitle rows plus `SUBTITLE_JSON` and `SUBTITLE_SRT`.
7. Build `RENDER_PREP_MANIFEST_V2` with hashes and timing authority.
8. Mark the job ready only after every required asset succeeds.

## Outputs

- Versioned segment-level `TTS_AUDIO_CLIP` assets.
- One current, full-duration `TTS_AUDIO_JOINED` WAV.
- Timing map, audio format, fit ratio and fit status metadata.
- Per-clip `speech_budget` evidence and manifest-level `duration_gate_summary`.
- `SubtitleSegment` rows and JSON/SRT subtitle assets.
- `RENDER_PREP_MANIFEST_V2` with SHA-256 and size for current assets.
- `audio_review.status = PENDING_AUDIO_REVIEW` until an operator approves the staged narration.

The manifest contains safe storage references only; it must not expose absolute local paths.

## Phase 4 handoff

Run from `apps/api`:

```powershell
python -m scripts.run_tts_v2_once <source-video-uuid>
python -m scripts.run_phase4_approval stage-audio-from-db <artifact-root> <source-video-uuid>
```

Staging copies the hash-verified narration to `phase4_joined_narration.wav` and preserves `PENDING_AUDIO_REVIEW`. After listening, the operator may approve it explicitly:

```powershell
python -m scripts.run_phase4_approval audio-from-db <artifact-root> <source-video-uuid> --operator <operator-id>
```

This writes `phase4_audio_approval.json` and changes the manifest to `AUDIO_APPROVED`. Final render is fail-closed unless that approval and the narration SHA-256 both match.

## Background audio

When audio analysis has a verified Demucs `no_vocals.wav` stem, its storage reference and SHA-256 are carried into the manifest. Phase 4 may mix it under Vietnamese narration. If no verified background stem exists, the safe strategy is narration-only; original Chinese vocals are never mixed into final output.

## OmniVoice engine catalog in Ops

`/ops/tts-ai` exposes the full upstream OmniVoice Studio engine matrix through `GET /ops/tts-ai/engines`. Each row separates three independent facts:

- whether the dependency is installed on the current API host;
- whether the engine is compatible with the current operating system;
- whether `reup-douyin` has a production synthesize adapter for Preview and durable jobs.

The UI may install only registry-owned recipes through `POST /ops/tts-ai/engines/{engine_id}/install`. A recipe may use an allowlisted pip package or a managed source checkout. Source recipes run disk/tool preflight, shallow-clone the fixed repository URL, create an isolated venv, install fixed arguments, optionally download fixed Hugging Face weights, and run an import probe. The browser cannot submit a repository URL, package name, install arguments, or shell command for this endpoint.

Engine install progress is available at `GET /ops/tts-ai/engines/install/status`. The API persists `install-state.json` after every step and writes `installed.json` only after the recipe completes. Retrying reuses a healthy checkout, venv and resumable model directory. `AUDIO_TTS_ENGINE_ROOT` controls the managed root (default `./data/tts-engines`); it must remain a data path, not a source-code path. Pip-only recipes still use the allowlisted API-environment installer because their future in-process adapters need that import.

This is deliberately not a universal GitHub installer. Every automated repository and argument must be reviewed and added to the backend registry. Engines needing a bundled binary, unsupported operating system, external API server, unautomated system dependency, or an unverified weights layout keep a setup guide instead of executing arbitrary repository instructions.

Completing an engine recipe does not make the engine selectable. Only engines with both a healthy installation and a wired synthesize adapter can be saved as `model_id`; this prevents Preview and worker jobs from accepting a configuration they cannot execute. Adding a future engine therefore requires both a reviewed install recipe and a tested provider adapter/factory route.

## Known limits

- Timing compression is deliberately limited to 15%; text or voice settings require operator correction beyond that limit.
- Spoken-unit counting is a deterministic Vietnamese heuristic, not phoneme alignment. Provider output duration remains authoritative.
- Calibration needs at least three matching provider/voice/rate clips; new voices use the default rate until enough evidence exists.
- Underfilled text is not automatically padded because invented filler can alter meaning; it is flagged for review instead.
- The current final render uses single-pass FFmpeg loudness normalization. Output QA measures the encoded result and blocks duration, loudness or clipping failures.
- Background preservation depends on a new audio-analysis run that persisted a verified no-vocals stem; older analyses remain narration-only.
- No lip-sync is provided.
- OmniVoice Studio engines other than `k2-fsa/OmniVoice` are discoverable/installable where safe, but remain unavailable to Preview/jobs until their individual adapters are implemented.

## Temporal V4 additions

- Fitted-cache and raw acoustic-cache are separate. A timeline edit can reuse expensive model inference and redo only local fitting.
- Frontend Generate defaults to cache-first. A full regeneration requires an explicit `force_refresh=true` action.
- Display text remains the subtitle authority while deterministic Vietnamese speech text expands ambiguous numbers, units and alphanumeric model names for pronunciation.
- Speech normalizer V2 also expands dates, times, negative values, numeric ranges, currency, percentages, multiplication/slash expressions, URLs, emails and complex model IDs. Operator pronunciations can be supplied in `options_json.pronunciation_glossary`; the glossary affects speech/cache/profile authority, never subtitle text.
- A calibrated duration planner increases the initial provider rate only for predicted overflow, capped at +12%; it never slows a short sentence merely to fill silence.
- Alternative translations are probed only when Translation emitted the explicit `tts_eligible` contract.
- Candidate synthesis is adaptive: approved alternatives are ranked locally, a second candidate is synthesized only after a measured miss, and voice-rate correction keeps the remote-call ceiling at three attempts per segment.
- Every clip receives a 6 ms click-safe edge fade and local waveform QA for silence, clipping, DC offset and low peak.
- Local ASR word timestamps are retained as source phrase/pause evidence. Heavy full-video lip sync remains out of scope.
- OmniVoice is warmed once in the persistent worker process and inference is serialized per model/device to avoid duplicate model loads and VRAM contention.
- `phase3_tts_performance.json` records fitted/acoustic cache hits, real provider calls, provider time, local fitting/QA time and total elapsed time. The Transcript Editor exposes the key counters.
- Switching a setup On is atomic and exclusive: it becomes active while all other setups are disabled in the same database write.
- A queued worker re-verifies the profile fingerprint before synthesis. Disabling, switching or editing the setup makes the old job fail closed with `tts_authority_changed`.
- Saved provider fallback is suppressed at the production boundary. Every clip and joined narration persist the same `tts_authority`; a provider/model/voice mismatch is rejected before cache persistence.
- Render and adaptive-final reuse validate that narration still belongs to the setup currently On. Legacy/mismatched narration must be regenerated.

## Context-aware performance direction

The TTS runtime now creates a provider-neutral performance plan before any paid
or remote synthesis call:

1. `VoiceBible` stores the reusable voice recipe (persona, accent, baseline pace,
   breathing and director rules). It is a reference recipe, never model training,
   and it does not imply that a provider remembers prior audio.
2. The local `TTS Director` maps each approved translation row to emotion,
   intensity, pace, pauses, emphasis, breath, transition, semantic weight and
   explicit previous/target `ProsodyState`. Existing Audio Analysis event
   timelines are reused when available; TTS does not decode the source audio a
   second time.
3. Prosodic-semantic chunks preserve speaker, meaning and continuity while
   retaining lossless member translation IDs. Planned states are computed ahead
   of synthesis so bounded provider batching remains possible.
4. `ProviderCapabilities` and the lowering adapter translate that plan only into
   features the active provider declares: Gemini-like endpoints may receive
   English Audio Tags, voice direction and sample context; classic Google/Azure
   endpoints may receive SSML; basic/Edge providers receive clean text and a
   degradation record. Subtitle display text is never polluted with control tags.

Director plans, performance chunks, capability matrices and per-clip lowering
metadata are persisted as secret-free `RENDER_DEBUG_JSON` artifacts. Their hashes
are included in fitted/acoustic cache keys, so a voice recipe or prosody change
invalidates only affected performance audio while preserving the existing
duration, waveform and authority gates. Unsupported expressive features are
warnings/review signals rather than silent provider switching.

Before synthesis, a deterministic Prosody QA contract verifies that each segment
starts from the previous segment's target state. A mismatch is recorded as a
review warning and in `phase4_tts_prosody_qa.json`; generated audio still remains
subject to the existing measured-duration and waveform hard gates.

### Expressive execution modes

`options_json.expressive_tts.mode` controls whether a provider may downgrade
emotion silently:

- `off` keeps neutral SSML/rate controls for compatibility;
- `best_effort` applies every capability available and records degradation;
- `required` fails before the network call when requested emotion, pause,
  emphasis or pace is not consumed by the provider request.

The provider-neutral Voice Direction carries canonical `emotion`, `emphasize`,
and `pauses: before/after …ms` fields. A connector binding `voice_direction`
therefore has deterministic proof that these controls reached its prompt even
when a neutral segment has no Audio Tags. A missing required binding raises
`expressive_feature_not_applied` as a terminal configuration error; it is not
auto-retried because an identical manifest cannot heal between attempts.
This lowering change is versioned as `tts-provider-lowering-v2`, so pre-fix
acoustic cache entries cannot masquerade as audio generated with the new prompt.

Google Cloud classic profiles are normalized to SSML by default. The effective
duration rate and local prosody pace are combined once inside `<prosody rate>`;
the Google `audioConfig.speakingRate` remains neutral, preventing double speed
application. Emotion also maps to SSML pitch/volume and clause-level breaks.

`google_gemini` is a separate expressive provider slug over the universal HTTP
transport. Its reviewed manifest must consume at least one of
`audio_tags`, `rendered_text`, `voice_direction`, `sample_context` or
`ssml_text`; requests with expressive features are forced to `required` mode.
The actual Gemini/Vertex endpoint remains configurable, while the adapter and
security boundary stay provider-neutral.

Each HTTP synthesis response carries a `tts-provider-execution-contract-v1`
record containing requested, applied and degraded features. Audio QA verifies
that the execution contract agrees with the rendered WAV; metadata alone is not
treated as evidence that emotion reached the provider.

### Gemini expressive runtime

When `google_gemini` has no custom connector manifest, the runtime supplies the
safe AI Studio-compatible defaults:

- base URL `https://generativelanguage.googleapis.com/v1beta`;
- model `gemini-2.5-flash-preview-tts` when Model ID is empty;
- API-key query authentication;
- `generateContent` with `responseModalities: ["AUDIO"]`;
- Voice Bible/Director Notes, Sample Context and tagged transcript in the prompt;
- inline Base64 audio extraction from `inlineData`.

The endpoint, model and manifest remain overrideable for Vertex or a compatible
gateway. Raw `audio/L16` responses are wrapped with their declared sample rate
before the common 48 kHz mono WAV normalization boundary.

Long tagged scripts are grouped into semantic 4-8 second provider requests,
never fixed character slices. Calls run with bounded concurrency (default two),
retain chunk IDs and are reassembled in order. A chunk above the expressive
timing target is retried once with a faster natural-delivery instruction. When
both neutral and excited/positive chunks exist, local RMS and zero-crossing
evidence can trigger one stronger-emotion retry for only the mismatching chunk.
Every underlying HTTP call and retry is included in provider cost/performance
metadata.

The same `google_gemini` profile may use a billed Vertex AI transport by
setting `credential_mode` to `google_service_account` or `google_adc` and
providing `options_json.vertex_ai.location` (default `us-central1`). The
runtime derives the project-scoped publisher endpoint from the validated
credential metadata, exchanges OAuth with the Cloud Platform scope, and uses
bearer authentication. AI Studio API-key profiles remain supported and are
not silently converted to Vertex.

Vertex Gemini may declare Google Cloud TTS as a fallback. That fallback is a
separate transport with its own Classic TTS manifest. When Vertex cannot run,
the fallback strips provider-specific Audio Tags, records
`tts_expressive_fallback_degraded`, and retains the requested expressive
features in provenance instead of claiming that Classic TTS rendered native
emotion. A profile that fails its Vertex permission/model probe should remain
Off until `aiplatform.endpoints.predict` is granted and the selected model is
available in the configured project/region.

For short-form videos that require one consistent narrator, set
`expressive_tts.single_voice_mode` to `required` and
`expressive_tts.synthesis_strategy` to `whole_video`. `TTS_TEMPORAL_V6` selects
only approved Translation Draft candidates before the paid boundary, compiles
all local Audio Tags and pauses into one video script, and calls Gemini once.
The returned WAV first receives a gentle block-level timing correction and is
then split by `whole-video-silence-alignment-v2`. V2 selects all stable pause
boundaries as one sequence, rejecting short phoneme valleys that previously
caused cumulative sentence drift. A recovered sentence may borrow only the
real empty gap before the next source segment; it never overlaps the next
utterance. If one slice still needs too much local correction, the block gets
one bounded adaptive refinement while the cached provider audio remains
unchanged. Low-confidence fallback boundaries and all borrowed milliseconds
remain visible in QA metadata. This lane still makes one provider request for
the entire admitted video.

When the configured `max_whole_video_seconds` or `max_request_chars` boundary
is exceeded, the runtime creates a small number of bounded narration blocks
(default 45 seconds) instead of reverting to one request per sentence. Each
block is cacheable before local timing work. Multi-block output is explicitly
reported as `single_voice_verified=false`; the runtime never claims global
speaker identity from several independent generations.

The legacy `segment` strategy remains available as a diagnostic fallback. It
is not the recommended production mode for Gemini because provider quota and
voice identity scale with the number of timeline segments.

### Gemini-only text-conditioned emotion planner

`emotion_planner.enabled` is scoped to the `google_gemini` profile. It batches
the Translation Draft into intent/emotion decisions, applies a neutral gate,
and records confidence, evidence and rejected signals. Punctuation alone never
creates `excited`; CTA language maps to a mild positive delivery, instructions
remain neutral, and weak/ambiguous evidence falls back to neutral. Decisions
are lowered into Gemini Audio Tags and Voice Direction only after the planner
passes its capability gate. Google Classic and every other provider explicitly
skip this planner and receive neutral prosody.
Before an asset is accepted, the runtime records a Gemini emotion acceptance
report covering policy adjustments, execution verification, single-request
voice identity, waveform validity and timing. A fitted ratio above
`expressive_tts.max_review_atempo` (default `1.10`) is retained with an explicit
translation-repair recommendation; the hard `1.15` atempo safety limit remains
fail-closed.

Default expressive options are:

```json
{
  "expressive_tts": {
    "synthesis_strategy": "whole_video",
    "single_voice_mode": "required",
    "max_whole_video_seconds": 180,
    "max_block_seconds": 45,
    "max_request_chars": 6000,
    "compact_trigger_ratio": 0.88,
    "mode": "required",
    "min_chunk_seconds": 4,
    "max_chunk_seconds": 8,
    "max_concurrency": 1,
    "max_tempo_correction": 1.08,
    "max_review_atempo": 1.10,
    "min_request_interval_seconds": 0,
    "regenerate_on_timing_mismatch": false,
    "regenerate_on_emotion_mismatch": false,
    "pcm_endianness": "little"
  }
}
```
