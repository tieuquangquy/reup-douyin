# Phase 22C-2E Legacy Code Cleanup Resume

## What changed

- Production popup collection is restricted to canonical runner targets.
- Stored forbidden legacy runner targets are removed during state read/migration.
- Legacy whole-profile runner is blocked outside Node test/dev execution.
- Visible advanced legacy dry-run buttons were removed from popup markup.

## Allowed runners

- `runBatchCollectNext3SafeMode`
- `wholeProfileHarvest/controller.runBatchCollectNext3SafeMode`
- `runOneItemCollectAndSave`
- `wholeProfileHarvest/controller.runOneItemCollectAndSave`

## Forbidden runners

- `runRealModalExtractionHarvest`
- `wholeProfileHarvest/controller.runRealModalExtractionHarvest`
- legacy modal harvest aliases
- legacy flush-only runner aliases

## Diagnostics

- `forbidden_runner_target_detected`
- `forbidden_runner_target`
- `forbidden_runner_blocked_at`
- `allowed_runner_target`
- `runner_cleanup_version = 22C-2E`
- `legacy_state_migration_ran`
- `legacy_keys_removed`
- `legacy_keys_quarantined`
- `forbidden_runner_removed_from_state`

## Validation

Run:

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

Backend was not touched in this phase.
