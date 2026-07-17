# Phase 15B Log — Extracted Item Commit Watchdog

## Scope
- Phase 15B extension-only hardening in [`apps/extension-douyin-capture/src/modalHarvest.ts`](apps/extension-douyin-capture/src/modalHarvest.ts), [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts), and [`apps/extension-douyin-capture/src/popupProgress.ts`](apps/extension-douyin-capture/src/popupProgress.ts).
- Objective: avoid “running forever” behavior when metrics are extracted but not durably committed.

## Implemented Changes
1. Added item-stage and commit diagnostics in [`FullModalHarvestProgress`](apps/extension-douyin-capture/src/types.ts:759):
   - `item_stage`
   - `phase_elapsed_ms`
   - `extracted_not_committed_ms`
   - `last_commit_result`
   - `repair_extracted_not_committed_count`
2. Expanded per-target status domain in [`FullModalHarvestTargetStatusValue`](apps/extension-douyin-capture/src/types.ts:742) with `extracting` and `extracted`.
3. Introduced staged commit path in [`commitExtractedTargetMetrics()`](apps/extension-douyin-capture/src/modalHarvest.ts:1062) and migrated direct queue mutation in [`start()`](apps/extension-douyin-capture/src/modalHarvest.ts:535) to that atomic helper.
4. Replaced several direct phase assignments with [`setPhase()`](apps/extension-douyin-capture/src/modalHarvest.ts:999) to keep phase timing and stage updates consistent.
5. Added stage-aware copy in [`phaseView()`](apps/extension-douyin-capture/src/popupProgress.ts:172) for extracting/committing transitions.

## Validation
- Typecheck passed via `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`.
- Targeted tests passed:
  - [`modalHarvest.test.ts`](apps/extension-douyin-capture/src/modalHarvest.test.ts)
  - [`popupProgress.test.ts`](apps/extension-douyin-capture/src/popupProgress.test.ts)
  - [`harvestRuntimeV2.test.ts`](apps/extension-douyin-capture/src/harvestRuntimeV2.test.ts)

## Known Status
- Workspace-wide [`npm test`](apps/extension-douyin-capture/package.json:5) remains blocked by an existing assertion in [`popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts) expecting legacy `/Maintenance/` text.
- Phase 15B runtime mapping in [`runtimeV2ToProgress()`](apps/extension-douyin-capture/src/harvestRuntimeV2.ts:367) still needs final alignment pass for the newly added diagnostics fields.
