# Phase 21D-13 Scanner Action Handler Workflow Fix Resume

## Status

Phase 21D-13 scanner action handler fixes have been implemented and fully validated.

## Completed

- Added canonical scanner readiness via `getDouyinScannerWorkflowReadiness(state)`.
- Routed calibrated/no-scan scanner state to `Scan Profile`.
- Added scanner action diagnostics:
  - `last_action_clicked`
  - `last_action_result`
  - `last_action_error`
- Added `runScanProfileWorkflow(runtime)` for one-click Scan Profile behavior.
- Preserved scan failure diagnostics and mapped profile-tab failures to:

```text
Open a Douyin profile page first.
```

- Added `runStartCollectingWorkflow(runtime, options)` with explicit blocked-state messages:

```text
Scan Profile first.
No videos are queued for collection.
Calibrate 4 Points first.
Collector runner is not connected yet.
```

- Ensured Start Collecting blocked preflight does not mark idle scanner state as globally failed.
- Added `resetScannerWorkflowState(runtime)` scanner reset entry point preserving calibration.
- Wired popup scanner actions to the new controller workflows.
- Forced detector reconnect in popup scanner content-script readiness to support one-click Scan Profile recovery.
- Confirmed the main calibration action still calls the real calibration handler.
- Added Phase 21D-13 coverage to `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`.
- Updated scanner readiness and view-model coverage for canonical `Start Collecting`, legacy Run-tab `Extract Next 10`, classified empty queues, and stale legacy running locks.

## Validation Already Run

From `apps/extension-douyin-capture`:

```text
npx tsx src/wholeProfileHarvest.viewModel.test.ts
npx tsx src/wholeProfileHarvest.readiness.test.ts
npx tsx src/wholeProfileHarvest.test.ts
```

Result: passed.

From the repository root:

```text
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

Result: passed.

## Remaining Recommended Validation

None for Phase 21D-13. The requested extension test, typecheck, and build commands passed after the final edits.

## Important Files

- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase21D-13-action-handler-workflow-fix-log.md`

## Notes

The implementation keeps existing backend contracts and existing scan/classification/collection orchestration boundaries. It does not add crawler, backend DB, queue, or popup redesign work.
