# Douyin Capture Inbox Media-first Triage Studio Log

## Decision

Capture Inbox at `/ops/extensions/douyin/capture-inbox` is moving to a Media-first Triage Studio. This is the fixed primary UX direction for Capture Inbox.

The implementation must not revert to card-grid-first, table-first, Kanban-first, or 3-pane-first primary layouts.

## Scope

### Touched areas

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- Media-first Capture Inbox docs under `docs/`

### Expected non-goals

- No crawler implementation.
- No video processing implementation.
- No scoring or filtering architecture changes.
- No database schema changes.
- No queue implementation changes.
- No unrelated page redesign.
- No new primary layout proposals.

## Audit Findings

### Current state before implementation

The current Capture Inbox implementation is Kanban-oriented from the previous iteration. It includes Kanban data structures, board copy, column rendering, moderation cards, and tests that assert Kanban behavior.

Kanban artifacts to remove as the primary experience:

- `BoardColumnKey`
- `BoardColumn`
- `boardColumns`
- `buildBoardColumns`
- `KanbanBoard`
- `KanbanColumn`
- `ModerationCard` as a Kanban-era component name and structure
- `capture-inbox-kanban-*` CSS classes
- Copy such as `Moderation Board`, `Workflow columns`, and `Board controls`

### Reusable logic

The current page has reusable behavior that should be retained:

- Session loading and active session selection.
- Session delete with active session fallback.
- Item delete with selected item and inspector synchronization.
- Promote, retry enrichment, retry preview, and exclude action wiring.
- Batch action state and selected item handling.
- Summary derivation from session items.
- Truthful thumbnail resolver using captured payload fields and image-like URL detection.
- Bottom inspector data sections.
- Long text disclosure through `CompactText`.

### API impact

No backend change is expected for this refactor. Existing API calls already support sessions, session detail, session delete, item actions, item delete, promotion, retry, exclusion, summaries, and thumbnail metadata. API work should only happen if implementation proves a minimal missing field or detail payload gap.

## Required UX Structure

1. Compact Header
2. Session Ribbon
3. Status Strip
4. Flat Filter Toolbar
5. Media-first Tile Gallery
6. Bottom Inspector Sheet
7. Operator-first actions and batch action bar

## Implementation Notes

- Header must use title `Capture Inbox` and concise subtitle `Review captured Douyin items before sending them forward`.
- Status Strip must use compact metric pills for Captured, Ready, Duplicates, Needs action, Failed, and Promoted.
- Filter toolbar must include search, status/session filters, sort, and toggles:
  - Only actionable
  - Only with thumbnail
  - Hide duplicates
- The gallery must be thumbnail-first, compact, visual, and responsive.
- The inspector must remain a bottom secondary detail surface, not a right drawer as the primary desktop pattern.
- Empty and low-data states must be operator-friendly and avoid debug/raw-first presentation.

## Progress

- Read `AGENTS.md`.
- Audited current Capture Inbox page, styles, tests, API client, and related boundaries.
- Created this docs-first implementation log before code changes.
- Replaced the Kanban-oriented Capture Inbox primary workspace with the Media-first Triage Studio.
- Added the compact Status Strip, flat Studio filter toolbar, required toggles, media tile gallery, and media tile components.
- Preserved existing session loading, session delete, item action, item delete, batch action, thumbnail resolver, and bottom Inspector Sheet behavior.
- Updated Capture Inbox source tests to assert Media-first behavior and reject Kanban/table/card-grid/3-pane primary-layout artifacts.

## Verification

Completed from the repository root:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

Both commands passed.

Verified guarantees:

- The primary item workspace is `MediaTileGallery`, not Kanban columns, table rows, card-grid-first UI, or a 3-pane layout.
- Status metrics are compact status pills, not dashboard cards.
- Toolbar toggles for `Only actionable`, `Only with thumbnail`, and `Hide duplicates` are client-side filters only.
- Session delete and item delete keep active session, gallery, selected items, active inspector item, and sheet state synchronized through the preserved state handlers.
- Thumbnail rendering remains truthful and uses existing captured URL resolution with a `No thumbnail` fallback.
