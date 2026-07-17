# Douyin Factor 5 — Intake Wiring Architecture

## Objective
Provide deterministic backend-owned intake evaluation wiring between `/intake` and Capture Inbox, while preserving raw captured data and exposing operator-usable state in the UI.

## Boundaries
- `apps/api` owns intake evaluation computation and persistence.
- `apps/web` owns display/filter/grouping and explicit re-evaluation trigger UX.
- `apps/extension-douyin-capture` remains capture-only and does not perform intake filtering decisions.

## End-to-End Flow (Target)
1. Capture enters Capture Inbox via stage flow.
2. Backend evaluates each selected item against active intake config/preset.
3. Backend persists intake evaluation fields on each item.
4. API returns persisted evaluation fields in capture inbox responses.
5. Frontend groups/filters badges based on persisted status semantics.
6. Operator can trigger re-evaluation action; backend recomputes and persists deterministically.
7. Post-enrich path re-evaluates when new metadata may affect filter outcomes.

## Four-State Semantic Model
Canonical semantic statuses for Capture Inbox intake evaluation:
- `HARD_REJECTED` — item is permanently non-actionable by policy/context mismatch or explicit terminal exclusion logic.
- `NEEDS_ENRICHMENT` — item cannot be confidently evaluated yet because required metadata is missing.
- `FILTERED_OUT` — item is fully evaluated and does not pass intake thresholds/rules.
- `MATCHED` — item is fully evaluated and passes intake thresholds/rules.

### Compatibility Mapping Strategy
Current enum (`NOT_EVALUATED`, `MATCHED`, `FAILED`, `ERROR`) will be mapped/refined so API/web can represent the required four semantics without breaking existing rows:
- `MATCHED` -> `MATCHED`
- `FAILED` -> either `FILTERED_OUT` or `HARD_REJECTED` based on failure reason classification
- `NOT_EVALUATED` -> `NEEDS_ENRICHMENT` when missing required signals; otherwise preserved only as transient internal state
- `ERROR` -> `HARD_REJECTED` when deterministic hard failure, else explicit error surface with retryable semantics (final implementation documents exact branch)

> Implementation may introduce explicit enum values for the four states, with backward-safe mapping for historical rows.

## Deterministic Persistence Rules
Each evaluation pass must atomically set:
- `intake_evaluation_status`
- `matches_intake`
- `intake_failed_rules_json`
- `intake_missing_requirements_json`
- `intake_filter_version`
- `intake_preset_name`
- `last_intake_evaluated_at`
- `intake_evaluation_error`

Rules:
- Never clear raw capture payload fields.
- Missing-signal determination must be deterministic and reproducible from the same inputs.
- Error text must be concise and safe for operator surfaces.
- Old/null rows must be safely interpreted and re-evaluable.

## Trigger Points
- Post-stage capture completion.
- Post-enrich completion (`retry_enrich` / enrich refresh).
- Explicit operator action: `re_evaluate_intake`.
- Optional preset-change-driven re-evaluation entry point (narrow, no broad orchestration redesign).

## API/Frontend Contract Expectations
- API exposes persisted intake evaluation fields in `CapturedItemResponse`.
- Frontend type union aligns with backend status values.
- Capture Inbox UI summary/filter chips derive from persisted status only (not recomputation in UI).

## Test Strategy (Focused)
Backend tests:
- status mapping for matched/filtered-out/needs-enrichment/hard-rejected.
- deterministic persistence field writes.
- post-stage + post-enrich + explicit action triggers.

Frontend tests:
- status label/tone/filter grouping for four-state model.
- re-evaluate action wiring remains intact.

## Non-goals
- No extension-side intake policy logic.
- No deletion/rewrite of raw captured records.
- No broad intake product redesign.
