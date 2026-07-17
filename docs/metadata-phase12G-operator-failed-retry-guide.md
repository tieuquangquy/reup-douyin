# Phase 12G Operator Failed Retry Guide

## When To Use

Use **Retry Failed Only** when Smart Capture & Harvest finishes as `completed_with_warnings` or `failed` and the progress panel shows failed targets.

## Steps

1. Keep or reopen the Douyin modal for the same captured profile/session.
2. Open the extension popup.
3. Review the harvest panel:
   - Mode
   - Target index
   - Updated
   - Failed
   - Skipped
   - Remaining
   - Failed target list
4. Click **Retry Failed Only**.
5. Keep the modal open while the popup shows `Retry failed: X / Y`.
6. When complete, verify the final state is `completed` or `completed_with_warnings`.
7. If failures remain, repeat Retry Failed Only only for the remaining failed targets.

## Expected Behavior

- Updated targets are not rerun.
- Failed targets are retried from the failed status map only.
- Progress never displays an index greater than the target count.
- A single stuck video is marked failed and the batch continues unless fatal thresholds are reached.
