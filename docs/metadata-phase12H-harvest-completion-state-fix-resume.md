# Phase 12H Harvest Completion State Fix Resume

## Task

Fix Smart Capture & Harvest completion state when the target index reaches target count. The narrow bug is the stuck terminal case where progress reaches the final target, such as `53 / 53`, but the extension remains running in `extracting_metrics`.

## Files Changed

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupProgress.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/popupProgress.test.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
- `docs/metadata-phase12H-harvest-completion-state-fix-log.md`
- `docs/metadata-phase12H-harvest-completion-state-fix-resume.md`

## Root Cause

The harvest loop could process the last target item, persist a running phase such as `extracting_metrics`, and only rely on later loop/finalizer behavior to finish. Because there was no single guard run after each final-target boundary, the UI could observe and keep displaying a running state even though all targets were already processed.

## Completion Guard Behavior

The controller now has one completion guard:

- complete when `processed_count >= target_count`
- for explicit target queues, complete when all `target_aweme_ids` have status `updated`, `failed`, or `skipped`
- run after resume state load, failure marking, successful queueing, flush success, and before next navigation

## Final Flush Behavior

When the guard detects completion, the controller enters the terminal finalizer. If pending items exist, it flushes before persisting completion. After flush success, it persists either `completed` or `completed_with_warnings`. If the final target is already complete, it does not call next navigation and does not wait for modal id change.

## Completed / Completed With Warnings Behavior

- `failed_count = 0`:
  - phase/current state: `completed`
  - message: `Harvest completed. Updated Y/Y.` as UI summary behavior
  - last error cleared
- `failed_count > 0`:
  - phase/current state: `completed_with_warnings`
  - message: `Harvest completed with warnings. Updated X/Y. Failed Z.`
  - retry failed flow remains available

The popup progress phase view now maps `completed_with_warnings` to `Completed with warnings` instead of falling through to `Harvesting...`.

## Tests To Run / Run

Targeted tests already passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture exec -- tsx src/modalHarvest.test.ts && npm --workspace @reup-douyin/extension-douyin-capture exec -- tsx src/popupProgress.test.ts && npm --workspace @reup-douyin/extension-douyin-capture exec -- tsx src/popupWorkflow.test.ts
```

Required final verification commands:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Steps

1. Reload the extension.
2. Open the target Douyin profile/grid.
3. Start Smart Capture & Harvest with target count 53.
4. Let the modal process through the final target.
5. At `Target index: 53 / 53`, verify it transitions away from `Extracting metrics...`.
6. Verify pending items flush and no next navigation is attempted.
7. Verify the final state is not running and the next action is `Review results`.
8. Verify success case shows `Harvest completed`, `Updated 53 / 53`, `Failed 0`, and `Flushed 53`.
9. Verify warning case shows `Harvest completed with warnings`, `Updated 52 / 53`, `Failed 1`, and Retry Failed Only remains available.
10. Reopen popup / Show Progress after completion and verify the state stays terminal rather than normalizing back to running.
