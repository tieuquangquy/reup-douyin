# Phase 12H Harvest Completion State Fix Log

## Scope

Phase 12H fixes one narrow extension issue: Smart Capture & Harvest could remain in a running `extracting_metrics` state when the target index reached the target count, for example `53 / 53`.

Touched area:

- `apps/extension-douyin-capture`
- extension tests for harvest completion state
- Phase 12H documentation

Non-goals:

- No backend changes.
- No web app changes.
- No metric extraction changes.
- No broad navigation rewrite.
- No CDP/debug workflow reintroduction.
- No five-point calibration requirement.

## Root Cause

The harvest loop processed the final target item but did not consistently run a terminal completion check after the final item was extracted, queued, and flushed. In the final-target path, state could be persisted while still reporting `phase: extracting_metrics` or another running phase before the finalizer completed, and the popup could continue to show a running harvest even though processed target count already equaled target count.

The visible symptom was:

- Harvest running.
- Current state harvesting.
- Target index equal to target count, such as `53 / 53`.
- Phase stuck at `Extracting metrics...`.
- No next navigation should be needed, but the UI did not transition to completion.

## Completion Guard

A single completion guard was added to the modal harvest controller:

- `isHarvestComplete(state)` behavior is implemented by `FullModalHarvestController.isHarvestComplete()`.
- It returns complete when `processed_count >= target_count`.
- For explicit target queues, it returns complete only when every `target_aweme_id` has status `updated`, `failed`, or `skipped`.
- `processed_count` is represented as `updated_count + failed_count + skipped_count` through existing controller counters.

The guard now runs at the critical final-target boundaries:

- after resume state is loaded
- after marking an item failed
- after a successful item is extracted and queued
- after a flush succeeds
- before attempting next navigation

This prevents the controller from waiting for a modal id change or attempting next-video navigation after the final target is already processed.

## Final Flush Behavior

Terminal completion flows through the controller finalizer. If pending items exist at completion time, the controller enters `flushing`, flushes pending payloads, then persists a terminal state.

Expected final behavior:

- pending items are flushed before terminal completion
- if flush fails, harvest fails with backend flush failure state
- if flush succeeds, harvest moves to `completed` or `completed_with_warnings`
- no additional navigation is attempted after the final target

## Completed and Completed With Warnings

Terminal state behavior is now explicit:

- zero failed targets:
  - `phase: completed`
  - `current_state: completed`
  - no final error
  - popup title: `Harvest completed`
- one or more failed targets:
  - `phase: completed_with_warnings`
  - `current_state: completed_with_warnings`
  - warning message: `Harvest completed with warnings. Updated X/Y. Failed Z.`
  - popup title: `Harvest completed with warnings`

The popup workflow maps terminal progress to `next_required_action: Review results` and does not keep Smart Capture & Harvest in a running state.

## Defensive Normalization

Restored harvest progress now normalizes impossible states where the persisted target count is already fully processed but the stored phase/current state is still running. On popup refresh or Show Progress, a processed target set returns terminal progress rather than a running `extracting_metrics` view.

## Tests Run

Targeted Phase 12H command run successfully:

```bash
npm --workspace @reup-douyin/extension-douyin-capture exec -- tsx src/modalHarvest.test.ts && npm --workspace @reup-douyin/extension-douyin-capture exec -- tsx src/popupProgress.test.ts && npm --workspace @reup-douyin/extension-douyin-capture exec -- tsx src/popupWorkflow.test.ts
```

Full required verification commands are tracked in the resume doc and final report.

## Live Retest Steps

1. Reload the unpacked extension in the browser.
2. Open the Douyin profile/grid used for Smart Capture & Harvest.
3. Start Smart Capture & Harvest with a target count that reaches the known final item, such as 53.
4. Keep the modal open and allow the harvest to process the final target.
5. Confirm the popup never remains at `Harvest running` with `Target index: 53 / 53` and `Extracting metrics...`.
6. Confirm pending items flush at the final target.
7. Confirm the final popup shows `Harvest completed` with `Updated 53 / 53`, `Failed 0`, `Flushed 53`, elapsed time, and average per video.
8. If one target fails, confirm final popup shows `Harvest completed with warnings`, `Updated 52 / 53`, `Failed 1`, and exposes retry failed behavior.
9. Confirm Smart Capture & Harvest controls are enabled again after terminal state.
