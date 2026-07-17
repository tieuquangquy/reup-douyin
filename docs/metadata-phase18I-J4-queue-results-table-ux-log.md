# Phase 18I-J4 Queue / Results Table UX Log

## Why blobs were replaced

Queue preview and recent result areas were still rendering as wrapped text lists. That made it hard to scan:

- which target was pending
- which target extracted successfully
- which result flushed
- which item failed
- which targets were skipped because they were already complete

The popup now renders compact row tables instead of long text blobs.

## Queue table fields

Queue Preview rows now show:

- index
- capture-status chip
- shortened aweme id
- shortened title
- queue status

The main panel shows the first 5 rows and `+N more` when extra targets exist.

## Extraction results table fields

Recent Extraction Results rows now show:

- index
- result-status chip
- shortened aweme id
- duration
- inline metrics: likes, comments, favorites, shares
- error code when extraction failed

## Backend results table fields

Recent Backend Results rows now show:

- index
- backend-status chip
- shortened aweme id
- shortened Capture Inbox item id when present
- metadata/backend status
- error code when flush failed

## Empty states

- Queue: `No queue yet. Verify Profile and choose Run Extraction.`
- Extraction: `No extraction results yet.`
- Backend: `No backend flush results yet.`
- If verified but no eligible targets remain in `new_and_incomplete`, Queue explains that complete videos were skipped.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Next UX phase plan

- tighten Details layout for larger full lists
- optionally add row-level copy helpers for aweme ids / item ids
- keep main popup fixed-height and compact as result counts grow
