# Douyin Factor 5 — Intake Wiring Log

## Scope Lock
- Implement **only Factor 5**: intake evaluation wiring between `/intake` and Capture Inbox.
- Backend remains source of truth for intake evaluation.
- Frontend only displays evaluation state/grouping/filtering and triggers re-evaluation.
- Do not move filtering logic into extension.
- Do not delete raw captured items as part of intake filtering.
- No broad product redesign or unrelated refactors.

## Ordered Plan (User-Mandated)
1. Audit `/intake` + Capture Inbox + backend wiring.
2. Docs first (`log` / `resume` / `architecture`).
3. Finalize 4-state status model.
4. Backend evaluation service updates.
5. Post-stage/post-enrich wiring.
6. Deterministic persistence of intake evaluation fields.
7. API/re-evaluate route alignment.
8. Narrow frontend wiring.
9. Focused tests.
10. Verification.
11. Final docs update.

## Audit Findings (Current)

### Existing backend wiring (already present)
- `apps/api/src/services/capture_inbox_service.py`
  - `stage_extension_capture(...)` already calls intake evaluation flow.
  - `retry_enrich(...)` already calls intake evaluation flow.
  - `re_evaluate_intake(...)` action exists for explicit operator-triggered re-check.
  - `_evaluate_items_against_intake(...)` already resolves filter config and calls candidate filter logic.
- `apps/api/src/api/routes/capture_inbox.py`
  - `POST /capture-inbox/sessions/{capture_session_id}/actions` supports `re_evaluate_intake`.
- `apps/api/src/models/capture_inbox.py`
  - `CapturedItem` already contains intake evaluation persistence columns.

### Existing model/contract shape
- `apps/api/src/enums/__init__.py`
  - `IntakeEvaluationStatus` now aligned to migration-compatible values: `NOT_EVALUATED`, `MATCHED`, `FILTERED_OUT`, `MISSING_REQUIREMENTS`, `EVALUATION_ERROR`.
- `apps/web/src/types/capture-inbox.ts`
  - Frontend union mirrors current enum values.
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - Current UI filtering/summary is tied to current enum semantics.

### Gap versus required Factor-5 semantics
Required semantic buckets:
1. `hard_rejected`
2. `needs_enrichment`
3. `filtered_out`
4. `matched`

Current persisted status does not directly expose these semantics in a stable four-state model, so mapping/alignment is required while preserving existing API safety and migration compatibility.

## Target Persistence Fields (must be consistently set)
- `intake_evaluation_status`
- `matches_intake`
- `intake_failed_rules_json`
- `intake_missing_requirements_json`
- `intake_filter_version`
- `intake_preset_name`
- `last_intake_evaluated_at`
- `intake_evaluation_error`

## Progress
- [x] Read `AGENTS.md` and repo constraints.
- [x] Completed audit pass across intake/capture-inbox backend+frontend surfaces.
- [x] Docs-first kickoff started.
- [x] Finalize semantic status mapping + naming.
- [x] Implement backend changes.
- [x] Implement frontend narrow wiring.
- [x] Verification run (web typecheck passed; API pytest blocked by missing `pytest`).
- [x] Add focused tests updates for Factor-5 semantics.

## Final Changed Files (Factor 5)
- `apps/api/src/enums/__init__.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-factor5-intake-wiring-log.md`
- `docs/douyin-factor5-intake-wiring-architecture.md`
- `docs/douyin-factor5-intake-wiring-resume.md`

## Verification Evidence
- `npm --workspace @reup-douyin/web run typecheck` ✅ passed
- `npx tsx apps/web/src/test/capture-inbox.test.ts` ✅ passed
- `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py -k intake` ⛔ environment missing `pytest` module

## Non-goals
- No crawler changes.
- No extension filtering redesign.
- No queue or worker architecture changes.
- No broad UI redesign.
