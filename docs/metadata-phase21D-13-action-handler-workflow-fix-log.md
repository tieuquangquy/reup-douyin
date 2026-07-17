# Phase 21D-13 Scanner Action Handler Workflow Fix Log

## Summary

Phase 21D-13 fixed the Douyin Scanner action path so scanner controls are driven by one canonical readiness selector and explicit controller workflows.

The diagnostic state with an idle profile page, preserved calibration, no session, and no profile scan now routes the scanner main action to `Scan Profile`, not `Calibrate 4 Points` or `Start Collecting`.

## Scope

Touched extension-only scanner workflow files:

- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

Non-goals preserved:

- No backend contract changes.
- No database or queue implementation changes.
- No popup UI redesign.
- No fake collection success.
- No legacy/V2 scanner route promotion.

## Implementation Notes

### Canonical readiness

Added canonical scanner readiness through `getDouyinScannerWorkflowReadiness(state)`. It returns calibration, profile scan, classification, queue, busy, pause, reset, and next-action fields used by scanner action gating.

Next-action priority is now:

1. collecting -> `pause`
2. paused -> `resume`
3. profile scan missing -> `scan_profile`
4. profile scan ready but classification missing -> `scan_profile`
5. queue ready but calibration missing -> `calibrate`
6. queue ready and calibration ready -> `start_collecting`
7. scanned/classified with no queue -> `open_capture_inbox`

The no-queue disabled reason is exactly:

```text
No new or incomplete videos to collect.
```

### Scan Profile workflow

Added `runScanProfileWorkflow(runtime)` to make Scan Profile a one-click controller workflow. It:

- records clicked/running diagnostics before work starts,
- runs the existing profile verification pipeline,
- keeps existing profile scanning, backend classification, and queue building in the existing controller path,
- marks returned failed states as failed instead of success,
- maps profile/tab readiness failures to the user-facing message:

```text
Open a Douyin profile page first.
```

The popup runtime now forces detector reconnect from `ensureContentScriptReady(...)` so a Scan Profile click can recover content-script readiness without requiring a separate reconnect click.

### Start Collecting workflow

Added `runStartCollectingWorkflow(runtime, options)` as the scanner-specific start path. It performs explicit readiness preflight and writes user-facing blocked diagnostics instead of silently returning.

Required blocked messages are emitted for invalid scanner states:

- `Scan Profile first.`
- `No videos are queued for collection.`
- `Calibrate 4 Points first.`
- `Collector runner is not connected yet.`

Blocked preflight does not mark an idle scanner state as globally failed. It records `phase: "blocked"`, `last_error`, `last_action_result: "blocked"`, and `last_action_error`.

### Reset workflow

Added `resetScannerWorkflowState(runtime)` as the scanner reset entry point. It delegates to the reset logic that clears scan/classification/queue/progress/error/pause workflow state while preserving calibration and harvest options.

### Diagnostics

Extended scanner debug state with:

- `last_action_clicked`
- `last_action_result`
- `last_action_error`

Both scan and start workflow success/failure/final states preserve the clicked action so UI diagnostics can show which button initiated the latest workflow.

### Test/view-model alignment

Updated scanner view-model coverage for the Phase 21D-13 canonical scanner workflow:

- Scanner main/canonical readiness now expects `Start Collecting` when scan, classification, queue, and calibration are ready.
- The legacy Run tab can still expose `Extract Next 10` for its existing extraction action mapping.
- Stale legacy `harvest.status: "running"` locks no longer force the scanner primary action into `pause` when `getScannerBusyState(state)` has determined the lock is stale.
- A zero-target scan that has not completed classification still remains on the `Scan Profile` planning path; classified empty queues use the no-new/incomplete capture-inbox path.

## Validation

Commands run after the final code edits:

```text
npx tsx src/wholeProfileHarvest.viewModel.test.ts
npx tsx src/wholeProfileHarvest.readiness.test.ts
npx tsx src/wholeProfileHarvest.test.ts
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

All passed at the time of this log.
