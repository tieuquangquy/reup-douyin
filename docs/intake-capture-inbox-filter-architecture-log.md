# Intake ↔ Capture Inbox Filter Architecture Log

## Date
- 2026-04-29 (Asia/Bangkok)

## Scope
Define and document the correct filtering architecture between [`/intake`](apps/api/src/api/routes/intake.py) and [`Capture Inbox`](apps/api/src/api/routes/capture_inbox.py), with **backend-owned** intake filter evaluation and **raw staged capture preservation**.

## Audit Summary

### Confirmed current behavior
- Extension/API request paths currently accept `preset_name` + `filter_config` conversion helpers in:
  - [`_to_filter_config()`](apps/api/src/api/routes/intake.py:46)
  - [`_to_filter_config()`](apps/api/src/api/routes/douyin_extension.py:32)
  - [`_to_current_page_filter_config()`](apps/api/src/api/routes/douyin_accounts.py:69)
- Capture staging and enrichment are handled in [`CaptureInboxService`](apps/api/src/services/capture_inbox_service.py:150).
- Candidate filtering for promotion/intake runs currently uses [`CandidateEvaluationService.apply()`](apps/api/src/services/candidate_service.py:49).
- Capture Inbox action contract currently does **not** include an intake re-evaluation action in [`CaptureInboxActionRequest`](apps/api/src/schemas/capture_inbox.py:159).
- `CapturedItem` API/web types currently do **not** expose explicit intake evaluation fields:
  - [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24)
  - [`CapturedItem`](apps/web/src/types/capture-inbox.ts:41)

### Gaps vs required target behavior
- No persisted per-item intake evaluation status/version/timestamp.
- No first-class backend re-evaluation path for selected/all inbox items.
- No UI grouping/filtering bound to persisted intake match/fail state.
- Filter processing is still conflated with capture-time request payload in extension/current-page routes.

## Decision Summary
1. Keep extension capture focused on collection + context + hard-gates only.
2. Move intake quality filter evaluation to backend Capture Inbox service layer after staging/enrich.
3. Persist evaluation result on each captured item (status + reasons + version metadata).
4. Add explicit re-evaluate action in Capture Inbox actions API.
5. Keep promotion path independent from staging evaluation visibility (promotion may still run with selected preset, but inbox must show persisted intake eval state).

## Non-goals
- No crawler/video processing rewrite.
- No queue/distributed execution changes.
- No extension-side quality filter enforcement.

## Implementation Update (2026-04-29)

### Completed backend wiring
- Added post-stage intake evaluation and post-retry-enrich re-evaluation in [`CaptureInboxService`](apps/api/src/services/capture_inbox_service.py:160).
- Added explicit re-evaluation service path for selected/all items in [`re_evaluate_intake()`](apps/api/src/services/capture_inbox_service.py:544).
- Added evaluator helper that persists status/reasons/version/error fields in [`_evaluate_items_against_intake()`](apps/api/src/services/capture_inbox_service.py:961).
- Expanded runtime schema guard to require intake evaluation columns in [`validate_runtime_schema()`](apps/api/src/services/capture_inbox_service.py:422).

### Completed API contract updates
- Added `re_evaluate_intake` action support in [`CaptureInboxActionRequest`](apps/api/src/schemas/capture_inbox.py:167).
- Wired action handler in [`run_capture_inbox_action()`](apps/api/src/api/routes/capture_inbox.py:103).

### Completed web updates
- Extended intake-aware Capture Inbox filtering/actions in [`CaptureInboxPage`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:840):
  - `needs-action` includes not evaluated/error intake states.
  - `failed` includes intake failed state.
  - item action adds `Re-evaluate intake`.
  - summary includes intake matched/needs-review/failed counters for recommendation logic.

### Verification executed
- Passed: `npm run typecheck --workspace apps/web`
- Passed: `npx tsx src/test/capture-inbox.test.ts && npx tsx src/test/capture-inbox-canonical.test.ts`

## Next Ordered Steps
1. Confirm whether `/intake` saved preset binding requires additional behavior beyond current [`applySavedPreset()`](apps/web/src/components/intake/IntakePage.tsx:365).
2. Add/adjust focused tests for intake eval lifecycle in backend service/routes.
3. Finalize architecture docs/resume status to fully-complete.
