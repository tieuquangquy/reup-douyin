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

- **VAD:** `SileroVadProvider` (falls back to `HeuristicVadProvider` when torch/Silero unavailable). Result is persisted as `has_speech` on `SourceVideo.metadata_json` and in `AUDIO_ANALYSIS_METADATA`. When `has_speech` is false, STT/translation/separation are skipped (`skip_dubbing`).
- **Source separation:** `DemucsSourceSeparationProvider` runs Demucs two-stem vocals when `demucs` is importable (`python -m demucs --two-stems=vocals`), caches `{stem}_vocals.wav`, and points STT at that key. Falls back with `demucs_unavailable` / `demucs_failed` when import or execution fails (never `demucs_not_executed`).
- **Caption↔ASR consensus (ASR-first):** After STT with spoken units, `apply_caption_asr_consensus` only flags `caption_agreed` / `caption_asr_conflict` / `source_unverified`. **Caption never replaces DialogueBeat text** (Douyin title/hashtag is metadata/OCR later). Punctuation-only units (`!`) are dropped. Empty ASR never invents beats from caption.
- **STT:** `FunasrSttProvider` (Paraformer-zh when `funasr` installed). If unavailable/timeout/empty → **no DialogueBeats** (Douyin title/hashtag caption is not speech). `dialogue_phase=no_dialogue` + `skip_dubbing`. Untimed FunASR blobs stay **one DialogueBeat** then `duration_fit` into the media window (no automatic `sentence_split`; operator may Split in Transcript Editor).
- **Translation:** `DurationConstrainedTranslationProvider` — primary from Ops **Translation AI** DB override when enabled, else **Gemini** (`GEMINI_API_KEY`, `GEMINI_TRANSLATION_MODEL`) / Ollama / OpenAI-compatible; MyMemory zh→vi only for LLM-down / CJK recovery. Job `translation_count` = filled VI only.

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
- `persistence_failed`

## Phase 1 Limits

- No real audio extraction is bundled yet.
- No vocal/background model is bundled yet.
- No real STT or translation model is bundled yet.
- No transcript editor, TTS, subtitle generation, OCR, or render flow is included in this step.
