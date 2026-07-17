# Phase 18I-A Three-Layer Harvest State + UI Log

## Scope

Phase 18I-A defines the canonical 3-layer Whole Profile Harvest design and guard behavior only.

Included in scope:

- Canonical schema/version bump for Whole Profile Harvest state.
- 3-layer readiness model (`profile_scan` -> `dry_run` -> `harvest`).
- Durable options contract for Mode / Batch / Speed / unattended safe mode.
- Queue preview and target-status summary in canonical state.
- Run Harvest guard behavior that blocks real harvesting in this phase.
- Popup Mode / Batch / Speed controls persisted into canonical options.
- Progress summary updates for the new state shape.
- Test updates to align with guard-first behavior.

Out of scope:

- Real harvest execution loop.
- Capture session creation.
- Backend flush.
- Modal navigation/extraction loop.
- Legacy/V2/CDP/smart/full-modal integrations.

## Design Summary

### 1) Canonical schema version

Whole Profile state schema is now:

- `phase18i_a_three_layer_harvest_design`

### 2) Three-layer readiness model

Canonical state tracks layer gates:

- `layer.profile_scan_ready`
- `layer.dry_run_ready`
- `layer.harvest_ready`

These are used for explicit operator flow and for Run Harvest guard enforcement.

### 3) Harvest options contract

Canonical options live in:

- `harvest_options.mode`
- `harvest_options.batch`
- `harvest_options.speed`
- `harvest_options.unattended_safe_mode`

This decouples UI controls from execution internals and keeps Phase 18I-A focused on state+contract.

### 4) Queue preview + target status summary

State now includes:

- `harvest.queue_preview` (preview only, no execution)
- `harvest.planned_total`
- `target_status` summary by capture status bucket

### 5) Run Harvest guard behavior

`runHarvest` is guarded in Phase 18I-A and does **not** execute canonical harvesting.

Guard outcomes are explicit:

- recommends dry-run first when needed (`dry_run_recommended`)
- returns phase-disabled guard when execution is not enabled (`harvest_not_enabled_in_phase18i_a`)

No session creation, no backend flush, no modal-loop side effects.

## Progress Summary Updates

Progress renderer now reflects the 18I-A shape:

- Layer readiness fields.
- Harvest options fields (mode/batch/speed/unattended).
- Queue preview rows.
- Expanded target-status summary buckets.

## Popup Controls

The popup exposes canonical Whole Profile Harvest controls for:

- mode: `new_and_incomplete`, `new_only`, `refresh_all`
- batch: `next_5`, `next_10`, `next_20`, `all_remaining`
- speed: `safe`, `normal`, `fast`
- unattended safe mode toggle

Changing controls writes through the canonical `updateHarvestOptions` path and refreshes queue preview/progress state. Run Harvest still remains guard-only for Phase 18I-A.

## Files Updated in this pass

- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts`

## Validation Status (current workspace run)

Executed successfully:

```cmd
npm --prefix apps/extension-douyin-capture run typecheck
npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts
npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts
npm --prefix apps/extension-douyin-capture run build
```

Result: pass.

## Notes

This phase intentionally preserves a strict separation between configuration/state/UX contracts and real harvesting execution. It keeps local-first behavior deterministic while maintaining SaaS-ready boundaries for future worker/queue execution phases.
