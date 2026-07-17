# Phase 21D-14 Scan/Collect Status Separation Log

## Summary

Phase 21D-14 tightened Douyin Scanner workflow separation so scan, classification, and collection are represented by distinct canonical workflow states instead of leaking through legacy top-level or harvest-only status fields.

The scanner now avoids false `Collecting` UI during Scan Profile, stale running locks no longer incorrectly promote pause/collect actions, paused/resume readiness aligns to canonical collection workflow state, and reset/diagnostic expectations are validated against the separated workflow model.

## Scope

Touched extension-only scanner workflow files:

- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`

Validated against existing controller/readiness behavior in:

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`

Non-goals preserved:

- No backend contract changes.
- No database or queue implementation changes.
- No crawler or video-processing work.
- No popup redesign.
- No new runtime dependencies.
- No V2/legacy workflow promotion.

## Implementation Notes

### Canonical workflow assertions

Updated Phase 21D-14 tests to assert against canonical workflow state instead of legacy shortcuts.

The scanner workflow is now validated through explicit expectations for:

- `workflow.scan.status`
- `workflow.classification.status`
- `workflow.collection.status`
- `workflow.active_task`
- `workflow.action_lock`

This covers successful Scan Profile completion, failed Scan Profile attempts, paused collection, resumed collection, reset clearing, and classification failure handling.

### Scan Profile semantics

`Scan Profile` is now validated as a scan-plus-classification workflow, not a collection workflow.

Tests now assert that after a successful scan:

- scan workflow finishes as success,
- classification workflow finishes as success,
- collection workflow stays idle,
- action lock and active task are cleared,
- the queue is built for future collecting,
- diagnostic action state records the completed action code.

The persisted diagnostic action code is validated as:

```text
scan_profile.success
```

Failed Scan Profile tests were also aligned to controller behavior so canonical scan workflow state ends in `failed` rather than pretending the scan workflow stayed idle.

### Pause/resume and busy gating

Readiness coverage was updated so pause/resume visibility and stop availability follow canonical collection workflow status.

Tests now explicitly model:

- paused collection with `workflow.collection.status = "paused"`
- running collection with `workflow.collection.status = "running"`

This prevents stale top-level `status` or legacy `harvest.status` assumptions from being the only source of truth for scanner controls.

### View-model stale lock protection

The scanner view-model test file was repaired and kept aligned with stale-lock expectations.

Coverage preserves the rule that a stale legacy `harvest.status: "running"` record must not force scanner UI into `Collecting` or `pause` when canonical scanner busy logic considers that state stale.

### Reset and failure alignment

Reset coverage continues to require that scanner reset preserves calibration but clears canonical scan/classification/collection workflow state and lock/task fields.

Failure-path coverage now matches the real controller behavior in [`failState()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2243), including scan failure state and diagnostic completion values.

## Validation

Commands run after the final test edits:

```text
npm --workspace @reup-douyin/extension-douyin-capture run test
```

This workspace test script also completed:

```text
npm run build
node dist/distModuleResolution.test.js
```

Result: passed.
