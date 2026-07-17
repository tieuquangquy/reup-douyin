# Phase 17V Isolated Staged Harvest V2 Log

## Scope

Phase 17V adds `Whole Profile Staged Harvest V2` for finalized Capture Inbox writes from the verified modal whole-profile queue.

## Root cause addressed

The previous staged production path reused legacy Smart Capture / Harvest runtime surfaces: Smart Capture state, old capture-session preflight, Safe Harvest runner start, old progress rendering, and content-script pending flush queues. Those shared surfaces could pause, stop, clear, or overwrite the new whole-profile run before finalized backend rows appeared in Capture Inbox.

## Implementation

- Added isolated production state key: `douyinWholeProfileStagedHarvestV2`.
- Added schema version: `phase17v_whole_profile_staged_harvest_v2`.
- Added separate popup action: `Run Staged Harvest V2`.
- Added `Limit first N writes` with default `first 3` and options `first 1`, `first 3`, `first 5`, `all`.
- V2 reads only `douyinModalWholeProfileTestRun.verified_targets` and `verified_target_details`.
- V2 requires verified queue and right-rail calibration before writing.
- V2 opens each target by direct modal URL, waits for exact modal id, then reuses calibrated modal probe extraction.
- V2 builds one finalized backend payload per target and posts it directly to `/douyin-extension/full-modal-harvest`.
- V2 uses `commit_policy: finalized_only` and accepted evidence version `phase11a_production_stabilized_calibrated_harvest`.
- V2 marks a target `updated` only after backend success.
- V2 fails the run on backend schema rejection and pauses on retryable/network backend flush failures.

## Legacy isolation

V2 does not call the legacy Smart Capture / Safe Harvest runner, old capture-current-page endpoint, capture session preflight, old pending flush queue, or old harvest progress renderer. Legacy start/resume/retry controls are blocked while V2 is running.

## Files changed

- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `docs/metadata-phase17V-isolated-staged-harvest-v2-log.md`
- `docs/metadata-phase17V-isolated-staged-harvest-v2-resume.md`
- `docs/metadata-phase17V-operator-guide.md`

## Verification plan

Run extension tests, extension typecheck, extension build, and the existing API capture metadata tests because the backend endpoint contract is reused but not changed.
