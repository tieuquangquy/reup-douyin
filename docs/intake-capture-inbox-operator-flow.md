# Intake ↔ Capture Inbox Operator Flow

## Goal
Provide deterministic operator flow where Capture Inbox reflects backend-evaluated intake suitability without losing raw captured items.

## End-to-end flow
1. Operator captures current Douyin page.
2. System stages all valid raw captures into Capture Inbox.
3. System enriches metadata (duration/posted/views/etc.).
4. Backend evaluates intake filters and stores result on each item.
5. Capture Inbox shows grouped buckets:
   - Matched intake
   - Failed intake
   - Not evaluated
   - Evaluation error
6. Operator can:
   - inspect fail reasons
   - change preset context
   - re-evaluate selected/all
   - promote selected items

## Action semantics

### Re-evaluate intake
- Action name: `re_evaluate_intake`
- Scope:
  - selected items when `item_ids` provided
  - all session items when omitted
- Expected outputs:
  - updated item evaluation fields
  - updated summary counts for matched/failed/error/not-evaluated

### Retry enrich
- Existing action remains operational.
- After successful enrich retry, intake evaluation should auto-refresh for affected items.

### Promote now
- Promotion remains explicit operator action.
- Intake evaluation informs selection UX but does not delete/hide raw items.

## Operator UX principles
- Never silently drop failed items; show them with reasons.
- Keep hard-gate failures distinct from intake-quality failures.
- Make re-evaluation timestamp/version visible for trust and debugging.

## Failure handling
- If evaluation fails for an item, set status `error` with `intake_evaluation_error`.
- Keep item selectable for retries/re-evaluation.
- Log diagnostics with stable IDs (`capture_session_id`, `captured_item_id`).
