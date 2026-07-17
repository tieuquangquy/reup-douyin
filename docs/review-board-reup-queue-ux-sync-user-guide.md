# Review Board + Reup Queue UX Sync User Guide

## Purpose

Review Board and Reup Queue now follow the same operator workflow language as Capture Inbox. The pages are designed for fast local-first review while keeping future SaaS boundaries clean.

## Shared workflow rhythm

Use these pages from left to right in the operator flow:

1. Capture Inbox: triage captured Douyin items.
2. Review Board: decide whether candidates should be kept, rejected, or approved.
3. Reup Queue: move approved work through media prep, export package, and publish handoff states.

## Review Board

### Status strip

The compact status strip shows candidate counts by review state. Select a status pill to narrow the candidate list without changing any candidate state.

### Filters

Use the filter toolbar to search, sort, apply score bounds, choose a preset, or filter by status. Filters only change what is visible.

### Candidate workspace

Candidate cards show media preview, review score, source metadata, status, and next action. Use checkboxes for batch selection. Use Details or the media/title area to inspect a candidate.

### Right-side inspector

The right-side inspector shows the active candidate. It stays sticky on desktop and contains source context, review evidence, score metadata, downstream state, and diagnostics. Closing the inspector clears the active candidate but does not change selected checkboxes.

### Actions

- Keep/Approve preserves the candidate as approved work.
- Reject stops the candidate before Reup Queue.
- Mark in review keeps the candidate in manual review.
- Send to Reup Queue only applies to approved candidates.

## Reup Queue

### Status strip

The compact status strip shows queue counts by operational state. Selecting a status narrows visible queue items only.

### Filters

Search can match title, source, candidate id, export package, publish handoff, next action, and failure text. Sorting changes visible order only.

### Queue workspace

Queue cards show a media preview or placeholder, lifecycle status, media-prep readiness, downstream artifact ids where available, and the next operator action.

### Right-side inspector

The right-side inspector shows the active queue item. It stays sticky on desktop and separates lifecycle details into overview, queue lifecycle, source/review origin, media prep, export package, publish handoff, and diagnostics.

### Actions

Queue actions remain explicit lifecycle transitions. The page does not run hidden publishing automation. Export package and publish handoff actions create inspectable downstream artifacts and keep manual boundaries visible.

## Batch selection

Checkbox selection is independent from the right-side inspector on both pages. Selecting rows opens the sticky batch bar. Clearing selection does not change backend state.

## Empty, loading, and error states

Loading and error states use shared panels. Empty visible lists explain whether no data is loaded or filters are hiding work. Empty inspectors ask the operator to select an item for details.

## Verification status

The UX sync has been implemented and verified with:

```cmd
npx tsx apps/web/src/test/review-board.test.ts
npx tsx apps/web/src/test/reup-queue.test.ts
npm run typecheck --workspace apps/web
```
