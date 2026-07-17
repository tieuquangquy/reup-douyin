# Phase 22A-1 Reset Hard Clear Workflow Resume

## Status

Phase 22A-1 implementation is complete pending validation commands.

## Changed Areas

- `apps/extension-douyin-capture/src/popup.ts`
  - Reset click handlers now pass the click event.
  - Reset handler prevents default behavior, stops propagation, writes canonical reset state, updates local popup state, and re-renders immediately from the returned reset state.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - Hard reset diagnostics were expanded.
  - Reset continues to clear scan/classification/queue/progress/workflow state while preserving calibration/settings/context.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
  - Advanced technical rows now include reset diagnostics.

- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
  - Reset assertions expanded for scan/classification/queue/progress/workflow/storage write diagnostics.
  - Busy reset case added.

- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
  - Static popup reset assertions added.
  - Post-reset view-model assertions added.

## Validation To Run

Run from repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

Focused commands useful if failures occur:

```bash
cd apps/extension-douyin-capture && npx tsx src/wholeProfileHarvest.test.ts
cd apps/extension-douyin-capture && npx tsx src/wholeProfileHarvest.viewModel.test.ts
```

## Manual Retest Steps

1. Open a Douyin profile and scan until the scanner shows videos and a non-empty queue.
2. Confirm the popup shows `Start Collecting` and queue/new counts.
3. Click the footer `Reset` button.
4. Confirm the popup does not reload or close.
5. Confirm the scanner immediately shows `Ready` and primary action `Scan Profile`.
6. Confirm stats are hidden or counts are zero.
7. Confirm calibration remains ready and settings remain unchanged.
8. Open Advanced details and confirm reset diagnostics show success and `queueCount` is `0`.
9. Close and reopen the popup; confirm the old queue/counts do not return.
10. Repeat while collection state is running or stuck; reset should still clear `active_task`, `action_lock`, current target, current index, and queue.

## Notes For Future Work

- `reset_background_cancel_status` is recorded as `not_applicable_local_controller` because the current canonical scanner reset is a storage-level controller operation. If a distributed/background job runner is introduced, wire explicit cancellation into this diagnostic.
- Reset intentionally preserves profile/page context so the operator can immediately run `Scan Profile` again on the same page.
