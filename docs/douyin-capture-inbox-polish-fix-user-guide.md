# Douyin Capture Inbox Polish Fix User Guide

## What changed

The Capture Inbox remains the staging workspace for videos captured by the Douyin browser extension. This polish pass improves correctness and readability without changing the workflow.

## Deleting staged items

Use `Delete staged item` on a card or `Delete selected` in batch actions. Promoted items are protected and skipped. After confirmation, deleted staged items are removed from the visible cards and the summary count reflects the current remaining items.

## Thumbnails

Cards show a real captured thumbnail, cover, poster, or image-like preview URL when the capture payload includes one. If no image URL exists, the card shows `No thumbnail available` with the current preview state. The app does not fake thumbnails.

## Details drawer

Use `Open details drawer`, `Details`, `View more`, or the card thumbnail area to open the item inspector. The drawer shows full title/caption, source links, readiness, media/thumbnail state, and collapsed diagnostics.

## Long titles and captions

Cards show short clamped text so the grid remains scannable. Use the detail drawer to read the full caption/title.

## Capture Sessions panel

The sessions list is compact. Each row shows a short capture/session identifier, status, timestamp, and concise count chips for captured, ready, duplicate, and failed items.

## Item Detail panel

The detail panel is organized for operators first:

- Overview: current status, next action, and full caption.
- Source: source video id and links.
- Readiness: duration, posted time, dedupe, preview/media state.
- Diagnostics: collapsed raw metadata and error details for troubleshooting.

## Limitation

Thumbnail availability still depends on the extension/backend receiving real image URLs from Douyin page data. If Douyin does not expose an image URL in the captured payload, the UI keeps the honest placeholder.
