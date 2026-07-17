# TTS Pipeline

The TTS pipeline converts current edited Vietnamese `TranslationSegment` rows into render-ready narration assets.

## Inputs

- Current `TranslationSegment` rows where `is_current = true`
- Linked `TranscriptSegment` timing
- Voice config from `POST /tts`

The resolver validates that translation text exists, timing is positive, and current segments do not overlap.

## Outputs

- Segment-level `TTS_AUDIO_CLIP` assets
- Joined `TTS_AUDIO_JOINED` narration asset
- `SubtitleSegment` rows
- `SUBTITLE_JSON` and `SUBTITLE_SRT` assets
- `RENDER_PREP_MANIFEST` asset

## Provider Abstraction

The core pipeline calls a `TtsProvider` interface:

- input: text, language, voice config, optional target duration
- output: audio bytes, duration, MIME type, provider metadata, warnings

Production default is resolved by `AUDIO_TTS_PROVIDER` / Ops **TTS settings**:

- `edge` → `EdgeTtsProvider` (`edge-tts` + ffmpeg). Default voice `vi-VN-HoaiMyNeural`.
- `vieneu` → `VieNeuTtsProvider` (`pip install vieneu`). Default voice `Phạm Tuyên`.
- `auto` → prefer VieNeu if installed, else edge-tts, else placeholder.
- Cloud / HTTP (`google`, `azure`, `elevenlabs`, `openai`, `openai_compatible`, `http_custom`) accept full credentials in Ops; synthesis adapters land in follow-up slices — set `fallback_provider=edge` or `vieneu` until then.
- Custom Local/SDK slugs (e.g. `my_tts_sdk`) can be saved from Ops; use **Install** (`POST /ops/tts-ai/install`) for allowlisted `pip install <pkg>` or `git+https://…` into the API Python env. Synthesis still needs a known adapter or `fallback_provider` until a generic runner exists.
- Ops ready chip (Install + Test): `unchecked` → `not_installed` / `installed` → `ready` (or `failed`). Voice & runtime presets stay editable before Ready.
- After **Install**, API auto-runs probe+catalog and persists `runtime.last_install` / `runtime.last_probe` on the workspace (survives F5). **Test** also refreshes `last_probe`.
- GET `/ops/tts-ai` returns `runtime` + `live_import_ok` (cheap import check). Ops UI hydrates Ready chip and Voice dropdown from the snapshot.
- Ops **Preview speech** (`POST /ops/tts-ai/preview`): short sample text → one synthesize → base64 audio for in-page playback (not a durable Generate TTS job).
- `placeholder` → tone WAV for tests.

Workspace authority: enable override at `/ops/tts-ai` (same pattern as Translation AI). Secrets are masked on GET.

When workspace TTS is **enabled**, Generate TTS (`POST /tts` / `SYNTHESIZE_TTS`) uses Ops `voice_id` / speaking rate / language (and provider via factory) — client defaults such as `vi-VN-HoaiMyNeural` must not override. Web `createTtsJob` sends empty `voice_id` so Ops/env resolve authority.

Operator requirements for real speech: install the chosen SDK (`edge-tts` and/or `vieneu`) via Ops **Install** or CLI, and keep ffmpeg on PATH for edge. Disable Ops install with `AUDIO_TTS_ALLOW_INSTALL=false`. Missing SDKs fail the job with an actionable `TtsPipelineError` (or use configured fallback).

## Segment Clip Strategy

Each translation segment produces one TTS clip. The pipeline stores clip metadata:

- `translation_segment_id`
- actual duration
- fit status
- fit ratio
- provider metadata
- warnings

Phase 1 fails the whole job for invalid inputs or persistence errors. It does not silently skip broken segments.

## Joined Narration Strategy

The joined narration asset concatenates generated WAV clips and stores a `timing_map`. It does not time-stretch clips. Render step should use the map and fit warnings to decide exact placement.

## Timing Fit

TTS duration is compared with the segment slot:

- `fits_well`
- `slightly_long`
- `too_long`
- `too_short`

Mismatch is recorded as warnings and subtitle review flags. Phase 1 does not auto-compress audio.

`GET /source-videos/{id}/tts-summary` exposes structured `clips[]` (`translation_segment_id`, `fit_status`, `fit_ratio`, `warnings`) and `timing_fit_summary` counts so Transcript Editor can badge beats that need shorter/longer VI or Ops rate changes.

Phase 1 VieNeu on Windows: Ops `local_backend=auto` maps to ONNX in the API wrapper (avoids PyTorch+ModelScope MOSS tokenizer failures on GPU). Use `Ngọc Linh` etc. from the VieNeu catalog; set `fallback_provider=none` unless you explicitly want edge rescue.

## Job Flow

`SYNTHESIZE_TTS` steps:

1. `validate_input`
2. `resolve_translation_segments`
3. `synthesize_segment_clips`
4. `evaluate_timing_fit`
5. `assemble_narration_track`
6. `build_subtitle_segments`
7. `export_subtitle_assets`
8. `build_render_prep_manifest`
9. `persist_outputs`
10. `finalize`

The local worker executes the real pipeline at `persist_outputs`.

## Operator handoff (web)

In Transcript Editor, after Translate saves VI text:

1. **Generate TTS** creates `POST /tts` (`SYNTHESIZE_TTS`) and polls the job.
2. On success, the bench loads `TTS_AUDIO_JOINED` via authenticated blob URL (`fetchMediaAssetObjectUrl`) into a compact `<audio controls>` player.
3. Beat rail / focus editor show timing-fit badges from `tts-summary.clips` (problems only on the rail; full status + hint on the focused beat).

## Phase 1 Limits

- Switchable providers via Ops TTS settings / env (edge + VieNeu synthesize; cloud/HTTP settings saved with fallback).
- No voice selection UI in Transcript Editor (voice via Ops/API/settings).
- No time-stretching / atempo fit loop.
- No BGM mix with Demucs stems.
- No auto-enqueue TTS after Translate.
- No lip-sync.
- No final video render.
