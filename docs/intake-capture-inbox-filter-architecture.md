# Intake ↔ Capture Inbox Filter Architecture

## Problem
Current flow accepts filter inputs from multiple entry routes, but Capture Inbox lacks a persisted, explicit per-item intake evaluation lifecycle. This makes match/fail visibility and deterministic re-evaluation weak.

## Required Architecture

### 1) Responsibility boundaries
- **Extension (`apps/extension-douyin-capture`)**
  - Capture current page videos and metadata.
  - Perform identity/context checks only.
  - Do **not** decide intake quality match/fail.
- **API Capture Inbox (`apps/api`)**
  - Stage raw captured items.
  - Enrich canonical metadata.
  - Evaluate intake filters in backend service.
  - Persist evaluation result per captured item.
- **Web (`apps/web`)**
  - Render persisted evaluation results.
  - Allow operator to trigger re-evaluation.
  - Must not be source-of-truth for filtering decisions.

### 2) Lifecycle
1. Capture from extension/current-page endpoint.
2. Stage into Capture Inbox with hard-gates only (context mismatch, dedupe, malformed payload, etc.).
3. Enrich item metadata.
4. Evaluate intake filter config in backend.
5. Persist `matched`/`failed`/`error` (and reasons).
6. Show grouped status in Capture Inbox.
7. Optional promote downstream.

### 3) Domain model (new)
Add capture-inbox intake evaluation fields on captured item model/response:
- `intake_evaluation_status`: `not_evaluated | matched | failed | error`
- `matches_intake`: `bool | null`
- `intake_failed_rules_json`: `list[str]`
- `intake_missing_requirements_json`: `list[str]`
- `intake_filter_version`: `str | null`
- `intake_preset_name`: `str | null`
- `last_intake_evaluated_at`: `datetime | null`
- `intake_evaluation_error`: `str | null`

These fields are independent from existing [`CapturedItem.status`](apps/web/src/types/capture-inbox.ts:46), which remains operational state (ready/duplicate/promoted/etc.).

### 4) Evaluation source of truth
Evaluation config resolution must be deterministic and backend-owned:
- Resolve from preset + overrides using existing preset utilities (same rule family as intake).
- Stamp resolved version/name onto item (`intake_filter_version`, `intake_preset_name`).
- Re-run should overwrite evaluation fields, not mutate raw payload.

### 5) Re-evaluation triggers
- Automatic:
  - after staging/enrich completes
  - after [`retry_enrich`](apps/api/src/services/capture_inbox_service.py:503)
- Manual:
  - new action `re_evaluate_intake` on [`/capture-inbox/sessions/{id}/actions`](apps/api/src/api/routes/capture_inbox.py:103)
  - supports selected item IDs or whole session
- Config change:
  - operator supplies new preset/action context -> reevaluate selected/all

### 6) API contract changes
- Extend [`CaptureInboxActionRequest`](apps/api/src/schemas/capture_inbox.py:159) action literal with `re_evaluate_intake`.
- Extend [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24) with intake evaluation fields.
- Ensure list/session endpoints expose these fields consistently.

### 7) UI behavior
Capture Inbox should support:
- status chips: Matched / Failed / Not evaluated / Error
- filtering/grouping by intake evaluation state
- optional details panel section showing failed rules + missing requirements + evaluation timestamp/version

### 8) Observability
Add structured logs for:
- evaluation start/end per session and action trigger
- evaluated item count, matched count, failed count, error count
- filter version/preset identifiers
- do not log secrets/raw sensitive payloads

## Migration Notes
- Add nullable columns first.
- Backfill old rows as `not_evaluated` and `matches_intake = null`.
- Keep backward-compatible API defaults where possible.

## Risks and Mitigations
- **Risk:** UI interprets operational status as intake match.
  - **Mitigation:** Keep separate fields + explicit labels.
- **Risk:** inconsistent filter resolution across routes.
  - **Mitigation:** centralize evaluator config resolution in Capture Inbox service helper.
- **Risk:** stale evaluation after enrichment.
  - **Mitigation:** reevaluate on enrichment retry and timestamp every run.
