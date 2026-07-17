# Phase 18I-A Three-Layer Harvest State + UI Resume

## What this phase delivers

Phase 18I-A delivers the canonical state and UI contract foundation for Whole Profile Harvest without enabling real harvest execution.

Delivered:

- Schema version migration to `phase18i_a_three_layer_harvest_design`.
- Explicit 3-layer readiness gates.
- Canonical harvest options contract (mode/batch/speed/unattended safe mode).
- Popup Mode / Batch / Speed controls wired into canonical harvest options.
- Queue preview and target-status summaries in state.
- Run Harvest hard guard (no session/backend/modal execution in this phase).
- Progress summary alignment with the new state shape.
- Test alignment for schema and guard behavior.

## Operational intent

Operator flow in this phase is:

1. Verify profile and collect canonical target detail contracts.
2. Run dry-run sample and persist dry-run state.
3. Run Harvest remains guard-only to prevent premature execution paths.

## Key behavior constraints

- No real harvesting side effects are allowed.
- No canonical capture session create calls are allowed from Run Harvest.
- No backend flush calls are allowed from Run Harvest.
- No modal traversal loop is allowed from Run Harvest.

## Changed artifacts

- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts`
- `docs/metadata-phase18I-A-three-layer-harvest-state-ui-log.md`
- `docs/metadata-phase18I-A-three-layer-harvest-state-ui-resume.md`

## Validation commands

```cmd
npm --prefix apps/extension-douyin-capture run typecheck
npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts
npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts
npm --prefix apps/extension-douyin-capture run build
```

Status in this session: passing.

## Follow-up phase expectations

Next implementation block should keep Run Harvest guard-only until the execution phase is explicitly authorized, then replace the Phase 18I-A guard with a durable execution loop that preserves the existing state/options contracts.
