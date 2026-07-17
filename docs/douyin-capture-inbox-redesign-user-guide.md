# Douyin Capture Inbox Redesign User Guide

## Workflow overview

Use the workflow in this order:

1. Capture from Douyin with the browser extension.
2. Open Capture Inbox to inspect the staged capture session.
3. Fix or exclude items that are incomplete, duplicate, or failed.
4. Promote usable items to the Review Board.
5. Review candidates in Review Board.
6. Send approved candidates to Reup Queue.
7. Continue downstream processing, export, final review, publish draft preparation, and publish control.

## Capture Inbox

Capture Inbox is a staging workspace. It answers:

- Captured: how many items the extension saw and staged.
- Usable: items ready to promote into canonical review.
- Duplicate: items already seen in the same capture or canonical data.
- Pending: items needing enrichment or preview checks.
- Failed: items with an import/enrichment problem.
- Next action: what the operator should do now.

Main actions:

- Retry enrich: use when profile/video identifiers or normalized metadata are missing.
- Retry preview: use when thumbnail/preview state looks incomplete.
- Promote to Review Board: use for ready items only.
- Exclude/skip: use for items that should not enter review.
- Open source: inspect the original Douyin source in the browser.
- View technical details: open safe raw details only when troubleshooting.

## Review Board

Review Board is only for canonical candidates. It should not show raw extension payload cleanup work.

Use Review Board to:

- Move candidates into review.
- Approve usable candidates.
- Reject poor or risky candidates.
- Send approved candidates to Reup Queue.

## Reup Queue

Reup Queue is for approved downstream work. It groups approved candidates by what needs to happen next:

- Ready for processing: approved and queued.
- Waiting for media: source media is not ready yet.
- Waiting for metadata prep: metadata/caption preparation is incomplete.
- Ready to export/publish: downstream output is ready for final publishing steps.
- Failed/needs attention: operator must inspect a problem.
- Completed: downstream work is finished.

Reup Queue is not a second review board. It should not be used to re-decide whether a video is good content; that decision belongs in Review Board.

## Troubleshooting

- If Capture Inbox has many duplicates, promote only the ready non-duplicate items.
- If items are pending, retry enrichment or preview before promotion.
- If Review Board has approved items but Reup Queue is empty, use Send to Reup Queue and refresh.
- If queue items are waiting for media, downstream download/processing work has not completed yet.
- If queue items failed, inspect the queue item detail and related job when available.

## Safety

Do not paste or display cookies, tokens, account credentials, or private local paths in notes, logs, or UI fields.
