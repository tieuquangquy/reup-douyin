# Audio Analysis Pipeline

The audio analysis pipeline turns downloaded source media into reviewable transcript and Vietnamese translation drafts. It starts from the media layer created in step 7 and writes canonical DB rows plus JSON artifacts back into storage.

## Inputs

The pipeline resolves current assets in this order:

1. `SOURCE_AUDIO_EXTRACT`
2. `SOURCE_VIDEO_RAW`

If neither exists, analysis fails with `missing_source_asset`. The resolver checks storage existence through the storage backend; it does not build local paths directly.

## Outputs

Canonical app data:

- `TranscriptSegment`
- `TranslationSegment`

Storage artifacts:

- `AUDIO_ANALYSIS_METADATA`
- `TRANSCRIPT_JSON`
- `TRANSLATION_DRAFT_JSON`

Future providers may also write:

- `SOURCE_AUDIO_EXTRACT`
- `AUDIO_VOCAL_STEM`
- `AUDIO_BACKGROUND_STEM`

## Layers

- `AudioAssetResolver` loads the current input asset from the media layer.
- `SourceSeparationProvider` separates vocal/background when available.
- `SttProvider` returns normalized transcription units with timing and confidence.
- `TranscriptBuilder` creates clean transcript segments and difficulty flags.
- `TranslationProvider` creates Vietnamese draft text.
- `TranslationDraftBuilder` adds duration budgets and review hints.
- `AudioAnalysisService` persists DB rows, JSON assets, manifest state, and job output.

## Default Providers (localization free stack)

See also `docs/localization-reup-pipeline-design.md`.

- **VAD:** `SileroVadProvider` runs Silero waveform inference when the `silero-vad` package is installed (`pip install silero-vad`; model weights ship with the wheel, no runtime download) and records measured `speech_seconds` / `speech_ratio` / `speech_segment_count` plus the `silero_vad_executed` flag. Speech shorter than `min_speech_seconds` (0.8s) does not open a dubbing lane (`speech_below_threshold`). Falls back to `HeuristicVadProvider` with `silero_unavailable` / `silero_failed` when the package is missing or inference raises. Result is persisted as `has_speech` on `SourceVideo.metadata_json` and in `AUDIO_ANALYSIS_METADATA`. When `has_speech` is false, STT/translation/separation are skipped (`skip_dubbing`).
- **Source separation:** `DemucsSourceSeparationProvider` runs Demucs two-stem vocals when `demucs` is importable (`python -m demucs --two-stems=vocals`), caches `{stem}_vocals.wav`, and points STT at that key. Falls back with `demucs_unavailable` / `demucs_failed` when import or execution fails (never `demucs_not_executed`).
- **Caption↔ASR consensus (ASR-first):** After STT with spoken units, `apply_caption_asr_consensus` only flags `caption_agreed` / `caption_asr_conflict` / `source_unverified`. **Caption never replaces DialogueBeat text** (Douyin title/hashtag is metadata/OCR later). Punctuation-only units (`!`) are dropped. Empty ASR never invents beats from caption.
- **STT:** `FunasrSttProvider` (Paraformer-zh when `funasr` installed). `sentence_info`
  remains the first timing authority. When Paraformer omits sentences but returns a
  word-level `timestamp` array, the adapter now creates DialogueBeats at measured
  pauses (700 ms) with an 8-second safety bound; it no longer stretches the whole
  utterance into one full-video slot. This preserves the real gaps used by joined TTS
  and prevents narration from playing only at the beginning of the video. A genuinely
  untimed blob still stays one DialogueBeat and is `duration_fit` into the media window
  for explicit operator splitting. If STT is unavailable/timeout/empty → **no
  DialogueBeats** (Douyin title/hashtag caption is not speech). Outcome depends on VAD
  evidence: measured speech plus empty ASR becomes `dialogue_uncertain`; without a
  measurement it remains `no_dialogue` + `skip_dubbing`.
- **Translation:** `DurationConstrainedTranslationProvider` — primary from Ops **Translation AI** DB override when enabled, else **Gemini** (`GEMINI_API_KEY`, `GEMINI_TRANSLATION_MODEL`) / Ollama / OpenAI-compatible. The production high-quality lane is fail-closed: an LLM/provider failure never silently injects MyMemory into the draft. Gemini free-tier calls are sequential and paced by `GEMINI_TRANSLATION_MIN_REQUEST_INTERVAL_SECONDS` (default 13 seconds); HTTP 429 retries wait at least 60 seconds. Job `translation_count` = filled VI only.

### Reup Queue wiring

`MARK_MEDIA_READY` enqueues `ANALYZE_AUDIO` (`idempotency_key=reup-queue:{item_id}:analyze-audio`) and moves the item to `WAITING_FOR_METADATA`.

## Job Integration

`ANALYZE_AUDIO` uses these steps:

1. `validate_input`
2. `resolve_assets`
3. `extract_audio_if_needed`
4. `separate_sources`
5. `transcribe`
6. `build_transcript_segments`
7. `build_translation_draft`
8. `persist_outputs`
9. `finalize`

The current worker executes the real pipeline at `persist_outputs`; earlier steps remain orchestration checkpoints until specialized handlers are added.

## Rerun Strategy

Phase 1 keeps history and marks the latest run current:

- Existing transcript and translation rows are set `is_current = false`.
- New rows get the next numeric `version`.
- `analysis_version` uses `AUDIO_ANALYSIS_V1_RUN_N`.
- JSON artifacts use media asset versioning and `is_current`.

Editors should only load `is_current = true` rows by default.

## Error Codes

- `missing_source_asset`
- `audio_extract_failed`
- `source_separation_failed`
- `transcription_failed`
- `transcript_build_failed`
- `translation_failed`
- `translation_review_required` (durable queue checkpoint before TTS, not a provider failure)
- `persistence_failed`

## Phase 1 Limits

- No real audio extraction is bundled yet.
- No vocal/background model is bundled yet.
- No real STT or translation model is bundled yet.
- No transcript editor, TTS, subtitle generation, OCR, or render flow is included in this step.
