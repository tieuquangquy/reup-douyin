# Reup Queue UX Redesign Architecture

## Purpose

This document defines the operator-first Reup Queue UI architecture. The redesign aligns Reup Queue with the Capture Inbox workspace pattern while preserving backend-owned queue lifecycle, media prep state, Export Package creation, and Publish Handoff creation.

## Boundary

`apps/web` owns this UX slice. It may call existing API functions, render operator state, and submit explicit operator actions.

`apps/web` must not:

- run video processing;
- perform queue orchestration;
- write directly to the database;
- create hidden publishing side effects;
- infer backend state transitions outside the available API contracts.

## Data inputs

The page uses existing API functions:

- `fetchReupQueueItems`
- `runReupQueueAction`
- `runReupQueueBatchAction`

The primary item type is `ReupQueueItem`, which already includes:

- lifecycle status;
- media prep status;
- queue bucket and next action;
- source video context;
- available item actions;
- lifecycle timestamps;
- blocked/error details;
- metadata for Export Package and Publish Handoff references.

No backend schema changes are planned for this redesign.

## Page hierarchy

### Header

The header should identify the page as `Reup Queue` and show a short workflow subtitle:

Capture Inbox -> Review Board -> Reup Queue -> Media prep -> Export Package -> Publish Handoff.

Primary actions should emphasize downstream handoff work:

- Create Export Package from selected eligible items.
- Create Publish Handoff from selected eligible items.

Secondary links:

- Refresh queue.
- Export Packages.
- Publish Handoffs.

### Recommended next action

A banner summarizes the most useful next operator action from current queue state. Priority order:

1. Failed / needs attention.
2. Ready to export.
3. Ready to publish handoff.
4. Waiting for media or metadata.
5. Ready to process.
6. Processing.
7. Completed/cancelled only.

### Summary cards

Summary cards are clickable filters, not just metrics. Required cards:

- Ready to process.
- Waiting for media.
- Waiting for metadata.
- Processing.
- Ready to export.
- Ready to publish.
- Failed.
- Completed.
- Cancelled.

The cards filter the list to the associated operator state.

### Filter, search, and sort row

The operator can search by:

- title/caption;
- source video id/external id;
- video candidate id;
- source profile id;
- Export Package id;
- Publish Handoff id;
- next action;
- blocked/error text.

Sort modes:

- Newest.
- Ready first.
- Needs attention first.
- Export ready first.

### List cards

Collapsed cards should avoid technical queue dump behavior. Each card should show:

- checkbox for batch selection;
- title/caption snippet;
- source/profile identity when available;
- status badge;
- queue stage;
- prominent next action;
- export readiness summary;
- handoff summary;
- one or more contextual action buttons.

Technical fields such as raw metadata, full lifecycle timestamps, blocked diagnostics, and JSON payloads belong in the detail panel.

### Detail panel

The detail panel is a persistent right-side workspace. It should include semantic sections:

1. Overview
   - status;
   - queue stage;
   - next action;
   - priority.
2. Queue lifecycle
   - queued, started, held, failed, completed, cancelled timestamps;
   - last action and last action note.
3. Source / Review context
   - source video id;
   - external source id;
   - candidate id;
   - source link when available.
4. Media prep status
   - media prep status;
   - prep job id;
   - render output id.
5. Export Package
   - package id link when present;
   - readiness label when absent.
6. Publish Handoff
   - handoff id link when present;
   - target/attempt status when available.
7. Diagnostics
   - blocked reason;
   - error code/message;
   - raw item JSON in collapsed disclosure.

### Batch action bar

Batch actions should be sticky and state-aware. It should show selected count and eligible count for each action where possible. It must continue using existing backend batch actions:

- `START_PROCESSING`
- `HOLD`
- `RESUME`
- `RETRY`
- `MARK_MEDIA_READY`
- `CREATE_EXPORT_PACKAGE`
- `CREATE_PUBLISH_HANDOFF`
- `CANCEL`

Batch result details should remain inspectable after an action, including per-item result codes.

## Operator state vocabulary

Use honest labels:

- `Pending`
- `Not packaged`
- `No handoff`
- `Not prepared yet`
- `Needs action`
- `Waiting for media`
- `Waiting for metadata`
- `Ready to export`
- `Ready for handoff`

Avoid ambiguous placeholders such as `Unknown / missing`.

## Export and Publish Handoff safety

The UI may create Export Packages and Publish Handoffs through existing explicit operator actions. A Publish Handoff is an inspectable manual handoff artifact. It must not execute external publishing.

## Testing expectations

The Reup Queue source test should assert:

- operator-first title/header;
- full workflow path;
- recommended next action banner;
- clickable summary cards;
- search/filter/sort row;
- simplified queue cards;
- right-side detail panel sections;
- contextual item actions;
- sticky batch action bar;
- Export Package / Publish Handoff visibility;
- collapsed diagnostics;
- honest value labels;
- existing action constants remain present.
