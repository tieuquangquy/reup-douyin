# Phase 13J Modal-Start Operator Guide

## Purpose

This guide explains how to run Smart Capture & Harvest safely when starting from a Douyin modal URL and how to verify target-queue coverage before launching full modal harvest.

## When To Use

Use this workflow when the active tab is a profile modal URL such as:

- `https://www.douyin.com/user/<profile>?modal_id=<aweme_id>`

and you want Smart Capture & Harvest to process only the selected incremental target queue (`new_only`, `new_and_incomplete`, or `refresh_all`).

## Pre-Checks

1. Open the Douyin tab you intend to process.
2. Open the extension popup.
3. Confirm the selected Smart harvest mode matches your intention.
4. If needed, click `Reconnect Douyin tab` to refresh detector/content-script readiness.

## Modal-Start Smart Capture Flow

1. On a modal URL, click `Smart Capture & Harvest`.
2. If capture session + target queue are already known, the extension continues directly to modal calibration/probe/harvest gating.
3. If queue is unknown, the extension temporarily resolves the profile queue first:
   - navigates to profile URL without `modal_id`
   - runs profile capture
   - restores the original modal URL
4. If target queue remains empty for the selected mode, the run ends as no-op with:
   - `No new or incomplete videos found.`
5. If target queue exists, continue normal calibration/probe/start behavior.

## Verify Modal Harvest Coverage Action

Use `Verify Modal Harvest Coverage` before starting/resuming harvest when you need explicit confirmation.

The Details panel includes:

- Modal aweme
- Profile queue resolved status
- Capture session known/missing
- Target queue known/missing
- Total profile videos
- Target mode
- Target count
- Current modal in queue
- Remaining after current
- Can harvest all
- Reason

## How To Interpret Coverage

### `Can harvest all = yes`

Safe to start/resume harvest from current modal under the selected mode.

### `Can harvest all = no`

Read `Reason` and apply the action:

- `Active tab is not a Douyin profile modal URL.`
  - Open a supported modal URL first.
- `Capture session missing; resolve profile queue first.`
  - Run capture from profile / Smart Capture from profile.
- `Target queue missing; resolve profile queue first.`
  - Re-run Smart Capture so queue is rebuilt.
- `Current modal is not in the target queue for the selected mode.`
  - This modal is excluded for current mode; open a target modal or change mode and recapture.

## Recommended Retest Sequence (Phase 13J)

1. Start on a profile page and run Smart Capture.
2. Open a modal from the same profile.
3. Click `Verify Modal Harvest Coverage` and confirm expected mode/queue values.
4. Trigger Smart Capture & Harvest from modal.
5. Confirm queue-resolution path occurs only when queue is unknown.
6. Confirm modal URL is restored after profile queue resolution.
7. Confirm missing queue/session blockers are explicit and actionable.
8. Confirm excluded current modal reports `Current modal is not in the target queue for the selected mode.`

## Notes

- This phase changes extension-side popup orchestration only.
- Backend API contracts and worker queue architecture are unchanged.
