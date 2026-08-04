# Phase 3 visual-text translation contract

Phase 3 localizes OCR-approved visual text from Chinese to Vietnamese. It does not
translate dialogue audio, synthesize speech, render video, or publish/export.

## Authority and boundary

- Sole input authority: `phase2_handoff.json` with status `READY_FOR_PHASE3`.
- Phase 3 references the SHA-256 of that file and never overwrites
  `master_timeline.json` or `phase2_ocr_timeline.json`.
- Caption AI settings come from the workspace database through the existing
  Caption AI resolver. Environment settings remain only the resolver's existing
  fallback.
- Numeric values and units are protected before translation. `勺` renders as
  `muỗng`. A missing, added, or changed protected token fails closed.
- Every `content_id` is translated once. Phase 3 does not use approximate or
  near-duplicate matching. One content object may still cover multiple geometry
  references supplied by Phase 2.

## Execution

From `apps/api`:

```powershell
python -m scripts.run_phase3_only <phase2-output-directory>
```

After the operator explicitly locks every displayed candidate, record that
decision and close the phase with:

```powershell
python -m scripts.run_phase3_only <phase2-output-directory> `
  --lock-current-candidates --reviewer operator
```

The lock aborts if candidate text, review hash, content IDs, or the Phase 2
authority changed. It is not an automatic translation approval path.

The runner submits all non-deterministic content objects in one Caption AI batch
with `temperature=0`. It accepts the repository's flat keyed response schema and
the legacy workspace-prompt list schema, but the returned ID set must match the
requested `content_id` set exactly.

Translation memory is keyed by role, protected translation input, model, and
prompt. Re-running the same authority is therefore idempotent at the provider
boundary. Existing operator approvals are preserved; an approval file that
references another Phase 2 hash is rejected.

For a fresh Phase-2 authority derived from a regression rerun, prior locked
Vietnamese wording may be suggested only when `zh_approved` matches exactly and
the reference approval has `APPROVE`/`EDIT`, reviewer identity, and review
timestamp:

```powershell
python -m scripts.build_phase3_reference_edits `
  <new-phase3-root> <previous-reviewed-phase3-root>

python -m scripts.build_phase3_review_proposal `
  <new-phase3-root> <phase3_reference_edits.json>
```

The reference edits and resulting proposal are suggestion artifacts, not
approval authority. New Chinese content stays on the current provider candidate
and remains operator-reviewable. The proposal validator also rejects any edit
that adds, removes, or changes protected numeric/unit tokens.

## Artifacts and states

- `phase3_translation_timeline.json`: complete Phase 3 contract and candidates.
- `phase3_review_queue.json`: only objects requiring operator review.
- `phase3_reference_edits.json`: exact-Chinese reviewed wording suggestions;
  never approval authority.
- `phase3_review_proposal.json` / `.md`: self-hashed language-review proposal;
  does not write an operator decision.
- `phase3_approvals.json`: operator-editable decisions and approved text.
- `PHASE3_TRANSLATION_REVIEW_REPORT.md`: Chinese → Vietnamese comparison table.
- `phase3_render_handoff_preview.json`: blocked/ready diagnostic preview.
- `phase3_render_handoff.json`: created only when every required translation is
  approved; a stale final handoff is quarantined.
- `qa/phase3_translation_raw.json`: provider response fossil.
- `qa/phase3_translation_stats.json`: model-free lifecycle counts and status.
- `qa/phase3_translation_memory.json`: idempotent translation memory.
- `phase3_closeout.json`: immutable Phase 1→2→3 hash chain, created only after
  all translation candidates are explicitly approved.

Normal first-run state is `NEEDS_TRANSLATION_REVIEW`. Deterministic number/unit
rows are approved by rule; AI translations are never auto-approved. Render stays
blocked until all candidate rows pass explicit operator review. Operator edits
may improve wording but cannot change protected numeric values or units.

## Verification

Default tests mock the provider and cover response schemas, exact ID matching,
protected-token restoration, invalid operator edits, stale authority, review
artifacts, and the no-auto-render gate. They do not call live or paid services.
