# Douyin Capture Inbox Wording Cleanup User Guide

## Purpose

Capture Inbox is the staging workspace for Douyin extension captures. The wording now helps an operator quickly understand what is ready, what needs action, and what can safely move to Review Board.

## Wording Principles

- Use short labels.
- Prefer action-first wording.
- Use one term for one concept.
- Keep helper text useful and brief.
- Use honest state labels for missing or unfinished data.
- Keep technical wording in diagnostics and raw details where it helps troubleshooting.

## Operator Terminology

### Statuses

- `Captured`: all staged items in the selected session.
- `Ready`: item can be promoted to Review Board.
- `Needs action`: item needs follow-up, enrichment, preview, or operator review.
- `Preview pending`: preview readiness is not complete.
- `Duplicate`: item appears to repeat an existing capture/source.
- `Failed`: enrichment or preview work failed.
- `Promoted`: item was sent to Review Board.
- `Excluded`: item is intentionally kept out of promotion.

### Actions

- `Details`: open item details.
- `Promote`: send a ready item to Review Board.
- `Promote ready items`: send all ready items in the selected session to Review Board.
- `Promote selected`: send selected ready items to Review Board.
- `Retry enrich`: rerun enrichment.
- `Retry enrich selected`: rerun enrichment for eligible selected items.
- `Retry preview`: rerun preview readiness.
- `Exclude`: keep the item out of promotion.
- `Exclude selected`: exclude eligible selected items.
- `Delete staged item`: remove a local staged item from Capture Inbox.
- `Delete selected`: remove eligible selected staged items.
- `Delete session`: remove a local staged capture session and its staged items.
- `Open source`: open the source URL/profile when available.

### Fallback States

- `Not captured`: source data was not present in the capture payload.
- `Pending`: the value or readiness check is not complete yet.
- `Not analyzed yet`: analysis has not produced a result.
- `None`: no diagnostic/error value exists.

## Current Page Copy Map

### Page Header

- Title: `Douyin Capture Inbox`
- Page description: `Review staged Douyin videos before they move to Review Board.`
- Shell description: `Stage Douyin captures, fix incomplete items, and promote ready work to Review Board.`

### Summary And Search

- Summary title: `Capture summary`
- Search title: `Find captured items`
- Search helper: `Search by caption, video ID, source, or status.`
- Search placeholder: `Caption, video ID, or source`

### Detail Drawer

- Drawer eyebrow: `Details`
- Drawer title: `Item details`
- Empty drawer fallback: `Select an item to view details.`
- Main sections:
  - `Overview`
  - `Captured text`
  - `Source`
  - `Metadata`
  - `Outputs`
  - `Diagnostics`
  - `Raw details`

## Technical Text That Should Stay Technical

Do not oversimplify these areas because they help support/debugging:

- Diagnostics
- Raw details
- Action source URLs
- Latest raw action details
- Item ID
- Video ID
- Dedupe/readiness metadata
- JSON payloads
- Source URLs
- Raw session status enum values in the session filter

## Safe Delete Wording

Delete copy stays explicit:

- Deleting a staged item removes it from Capture Inbox.
- Promoted items are skipped for staged item deletion.
- Deleting a session removes the local staged session and local staged items.
- Promoted Review Board records are not deleted.

## Operator Flow After Cleanup

1. Select a capture session.
2. Review summary cards for `Ready`, `Needs action`, `Failed`, and `Promoted` counts.
3. Search or filter captured items.
4. Open `Details` for any item that needs inspection.
5. Use `Promote`, `Retry enrich`, `Retry preview`, `Exclude`, or `Delete staged item` as needed.
6. Promote ready items to Review Board.
7. Continue review work in Review Board.

## Verification

The wording cleanup was verified with:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```

Both the focused Capture Inbox test and the web typecheck passed.
