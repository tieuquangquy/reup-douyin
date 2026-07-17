# Douyin Capture Inbox Card Redesign User Guide

## What changed

The Capture Inbox is being redesigned as a visual staging workspace for Douyin extension captures.

Instead of scanning a dense text list, the operator should work from video-style cards with thumbnails, status badges, compact metadata, and contextual actions.

## Where to open it

Open the Ops Console route:

`/ops/extensions/douyin/capture-inbox`

## Main workflow

1. Select a capture session from the session panel.
2. Review the summary cards to understand captured, ready, duplicate, failed, and promoted counts.
3. Use search, filters, and sort controls to narrow the staging set.
4. Scan video cards visually using thumbnails and status badges.
5. Open item details when needed.
6. Promote ready items to Review Board.
7. Retry enrichment or preview generation for incomplete items.
8. Exclude items that should remain recorded but skipped.
9. Delete staged items only when they should be removed from Capture Inbox.

## Card states

Each item card should show:

- A thumbnail when available.
- A clear `No thumbnail available` placeholder when no thumbnail is available.
- Current staging status.
- Caption or fallback title.
- Source/video identity.
- Compact metadata such as duration, posted date, views, likes, and comments when available.
- The recommended next action.

## Details drawer

Use the details action or click/focus behavior to inspect a staged item.

The details drawer contains:

- Overview.
- Source and references.
- Metadata.
- Outputs and downstream artifact references.
- Collapsed diagnostics for raw payloads and action details.

Diagnostics are intentionally not shown on every card so the main workspace remains operator-friendly.

## Actions

### Promote

Promotes ready staged items into the Review Board flow.

### Retry enrich

Retries metadata/enrichment for raw or incomplete staged items.

### Retry preview

Retries preview/thumbnail readiness for items missing preview state.

### Exclude

Marks an item as excluded while preserving the staged record and reason.

Use exclude when the operator wants an audit trail that the item was reviewed and skipped.

### Delete staged item

Deletes staged rows from Capture Inbox after confirmation.

Use delete when the item should be removed from the staging workspace rather than kept as an excluded/skipped record.

Promoted items should not be deleted from Capture Inbox through this action because they may already have downstream Review Board or candidate references.

## Bulk actions

When items are selected, a sticky bulk action bar appears.

Expected bulk actions:

- Promote selected ready items.
- Retry selected retryable items.
- Exclude selected non-promoted items.
- Delete selected staged items after confirmation.
- Clear selection.

## Safety notes

- Delete is explicit and confirmation-based.
- Exclude is safer when you want to preserve an operator decision trail.
- Promotion still goes through the existing Review Board path.
- No long-running video processing runs in the browser UI.

## Troubleshooting

If thumbnails do not appear:

1. Confirm the raw capture payload includes `thumbnail_url`, `cover_url`, or `poster_url`.
2. Confirm the item has `preview_ready` or `thumbnail_url` in the details drawer.
3. Use retry preview for preview-missing items.
4. If no image is available from the source payload, the card should show `No thumbnail available` honestly.
