# Audio Analysis Pipeline

The audio analysis pipeline turns downloaded source media into a reviewable Chinese transcript authority. Translation is a separate `BUILD_TRANSLATION_DRAFT` job. The local V5 recipe is content-addressed, resumable and keeps the source audio/background provenance needed by TTS. V5 uses high-recall ASR candidates, selective verification and a global dialogue quality decoder so audio-event models cannot silently erase speech or promote music hallucinations into dialogue.

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

The V5 recipe also writes/registers:

- `SOURCE_AUDIO_EXTRACT`
- `AUDIO_VOCAL_STEM`
- `AUDIO_BACKGROUND_STEM`
- Target Speech Authority embedded in `AUDIO_ANALYSIS_METADATA` and hash-referenced by `TRANSCRIPT_JSON` (target, ambiguous and rejected intervals plus evidence)
- compact target-speech WAV metadata (only accepted intervals are sent to ASR)
- ASR mix/stem consensus diagnostics and a source-hash-bound preserved-background policy

## Layers

- `AudioAssetResolver` loads the current input asset and resolves its SHA-256.
- `ensure_canonical_audio` decodes a raw video once to a 44.1 kHz stereo PCM WAV (`SOURCE_AUDIO_EXTRACT`). Its lineage checksum, PCM16/stereo/sample-rate and duration are validated before reuse. Demucs and full-quality ASR keep using this source authority.
- `materialize_analysis_audio` creates one content-addressed 16 kHz mono PCM intermediate (`.cache/audio-analysis/...`) for Silero and Target Speech DSP/YAMNet. The intermediate is keyed by source checksum and recipe, so repeated resampling/ffmpeg work is avoided while the canonical stereo source remains unchanged.
- `SileroVadProvider` supplies measured speech intervals, then `TargetSpeechAuthority` combines DSP features with the pinned local YAMNet ONNX AudioSet model. The authority labels each window as dialogue, speech+music ambiguous, singing/rap, music, reaction/SFX, silence or uncertain.
- The service uses a high-recall interval ASR path: Silero speech intervals are packed into a compact WAV even when YAMNet/DSP evidence is ambiguous. FunASR runs once on the primary source (separated vocal when available), timestamps are remapped to the original video timeline, and only uncertain spans receive a second local verification pass. If the authority is unavailable on local storage, the service still fails closed and creates no DialogueBeats.
- `SourceSeparationProvider` is invoked for mixed/ambiguous intervals and by one adaptive retry when primary ASR quality or the cheap mix probe is weak. The retry is bounded to one Demucs execution and the vocal stem is classified again; original singing evidence can veto a false dialogue result.
- `SttProvider` returns normalized transcription units with timing and confidence. When both mix and stem are available, a deterministic consensus selects the stronger result and marks strong disagreement for operator review.
- Preserved background is the original audio outside target intervals, plus Demucs no-vocals only inside target intervals. This keeps music, SFX, ambience and non-target vocals in the final mix without reintroducing source dialogue into dubbed intervals.
- `DialogueValidationAuthority` applies a local semi-Markov temporal decoder and token evidence fusion. Isolated short tokens in music are dropped; clean short replies remain valid. Review spans are persisted in `dialogue_quality_contract` and cannot be machine-approved or translated automatically.
- `SemanticDialogueSegmentation` stitches partial chunk overlap, keeps the measured token timeline as authority, and derives complete translation-ready utterances with a deterministic global boundary optimizer.
- `TranscriptBuilder` persists those semantic utterances and difficulty flags.
- `TranslationProvider` creates Vietnamese draft text.
- `TranslationDraftBuilder` adds duration budgets and review hints.
- `AudioAnalysisService` persists DB rows, JSON assets, manifest state, and job output.

## Default Providers (localization free stack)

See also `docs/localization-reup-pipeline-design.md`.

- **VAD:** `SileroVadProvider` runs Silero waveform inference when the `silero-vad` package is installed (`pip install silero-vad`; model weights ship with the wheel, no runtime download) and records measured `speech_seconds` / `speech_ratio` / `speech_segment_count` plus the `silero_vad_executed` flag. Speech shorter than `min_speech_seconds` (0.8s) does not open a dubbing lane (`speech_below_threshold`). Falls back to `HeuristicVadProvider` with `silero_unavailable` / `silero_failed` when the package is missing or inference raises. Result is persisted as `has_speech` on `SourceVideo.metadata_json` and in `AUDIO_ANALYSIS_METADATA`. When `has_speech` is false, STT/translation/separation are skipped (`skip_dubbing`).
- **Source separation:** `DemucsSourceSeparationProvider` runs Demucs two-stem vocals only when the adaptive quality gate asks for it, caches both vocal/background keys, and the service registers both as checksum-bound `MediaAsset` rows. It falls back with `demucs_unavailable` / `demucs_failed` when import or execution fails.
- **Target Speech Authority (V5):** `local_dsp_silero_yamnet` is evidence, not a destructive ASR gate. YAMNet is a pinned ONNX model with SHA-256 verification; runtime network access is not required or used. A missing/corrupt model or classifier exception is `UNAVAILABLE`, which is fail-closed (`dialogue_uncertain`, `needs_operator_review`). A single singing-like window cannot reject a complete Silero speech interval. Compact ASR units crossing discontinuous source intervals are split by FunASR word timestamps before remapping; untimed fallback preserves all text and is marked for review.
- **Caption↔ASR consensus (ASR-first):** After STT with spoken units, `apply_caption_asr_consensus` only flags `caption_agreed` / `caption_asr_conflict` / `source_unverified`. **Caption never replaces DialogueBeat text** (Douyin title/hashtag is metadata/OCR later). Punctuation-only units (`!`) are dropped. Empty ASR never invents beats from caption.
- **STT:** `FunasrSttProvider` (Paraformer-zh when `funasr` installed). The model is held in a long-lived, killable local worker process; timeout terminates that process instead of abandoning a thread. Media longer than `AUDIO_FUNASR_CHUNK_SECONDS` (default 60s) is split with 1.5s overlap, stitched by timed suffix/prefix alignment, and checkpointed under local storage `.cache/funasr`. `sentence_info`
  remains the first timing authority. When Paraformer omits sentences but returns a
  word-level `timestamp` array, the adapter creates timing units at measured pauses
  with a 15-second payload safety bound. That bound is not translation authority:
  `semantic-dialogue-segmentation-v1` reconstructs utterances globally using punctuation,
  pause, speaker, discourse and incomplete-clause evidence. This preserves the real gaps used by joined TTS
  and prevents narration from playing only at the beginning of the video. A genuinely
  untimed blob still stays one DialogueBeat and is `duration_fit` into the media window
  for explicit operator splitting. If STT is unavailable/timeout/empty → **no
  DialogueBeats** (Douyin title/hashtag caption is not speech). Outcome depends on VAD
  evidence: measured speech plus empty ASR becomes `dialogue_uncertain`; without a
  measurement it remains `no_dialogue` + `skip_dubbing`.
- **Translation:** `translation-v3-contextual-semantic-utterance-ranking-5` consumes the semantic utterance authority, then uses contextual dialogue blocks, adaptive 1/2/3-candidate generation, timing-band-first local ranking, selective semantic review, hard gates, block checkpoints and content-addressed cache. Runtime prompt rules treat source/context as untrusted data and make JSON/schema constraints non-overridable. The calibrated physical slot—not Chinese character count—is the hard Vietnamese speech budget. `translation_authority_v1` hash-binds transcript, prompt, provider/model, quality contract and TranslationSegment rows for TTS. Legacy temporal pre-merge remains compatibility-only and cannot mutate a hash-bound semantic utterance. `DurationConstrainedTranslationProvider` remains the provider boundary — primary from Ops **Translation AI** DB override when enabled, else **Gemini** (`GEMINI_API_KEY`, `GEMINI_TRANSLATION_MODEL`) / Ollama / OpenAI-compatible. The production high-quality lane is fail-closed: an LLM/provider failure never silently injects MyMemory into the draft. Gemini free-tier calls are sequential and paced by `GEMINI_TRANSLATION_MIN_REQUEST_INTERVAL_SECONDS` (default 13 seconds); HTTP 429 retries wait at least 60 seconds. Job `translation_count` = filled VI only; `translation_quality_contract` is the completeness/TTS-readiness authority.

### Reup Queue wiring

`MARK_MEDIA_READY` enqueues `ANALYZE_AUDIO` (`idempotency_key=reup-queue:{item_id}:analyze-audio`) and moves the item to `WAITING_FOR_METADATA`.

## Job Integration

`ANALYZE_AUDIO` retains these durable UI steps for compatibility:

1. `validate_input`
2. `resolve_assets`
3. `extract_audio_if_needed`
4. `separate_sources`
5. `transcribe`
6. `build_transcript_segments`
7. `build_translation_draft`
8. `persist_outputs`
9. `finalize`

The worker executes the V3 service from `persist_outputs`, while heartbeats expose the real subphases (`resolve`, `audio_extract_ready`, `vad_done`, `separation_started`, `funasr_chunk|n|total`, `temporal_validation`, `semantic_dialogue_segmented`, `persist_outputs`). New jobs use `progress_authority=audio_subphase`, so placeholder step completion cannot make the UI jump to 77% before ASR starts. Legacy jobs continue to report their previous step-weighted progress.

## Cache and idempotency

- Fingerprints include source SHA, recipe version, Target Speech/YAMNet provider and model hashes, Demucs policy and chunk settings.
- A valid current metadata artifact plus the fingerprint returns an `audio_analysis_cache_hit` without VAD/Demucs/FunASR. Cache validation now requires current metadata and transcript JSON assets, matching analysis version/fingerprint, transcript row count and the hash-bound authority manifest; a translated run also requires its translation JSON node. `force_refresh=true` creates a new immutable run.
- Analysis intermediate cache hits are probed as real PCM16/16 kHz/mono WAV files; corrupt cache files are regenerated. The regenerable `.cache/audio-analysis` namespace is bounded by `AUDIO_ANALYSIS_CACHE_MAX_BYTES` and `AUDIO_ANALYSIS_CACHE_MIN_AGE_HOURS` (defaults: 5 GB and 24 hours).
- Build Translation Draft rechecks the current transcript hash against `audio_analysis_authority`. Transcript edits therefore cannot silently translate stale authority; explicit operator approval rebinds the manifest to the edited transcript.
- API and Reup Queue use a source-level single-flight guard. A queued/running/retryable Analyze Audio job is returned instead of creating a duplicate GPU job.
- ASR timestamps are passed through a local temporal gate that clamps only out-of-window beats and flags overlap/outside-authority intervals; it does not globally rescale otherwise-correct beats. Compact-audio offsets are remapped before this validation.
- Job output and `SourceVideo.metadata_json.audio_analysis_metrics` expose `resolve_ms`, `canonical_extract_ms`, `vad_ms`, `mix_quality_ms`, direct/retry ASR time, separation time, persistence time, total time and cache/adaptive reasons.

## Offline quality benchmark

`apps/api/scripts/benchmark_audio_analysis.py` scores a hand-labelled local JSON manifest with CER/WER, timing IoU, false-dialogue rate and missed-dialogue rate. Optional `--max-cer`, `--max-wer`, `--min-timing-iou`, `--max-false-dialogue-rate` and `--max-missed-dialogue-rate` flags turn the report into a CI gate. It is deliberately separate from runtime authority and has no Douyin, cloud ASR or paid-provider dependency. Use it to compare recipe/model changes on a fixed corpus before changing thresholds.

Start from `docs/audio-analysis-benchmark-manifest.example.json`, replace both example rows with labelled real clips, then run the script from `apps/api`. The example only verifies the report contract; it is not evidence of production accuracy.

## Rerun Strategy

Phase 1 keeps history and marks the latest run current:

- Existing transcript and translation rows are set `is_current = false`.
- A successful new ASR persistence also supersedes current subtitle rows and
  Translation/TTS media assets (joined clips, segment clips, subtitle exports,
  render-prep manifests and temporal debug artifacts). Files and rows are not
  deleted; they remain audit history.
- Source-level Translation/TTS counters, cache fingerprints, approval and
  readiness projections are cleared in the same transaction and an abbreviated
  invalidation event records the old/new analysis versions. If persistence
  fails, the transaction rolls back so the previous authority remains valid.
- New rows get the next numeric `version`.
- `analysis_version` uses `AUDIO_ANALYSIS_V5_RUN_N`.
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

## Local-first limits

- Silero, YAMNet, Demucs and FunASR remain local dependencies; missing Target Speech/YAMNet authority fails closed. Non-local storage adapters retain a compatibility boundary for tests/adapters. Production local PCM uses high-recall candidate ASR followed by dialogue validation, never caption/title text as speech.
- Translation still belongs to the separate LLM-backed translation job; no cloud provider is used by Analyze Audio itself.
