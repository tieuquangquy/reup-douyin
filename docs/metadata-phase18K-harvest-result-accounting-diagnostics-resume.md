# Phase 18K Harvest Result Accounting Diagnostics Resume

## Current Scope

Only canonical Whole Profile Run Harvest result accounting and diagnostics were changed. Scanner, dry-run, backend, legacy V2, Smart Harvest, and CDP paths are intentionally out of scope.

## Implementation Summary

- Added structured harvest final status rules so all-failed batches are failed, not completed with warnings.
- Added structured `last_error` objects for harvest batch failures.
- Added per-target diagnostic fields to `harvest.results`.
- Added `harvest.failure_summary` aggregation.
- Added compact progress rows and top failure display.
- Kept Copy Debug JSON as full state copy, now including queue/results/failure summary.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase18K-harvest-result-accounting-diagnostics-log.md`
- `docs/metadata-phase18K-harvest-result-accounting-diagnostics-resume.md`

## Validation Commands

Run before handoff:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Steps

1. Rebuild and reload the extension.
2. Open a Douyin profile and run Verify Profile.
3. Confirm dry-run behavior is unchanged.
4. Run canonical Run Harvest with batch limit 10.
5. For an all-failed batch, confirm top-level `status=failed`, `phase=failed`, `harvest.status=failed`, and `last_error.code=harvest_all_targets_failed`.
6. Confirm progress shows `Top failure` and compact failed target rows.
7. Copy Debug JSON and confirm `state.harvest.queue`, `state.harvest.results`, `state.harvest.failure_summary`, `state.debug.last_request_summary`, `state.debug.last_response_summary`, and `state.last_error` are present.
