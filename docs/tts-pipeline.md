# TTS Pipeline V2

The TTS pipeline converts the current, operator-locked Vietnamese translation into timeline-aligned narration and subtitle assets. It is local-first, but provider, storage and job boundaries remain replaceable for a future SaaS runtime.

## Input authority

- Current `TranslationSegment` rows (`is_current = true`).
- Linked source timing from `TranscriptSegment`.
- Source video duration.
- Active Ops TTS profile, including provider, voice and speaking rate.

The service rejects missing text, invalid timing, overlapping segments and segments outside the source-video timeline. A SHA-256 of the resolved translation input is stored in the render-prep manifest.

## Provider boundary

The core pipeline calls a `TtsProvider` interface. A provider receives text, language, voice configuration and an optional duration target, and returns audio bytes plus duration, MIME type, metadata and warnings.

Provider selection comes from the active Ops TTS profile, with environment configuration as fallback. Real local providers include Edge TTS, VieNeu and OmniVoice. `placeholder` is test-only and must not become production render authority.

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
- calibrates by provider, voice ID and speaking rate from matching prior clips after at least three valid samples;
- uses a median rate and ignores implausible samples outside 2-9 units per second.

Each clip persists the estimate, calibration source, observed duration, observed speech duration, observed units per second, actual timing ratio and `timing_quality_band` under `speech_budget`. Punctuation pause is subtracted from observed total duration when learning the rate so future estimates do not double-count pauses.

The assembler places each clip at its exact `start_ms` on a full-duration silent timeline. It rejects overlap, spill and out-of-range placement. The joined WAV therefore has the same duration as the source video and no downstream renderer needs to reconstruct timing from concatenated clips.

## Durable execution and idempotency

The stable idempotency key covers source video ID, translation input hash and voice configuration. An identical rerun reuses the existing result; `force_refresh=true` intentionally creates a new current version.

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
