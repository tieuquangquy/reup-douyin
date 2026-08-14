# Semantic Hard-sub Cue Authority

## Purpose

The OCR detector is geometry evidence, not dialogue meaning. Phase 2 therefore
must not translate every raw OCR string as an independent caption. The semantic
cue layer reconstructs stable display cues locally from OCR observations and the
current ASR token timeline.

This layer makes no OCR, translation, or cloud-model call. The existing
translation provider remains upstream in `Build Translation Draft`.

## Frontend runtime flow

The durable frontend `ANALYZE_OCR` job executes:

```text
OCR-V27.1 observations and geometry
  -> local temporal ASR/OCR alignment
  -> source/editor provenance routing
  -> transition-noise attachment
  -> fuzzy temporal cue canonicalization
  -> approved dialogue translation reuse
  -> monotonic Vietnamese display-cue planner
  -> Phase 2 review/handoff
```

Before every Phase-2 invocation, including approval retries and residual
remediation resumes, `QualityLocalizationService` writes
`semantic_dialogue_authority.json` from current `TranscriptSegment` and
`TranslationSegment` rows. The artifact is bound to the immutable Phase-1 SHA,
the ASR token authority and exact translation version/status/text.

## Authority rules

- OCR owns observed glyph evidence and geometry.
- ASR word timestamps own dialogue text and timing.
- Only an `APPROVED` Vietnamese `TranslationSegment` owns dialogue render text.
- `DIALOGUE_HARDSUB` never enters Caption AI as fragmented OCR text.
- `EDITOR_LABEL` follows normal exact OCR/operator review and Phase-3 translation.
- `SOURCE_INTRINSIC` and platform UI preserve source pixels.
- Missing provenance becomes `UNCERTAIN`; it never defaults to editor text.
- Short transition corruption is either attached to a stable neighboring cue's
  geometry or emitted as cover-only, never translated.

## Content and render behavior

Rows with the same semantic `cue_id` become one Phase-2 content object even when
their OCR spellings differ. The content object carries every geometry reference,
so concealment covers all temporal/geometry occurrences while the Vietnamese
cue renders once.

When one approved dialogue translation spans multiple visual cue epochs, the
planner divides Vietnamese words monotonically using aligned ASR-token weights.
It does not duplicate or discard words. A missing/unapproved translation creates
`semantic_dialogue_pending`, blocks the Phase-2 handoff explicitly, and sends
zero dialogue fragments to Caption AI.

## Versioned artifacts

- Semantic recipe: `semantic-hardsub-cue-authority-v1`
- Semantic schema: `semantic_hardsub_cues_v1`
- Phase-2 contract: `phase2_ocr_timeline_v3_semantic_cues`
- Phase-2 handoff: `phase2_handoff_v2_semantic_cues`
- Review hash: `phase2_review_input_v2_semantic_cues`
- DB bridge: `semantic_dialogue_authority.json`

Raw OCR evidence, `master_timeline.json`, and Phase-1 coverage artifacts remain
unchanged. Semantic authority and its hashes are carried into Phase-2 review,
preview payloads, metadata and the Phase-3 handoff.

## Fail-closed conditions

Phase 2 blocks or preserves pixels when:

- the semantic dialogue artifact does not match the current Phase-1 SHA;
- its self-hash is invalid;
- dialogue translation is not `APPROVED`;
- provenance cannot be proven as dialogue/editor content;
- geometry cannot be mapped exactly once into the handoff.

## Test coverage

Focused tests cover transition junk such as `AL立TT`, platform UI such as
`1天前·山东`, fuzzy duplicate canonicalization, OCR typo recovery from ASR,
monotonic Vietnamese cue allocation, fail-closed unapproved translations,
missing provenance and semantic-authority review-hash invalidation.
