# Translation Draft Flow

## Translation V5 recipe

The active recipe is `translation-v3-contextual-semantic-utterance-ranking-5`. Approved
semantic utterances remain the only speech authority; raw ASR timing units, video
caption, title and hashtags are never treated as complete dialogue sentences.

Before the first provider call, `semantic-dialogue-segmentation-v1` reconstructs each
utterance from the immutable local ASR token timeline. It aligns partial text duplicated
at FunASR chunk seams, scores boundaries with pause/punctuation/speaker/discourse
evidence, vetoes incomplete clauses and lexical splits, and persists token-range lineage
plus an authority hash. A failed authority/overlap contract blocks Translation locally.

1. Build non-overlapping dialogue blocks (up to 10 beats or 30 seconds) with two
   neighboring beats on each side as read-only context.
2. Send one structured request per block with speaker labels, timeline budgets,
   glossary and non-authoritative exact translation memory. Candidate count is adaptive:
   one for clean/high-confidence spacious beats, two for moderate timing risk, and three
   for short, low-confidence or protected-token beats.
3. Calibrate the spoken-unit rate from recent TTS clips for the active provider,
   voice ID and speaking rate. Fewer than three valid samples falls back to the
   provider-neutral default, so Translation never has to synthesize a probe.
4. Run local deterministic gates and ranking: CJK removal, protected number/unit/URL
   checks, glossary consistency, speech-budget fit, naturalness and prosody. A
   provider self-score is only a tie-breaker and never replaces a hard local gate.
5. Select the best candidate. Only a selected candidate outside the 15% over-duration
   limit enters the existing controlled rewrite path.
6. Checkpoint every completed block in the durable job metadata. A retry resumes from
   the first incomplete block and does not repeat completed provider calls.
7. Persist the immutable V3 fingerprint, candidate history and a quality contract with
   `filled_count`, `review_required_count`, `blocked_count`, `complete` and `tts_ready`.
   Hard-valid alternative candidates are forwarded to Temporal TTS V3 so an actual
   duration miss can be corrected locally without translating the whole dialogue again.
8. Persist `translation_authority_v1`, binding the source transcript hash, prompt hash,
   provider/model identity, quality-contract hash and current TranslationSegment rows.
   TTS validates this manifest and fails closed when transcript or translation data changes.

The run fingerprint binds the transcript timing/text, preset, provider/model, prompt,
glossary, speech policy and recipe version. A non-forced rerun with the same fingerprint
reuses the current verified draft; a forced rerun creates a new immutable version.

Runtime hard rules always override conflicting operator style instructions. Chinese
source/context and translation memory are treated as untrusted data, candidate text fields
must be Vietnamese-only, and JSON keys/IDs remain part of the required transport schema.
The physical TTS-calibrated slot is the hard spoken-unit budget; Chinese character count is
not used as a hard Vietnamese length cap.

The compact V5 operator prompt template is versioned at
`apps/api/prompts/translation_user_v5.txt`. Workspace prompt profiles may still override
style preferences, but the runtime hard rules above are always appended and cannot be
weakened by a profile.

The translation draft flow turns current `TranscriptSegment` rows (DialogueBeats) into Vietnamese `TranslationSegment` rows for later review, TTS, and subtitle generation.

## Biphasic contract (pilot, machine-first)

1. **Phase A — ASR only:** `ANALYZE_AUDIO` with `skip_translation=true` → Demucs vocals (when available) → FunASR → caption↔ASR consensus → **machine auto-approve** beats (`source_auto_approved` / `source_auto_approved_risk`). No auto-translate.
2. **Operator:** Review **Vietnamese** + timeline (Chinese is read-only reference). Optional advanced endpoint `POST .../transcript-draft/approve-source` remains but is not the primary CTA.
3. **Phase B — Literal translate:** `BUILD_TRANSLATION_DRAFT` (`literal_safe`) via `POST .../translation-draft/rerun`. Does **not** run FunASR. Requires beats `APPROVED` (satisfied by Phase A auto-approve).

Default Phase B CTA is `literal_safe` (faithful meaning). **Gemini (AI Studio `GEMINI_API_KEY`) is primary** unless Ops **Translation AI** overrides. The production high-quality lane does not fall back to MyMemory: provider failures fail/retry the durable job, preventing mixed-provider drafts. UI also offers **Translate natural** (`natural_viral`) for punchier spoken lines after literal quality is acceptable.

### Operator-owned Translation AI (LLM connection)

**Preferred:** Ops Console → **Translation settings** (`/ops/translation-ai`) → tab **Translation AI** → enable DB override → Save.  
Stored in DB at `workspaces.settings_json.translation_ai` (per workspace). Supports `gemini`, `openai_compatible` (third-party Chat Completions), `ollama`, and `auto`. API key is never returned in full (masked). Worker rebuilds the translation provider on each Translate job.

**Authority:** enabled workspace DB override → `.env` (`GEMINI_*` / `OLLAMA_*` / `AUDIO_TRANSLATION_PROVIDER`) → placeholder. Gemini free-tier execution is sequential and uses `GEMINI_TRANSLATION_MIN_REQUEST_INTERVAL_SECONDS=13` by default; a 429 receives a minimum 60-second durable retry delay.

Phase 1 note: if the login JWT `workspace_id` is not a real `workspaces` row, settings Save falls back to `ensure_default_workspace` (same local workspace jobs/videos use) so Translate picks up the saved connection/prompt.

API: `GET/PUT /ops/translation-ai`, `POST /ops/translation-ai/test`, `POST /ops/translation-ai/models` (list models after provider credentials are filled).

### Operator-owned translation prompt

**Preferred:** Ops Console → **Translation settings** → tab **Translation prompt** (`/ops/translation-prompt`) → Save.  
Stored in DB at `workspaces.settings_json.translation_user_prompt` (per workspace). The worker loads it on each Translate and appends a mandatory runtime contract, the real Chinese beat, the slot duration, and a spoken-unit ceiling. Placeholder source text inside a saved prompt is explicitly ignored. No code edit or restart is required after Save.

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

The versioned `TRANSLATION_DRAFT_JSON` also exports each row's `status` and safe `metadata`. This is where duration-rewrite candidates and their validation evidence remain reviewable without overwriting the approved/current text history.

## Duration-aware controlled rewrite

Translation first produces the complete Vietnamese meaning. It then evaluates the line against the slot using Vietnamese spoken units, punctuation pause budget, and a provider-neutral default rate. This estimate is an early review signal only; synthesized audio remains the final authority.

Only an oversized line enters controlled rewrite, for at most two attempts in the production provider factory. Every candidate records its text and SHA-256, speech-budget result, missing protected tokens, a deterministic semantic-retention screening score, and whether it is safe to present for operator review. Numbers, URLs, acronyms and common units are protected against accidental deletion. A safe candidate is selected as a review candidate and receives `needs_operator_review`; it is never silently approved.

If no safe candidate exists, the original translation is retained with `duration_adaptation_required` and `duration_rewrite_no_safe_candidate`. Underfilled lines are also retained rather than padded with invented speech. Candidate history is stored under `metadata.duration_adaptation` with schema `duration_adaptation_v1`.

The semantic-retention score is a deterministic screening heuristic, not a semantic equivalence proof. Operator review remains mandatory for a selected rewrite candidate and for low-retention warnings.

## Review Hints

Current quality flags:

- `translation_too_long_for_slot`
- `awkward_short_segment`
- `low_confidence_source`
- `provider_placeholder`
- `vi_contains_source_script` / `cjk_repair_applied` / `translation_gate_failed` (VI still had Chinese; repair or reject)
- `translation_fallback_used` (primary LLM failed; secondary used)
- `needs_operator_review` (only when risk flags above apply — not on every clean beat)

Dirty VI recovery in the production high-quality lane uses chat-LLM repair followed by micro-chunk LLM (`cjk_chunk_retranslate_applied`). MyMemory recovery remains available only to explicit legacy/manual provider instances; the default factory disables it. If a beat still fails the CJK gate, that beat stays empty; clean beats still persist (`translated_literal_partial`). Job `translation_count` = filled VI only.

Additional duration-review flags include `duration_rewrite_applied`, `duration_rewrite_no_safe_candidate`, `duration_rewrite_protected_token_mismatch`, `duration_rewrite_semantic_review_required`, and `duration_underfilled_review`.

## Versioning

Each audio analysis rerun creates a new current set:

- Prior translations become `is_current = false`.
- New translations point to the new current transcript rows.
- JSON draft artifact is written as `TRANSLATION_DRAFT_JSON`.

Translation history is immutable across jobs. A new Translate job inserts `max(version) + 1` for each `(transcript_segment_id, language_code)` and leaves prior rows non-current. Only an idempotent retry carrying the same `created_by_job_id` may update that job's own row. This satisfies `uq_translation_segments_transcript_language_version` while preventing a new run from overwriting a previously approved translation.

## Step 9 Contract

TTS/subtitle generation should read:

1. Current `TranslationSegment` rows ordered by `segment_index`.
2. `duration_budget_ms` as the slot budget.
3. `quality_flags_json` to decide whether a segment needs review before synthesis.
4. `metadata.speech_budget` and `metadata.duration_adaptation` as review evidence, never as approval authority.
5. `TranscriptSegment` timing for subtitle alignment.
6. `translation_authority` as the hash-bound transcript/translation handoff contract.

Before TTS, risky or unapproved rows park the Reup Queue at `translation_review`. The frontend approval endpoint hash-binds the reviewed Vietnamese text and timing; only then may the recipe-owned OmniVoice TTS job resume. `timing_fit_blocked` is terminal and is never retried as a transient provider error.

## Phase 1 Limits

- The default translation provider is an explicit placeholder.
- No external LLM or translation model is bundled.
- Candidate semantic fidelity is constrained by the configured translation provider;
  local ranking can prove structural/timing safety but is not a bilingual semantic proof.
- Glossary input currently comes from `source_videos.metadata_json.translation_glossary`;
  a dedicated operator glossary UI remains future work.
