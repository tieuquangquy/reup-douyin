# Ops Console Design System User Guide

## Purpose

The Ops Console Design System makes the main operator workflow feel like one product:

Capture Inbox -> Review Board -> Reup Queue -> Export Package -> Publish Handoff.

It does not change what the backend does. It changes how the operator sees, filters, selects, inspects, and acts on workflow records.

## Implementation status

The shared structure is implemented across Capture Inbox, Review Board, Reup Queue, Export Package, and Publish Handoff. Operators should see the same workflow context, summary, filter/list/detail, state, and batch-action language while each page keeps its domain-specific actions.

## Common page structure

Each workflow surface should use the same mental model:

1. Page title and workflow description.
2. Workflow context panel showing where the operator is in the flow.
3. Recommended next action banner.
4. Summary cards with important counts.
5. Search/filter/sort controls when the page has a list.
6. Main list of work items or artifacts.
7. Detail panel or detail sections for the focused item.
8. Sticky batch action bar when multiple selected items can be acted on.
9. Empty/loading/error states that explain what the operator can do next.

## Status badges

Status badges use the same visual meaning everywhere:

- Green: ready, healthy, completed, approved, exported, or handoff-ready.
- Yellow: pending, processing, held, incomplete, or needs operator attention.
- Red: failed, rejected, invalid, or blocked.
- Gray: cancelled, skipped, inactive, unknown, or not applicable.

The exact label remains domain-specific. For example, Reup Queue can show `READY_TO_EXPORT`, while Capture Inbox can show `READY_FOR_REVIEW`.

## Actions

Actions should follow a consistent hierarchy:

- Primary action: advances the workflow.
- Secondary action: safe supporting action.
- Detail/link action: opens or inspects context.
- Danger action: rejects, cancels, or performs a destructive state transition.

Only the page or service decides whether an action is allowed. The design system only makes action placement and visual priority consistent.

## Capture Inbox

Use this surface to stage Douyin extension captures.

Expected operator flow:

1. Choose or review the current capture session.
2. Use summary cards to focus incomplete, duplicate, ready, or promoted captures.
3. Use search and sorting to find a capture by profile, URL, caption, or status.
4. Select captures that need the same action.
5. Promote clean captures to Review Board.
6. Inspect source URLs and raw diagnostics only when needed.

## Review Board

Use this surface to decide which candidates should continue.

Expected operator flow:

1. Review the recommended next action.
2. Filter by status, preset, score, search text, or sort order.
3. Inspect candidates using consistent cards and detail sections.
4. Keep or reject candidates individually or in a batch.
5. Send approved candidates to Reup Queue.

Review Board should guard the Reup Queue transition: only approved candidates should be sent forward.

## Reup Queue

Use this surface to prepare approved candidates for downstream artifact creation.

Expected operator flow:

1. Focus failures or ready-to-export items using summary cards.
2. Search by title, source, candidate id, package id, handoff id, next action, or failure text.
3. Inspect queue lifecycle, media prep, source context, Export Package status, and Publish Handoff status.
4. Run item-level actions or batch actions.
5. Create Export Packages or Publish Handoffs only for eligible work.

Reup Queue does not auto-publish externally.

## Export Package

Use this surface to inspect durable export artifacts.

Expected operator flow:

1. Review package summary and status.
2. Inspect package contents.
3. Create a Publish Handoff when the package is ready and the action is available.
4. Open diagnostics/manifest data only when needed.

Export Packages are inspectable containers. They do not publish externally.

## Publish Handoff

Use this surface to inspect manual publish handoff artifacts.

Expected operator flow:

1. Review target platform, package id, readiness, and status.
2. Inspect payload content intended for manual downstream work.
3. Confirm no secrets, cookies, credentials, or private local paths appear in payloads.
4. Use the handoff externally as a manual artifact.

Publish Handoff records do not call platform APIs and do not auto-publish.

## Empty, loading, and error states

All workflow pages should explain state in operator language:

- Loading: what is being loaded.
- Empty: why no records are visible and what to try next.
- Error: what failed and whether retry is available.

Avoid raw technical dumps as the first thing the operator sees. Diagnostics should stay available in collapsed sections.

## Safety expectations

- Never imply that Publish Handoff auto-publishes.
- Never hide failed or skipped work.
- Never log or display secrets as normal payload fields.
- Use honest labels such as `Pending`, `Not packaged`, `No handoff`, or `Not prepared yet` when downstream artifacts do not exist.

## Verification note

The implemented guide expectations are covered by focused source tests and route checks:

- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/review-board.test.ts`
- `apps/web/src/test/reup-queue.test.ts`
- `apps/web/src/test/ops-console-design-system.test.ts`
- `apps/web/src/test/route-nav.test.ts`
