# Intake ↔ Capture Inbox Filter Architecture Resume

## Objective
Implement strict backend-owned intake filter evaluation for Capture Inbox while preserving raw staged captures.

## Status Snapshot
- Audit: ✅ complete
- Docs-first package: ✅ complete
- Backend intake evaluation + re-evaluate action: ✅ complete
- Capture Inbox intake-aware filtering/actions: ✅ complete
- `/intake` saved preset binding review: ⏳ pending confirmation
- Focused backend intake-eval tests: ⏳ pending

## Architecture Direction (locked)
- Extension capture **must not** apply intake quality filter decisions.
- Capture Inbox must store raw captured items first.
- Backend evaluates intake filters after stage/enrich and stores result per item.
- Re-evaluation must be supported for:
  - preset changes
  - enrichment updates
  - manual operator trigger

## Planned data contract additions
For each captured item, add persisted fields for:
- evaluation state (`not_evaluated` | `matched` | `failed` | `error`)
- `matches_intake` boolean
- failed rule list / missing requirement list
- `intake_filter_version`
- `intake_preset_name`
- `last_intake_evaluated_at`

## Planned API additions
- Extend [`CaptureInboxActionRequest.action`](apps/api/src/schemas/capture_inbox.py:160) with `re_evaluate_intake`.
- Extend [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24) to expose intake evaluation fields.
- Wire action handling in [`run_capture_inbox_action()`](apps/api/src/api/routes/capture_inbox.py:104).

## Planned service wiring
- Add evaluation entrypoint in [`CaptureInboxService`](apps/api/src/services/capture_inbox_service.py:150).
- Trigger evaluation:
  1. after successful stage/enrich
  2. after retry enrich action
  3. on explicit re-evaluate action

## UI impact
- Extend [`CapturedItem`](apps/web/src/types/capture-inbox.ts:41) with intake evaluation fields.
- Add Capture Inbox filters/grouping for matched/failed/not-evaluated.
- Keep `/intake` preset persistence as the source of filter config intent.

## Verification executed
- ✅ `npm run typecheck --workspace apps/web`
- ✅ `npx tsx src/test/capture-inbox.test.ts && npx tsx src/test/capture-inbox-canonical.test.ts`

## Remaining verification plan
- API unit tests for intake evaluation lifecycle + persistence expectations.
- Route contract tests for `re_evaluate_intake` action behavior and payloads.
- Optional web source-contract additions for intake status wording if tightened UX copy is introduced.
