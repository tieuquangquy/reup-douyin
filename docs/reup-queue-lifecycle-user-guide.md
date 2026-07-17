# Reup Queue Lifecycle User Guide

## What Reup Queue Does

Reup Queue is the operator workspace for videos that have already passed Review Board approval. It is not raw capture and it is not review. It tracks approved downstream work and prepares items for future export/publish workflows.

## Workflow

```text
Capture Inbox -> Review Board -> Reup Queue -> Media prep -> Ready to export
```

1. Capture items through the Douyin extension.
2. Promote usable capture items into Review Board.
3. Approve candidates in Review Board.
4. Explicitly send approved candidates to Reup Queue.
5. Use Reup Queue actions to process, block, hold, retry, or complete downstream work.
6. Stop this slice at Ready to export.

## Queue Buckets

- Ready for processing: approved items waiting to start.
- Waiting for media: source media is not ready or not confirmed.
- Waiting for metadata prep: media exists but captions/language/prep details need work.
- Processing: operator or future worker is preparing the item.
- Ready to export: item has completed media-prep handoff.
- Ready to publish: reserved for later downstream publish readiness.
- Failed / needs attention: an error or blocker requires operator decision.
- Completed: downstream work is done.
- Cancelled: item was intentionally removed from active work.

## Operator Actions

### Start processing

Use this when an approved queue item should begin downstream preparation. This does not run long video processing inline; it records the explicit lifecycle transition.

### Mark media ready

Use this after source media is known to be available or attached. Add a short safe note if needed. The item advances toward metadata preparation or export readiness.

### Mark blocked

Use this when the item cannot move forward. Choose a safe reason such as missing media, missing metadata, source unavailable, or operator decision. Do not paste secrets, cookies, tokens, private file paths, or account credentials.

### Hold / Pause

Use this when work should be paused without cancelling it. Add a short reason that another operator can understand.

### Resume

Use this when a held or waiting item can continue.

### Retry

Use this after a failed item has been corrected and should return to processing readiness.

### Cancel

Use this when the item should not continue downstream. Cancellation is explicit and visible.

### Mark completed

Use this only when downstream work has genuinely finished outside this slice or through a future linked workflow.

## Safe Notes

Operator notes and blocked reasons are visible in the UI and may be logged as lifecycle metadata. Keep notes short and safe:

- Good: `Source media unavailable from current capture.`
- Good: `Waiting for caption language decision.`
- Bad: browser cookies, tokens, account passwords, private local paths, or raw credential dumps.

## Current Limitations

- No automatic media download is implemented in this slice.
- No video processing is implemented in this slice.
- No automatic export job is implemented in this slice.
- No publish automation is implemented in this slice.
- `READY_TO_EXPORT` is the intended handoff point for future export/publish work.
