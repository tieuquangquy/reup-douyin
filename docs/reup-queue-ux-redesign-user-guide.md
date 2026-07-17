# Reup Queue UX Redesign User Guide

## Page

Open the Reup Queue at:

- `/selection/reup-queue`

The page sits after Review Board approval and before Export Package / Publish Handoff work.

Workflow context:

Capture Inbox -> Review Board -> Reup Queue -> Media prep -> Export Package -> Publish Handoff.

## What the Reup Queue is for

Use Reup Queue to manage approved videos that are moving toward downstream export and publishing handoff preparation. The queue helps an operator see:

- what can start processing;
- what is waiting for media or metadata;
- what is processing;
- what is ready to export;
- what has an Export Package;
- what is ready for Publish Handoff;
- what failed and needs attention;
- what is completed or cancelled.

## Recommended next action

The top banner tells you the most useful next action based on the current queue state. It prioritizes failures, export-ready items, handoff-ready items, blocked items, and ready-to-process items.

## Summary cards

Use the summary cards to filter the queue by work state:

- Ready to process
- Waiting for media
- Waiting for metadata
- Processing
- Ready to export
- Ready to publish
- Failed
- Completed
- Cancelled

Click a card to focus the list on that state.

## Search and sort

Use search to find queue items by title, source identifiers, candidate id, package id, handoff id, next action, or error text.

Sort options:

- Newest
- Ready first
- Needs attention first
- Export ready first

## Queue cards

Each queue card shows only the most important operator information:

- title or source id;
- source/profile hint;
- status badge;
- queue stage;
- next action;
- export package status;
- publish handoff status;
- contextual actions.

Select a checkbox to include an item in batch actions. Use `View details` to inspect the full detail panel.

## Detail panel

The right-side detail panel gives deeper context without cluttering the queue list. It includes:

- Overview
- Queue lifecycle
- Source / Review context
- Media prep status
- Export Package
- Publish Handoff
- Diagnostics

Raw queue JSON is kept collapsed under diagnostics for troubleshooting.

## Batch actions

When one or more items are selected, use the sticky batch action bar for multi-item work:

- Start processing
- Hold
- Resume
- Retry
- Mark media ready
- Create Export Package
- Create Publish Handoff
- Cancel

Batch action results show how many items succeeded, were skipped, or failed. Per-item details remain available for inspection.

## Export Package

Use `Create Export Package` for selected items that are ready to export. The package is an inspectable artifact and can be opened from the Reup Queue item detail or the Export Packages page.

## Publish Handoff

Use `Create Publish Handoff` only when selected items are ready for handoff. This creates an inspectable handoff artifact. It does not publish externally.

## Honest missing values

If data is not available yet, the page uses clear labels such as:

- `Pending`
- `Not packaged`
- `No handoff`
- `Not prepared yet`
- `Needs action`

These labels mean the data has not reached that workflow step yet or requires operator/backend action.
