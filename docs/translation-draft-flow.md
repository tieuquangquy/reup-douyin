# Translation Draft Flow

The translation draft flow turns current `TranscriptSegment` rows (DialogueBeats) into Vietnamese `TranslationSegment` rows for later review, TTS, and subtitle generation.

## Biphasic contract (pilot, machine-first)

1. **Phase A — ASR only:** `ANALYZE_AUDIO` with `skip_translation=true` → Demucs vocals (when available) → FunASR → caption↔ASR consensus → **machine auto-approve** beats (`source_auto_approved` / `source_auto_approved_risk`). No auto-translate.
2. **Operator:** Review **Vietnamese** + timeline (Chinese is read-only reference). Optional advanced endpoint `POST .../transcript-draft/approve-source` remains but is not the primary CTA.
3. **Phase B — Literal translate:** `BUILD_TRANSLATION_DRAFT` (`literal_safe`) via `POST .../translation-draft/rerun`. Does **not** run FunASR. Requires beats `APPROVED` (satisfied by Phase A auto-approve).

Default Phase B CTA is `literal_safe` (faithful meaning). **Gemini (AI Studio `GEMINI_API_KEY`) is primary** unless Ops **Translation AI** overrides; MyMemory is recovery only when the LLM is down or VI still has Chinese. UI also offers **Translate natural** (`natural_viral`) for punchier spoken lines after literal quality is acceptable.

### Operator-owned Translation AI (LLM connection)

**Preferred:** Ops Console → **Translation settings** (`/ops/translation-ai`) → tab **Translation AI** → enable DB override → Save.  
Stored in DB at `workspaces.settings_json.translation_ai` (per workspace). Supports `gemini`, `openai_compatible` (third-party Chat Completions), `ollama`, and `auto`. API key is never returned in full (masked). Worker rebuilds the translation provider on each Translate job.

**Authority:** enabled workspace DB override → `.env` (`GEMINI_*` / `OLLAMA_*` / `AUDIO_TRANSLATION_PROVIDER`) → placeholder.

Phase 1 note: if the login JWT `workspace_id` is not a real `workspaces` row, settings Save falls back to `ensure_default_workspace` (same local workspace jobs/videos use) so Translate picks up the saved connection/prompt.

API: `GET/PUT /ops/translation-ai`, `POST /ops/translation-ai/test`, `POST /ops/translation-ai/models` (list models after provider credentials are filled).

### Operator-owned translation prompt

**Preferred:** Ops Console → **Translation settings** → tab **Translation prompt** (`/ops/translation-prompt`) → Save.  
Stored in DB at `workspaces.settings_json.translation_user_prompt` (per workspace). The worker loads it on each Translate and appends only the Chinese beat text. No code edit; restart not required after Save.

**Fallback (if DB empty):**

- `AUDIO_TRANSLATION_USER_PROMPT_FILE=prompts/translation_user.txt`
- or `AUDIO_TRANSLATION_USER_PROMPT=...` (inline)
- else built-in `literal_safe` / `natural_viral` templates

API: `GET/PUT /ops/translation-prompt`.

## Presets

Supported presets:

- `literal_safe`: closer to source wording, safer for uncertain STT (**Phase B default**).
- `natural_viral`: more natural spoken Vietnamese for short-video review.
- `affiliate_soft_sell`: softer phrasing for affiliate-oriented content.

The preset is stored per translation segment in `translation_preset`.

## TranslationSegment Fields

Important fields:

- `source_video_id`
- `transcript_segment_id`
- `segment_index`
- `language_code`
- `text`
- `translation_preset`
- `duration_budget_ms`
- `estimated_tts_duration_ms`
- `quality_flags_json`
- `created_by_job_id`
- `is_current`

`duration_budget_ms` comes from the source transcript timing. It gives step 9 a clear budget for TTS/subtitle fitting.

## Review Hints

Current quality flags:

- `translation_too_long_for_slot`
- `awkward_short_segment`
- `low_confidence_source`
- `provider_placeholder`
- `vi_contains_source_script` / `cjk_repair_applied` / `translation_gate_failed` (VI still had Chinese; repair or reject)
- `translation_fallback_used` (primary LLM failed; secondary used)
- `needs_operator_review` (only when risk flags above apply — not on every clean beat)

Dirty VI recovery order after Gemini/LLM draft: **MyMemory zh→vi** (`machine_translate_applied`) → chat-LLM repair → micro-chunk LLM (`cjk_chunk_retranslate_applied`). If Gemini is fully unavailable, MyMemory is used as `machine_translate_recovery`. If a beat still fails the CJK gate, that beat stays empty; clean beats still persist (`translated_literal_partial`). Job `translation_count` = filled VI only.

## Versioning

Each audio analysis rerun creates a new current set:

- Prior translations become `is_current = false`.
- New translations point to the new current transcript rows.
- JSON draft artifact is written as `TRANSLATION_DRAFT_JSON`.

Re-running **Translate literal** on the same transcript version **upserts** rows keyed by `(transcript_segment_id, language_code, version)` — it does not INSERT a second row (avoids `uq_translation_segments_transcript_language_version`).

## Step 9 Contract

TTS/subtitle generation should read:

1. Current `TranslationSegment` rows ordered by `segment_index`.
2. `duration_budget_ms` as the slot budget.
3. `quality_flags_json` to decide whether a segment needs review before synthesis.
4. `TranscriptSegment` timing for subtitle alignment.

## Phase 1 Limits

- The default translation provider is an explicit placeholder.
- No external LLM or translation model is bundled.
- No automatic style adaptation beyond preset metadata is implemented.
