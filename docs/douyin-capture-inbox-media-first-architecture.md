# Douyin Capture Inbox Media-first Triage Studio Architecture

## Purpose

The Capture Inbox page is the operator's local-first staging surface for Douyin extension captures. The Media-first Triage Studio optimizes this page for fast visual review before items are promoted to the Review Board.

The design keeps the existing workflow semantics while changing the primary interaction surface from Kanban moderation columns to a compact, thumbnail-led triage studio.

## Final UX Model

The fixed page model is:

1. Compact Header
2. Session Ribbon
3. Status Strip
4. Flat Filter Toolbar
5. Media-first Tile Gallery
6. Bottom Inspector Sheet
7. Batch Action Bar when selected items exist

No alternate primary layout should be introduced for this page.

## Boundaries

### `apps/web`

Owns this refactor:

- React component layout.
- Local UI state for filters, toggles, selection, and inspector open state.
- API calls through existing API client helpers.
- Media-first CSS.
- Focused source tests.

### `apps/api`

No expected change. Existing routes already provide:

- Session list.
- Session detail.
- Session delete.
- Item action endpoint for promote, retry, exclude, and delete.
- Captured item detail fields and metadata.

Only minimal API changes are allowed if implementation proves a required thumbnail or detail field is not exposed.

### `apps/worker`

No change.

### `packages/shared` and `packages/config`

No change.

## Data Flow

1. The page loads capture sessions with `fetchCaptureInboxSessions`.
2. The selected session is loaded with `fetchCaptureInboxSession`.
3. The Session Ribbon selects or deletes sessions.
4. Status Strip and filter toolbar derive visible items from the selected session in memory.
5. The tile gallery renders visible items and uses truthful thumbnail mapping.
6. Tile selection drives batch actions.
7. Tile details open the bottom Inspector Sheet.
8. Actions call `runCaptureInboxAction` and reconcile local session state from the response.
9. Item delete and session delete prune selected IDs and close or reset the inspector when the active record disappears.

## State Model

Preserve current durable UI state concepts:

- `sessions`
- `totalCount`
- `selectedSessionId`
- `selectedSession`
- `statusFilter`
- `operatorFilter`
- `searchQuery`
- `sortMode`
- `selectedItemIds`
- `activeItemId`
- `loading`
- `working`
- `error`
- `notice`
- `rawDetails`
- `sourceUrls`
- `inspectorSheetOpen`

Add minimal filter toolbar toggle state:

- `onlyActionable`
- `onlyWithThumbnail`
- `hideDuplicates`

These toggles are pure client-side filters and must not change workflow semantics.

## Media-first Gallery Design

The gallery is the main workspace. It should:

- Use compact media tiles.
- Give thumbnails visual priority.
- Use status badges and concise metadata chips.
- Show short source/title/caption previews without long text walls.
- Provide primary operator actions from the tile.
- Open the bottom inspector for deeper details.
- Use a responsive 2 to 3 column layout on wide screens.
- Avoid Kanban columns, raw tables, and dense debug lists as the primary view.

## Bottom Inspector Sheet

The inspector remains a secondary detail surface. It should:

- Sit below the gallery in normal desktop flow.
- Use bottom-sheet behavior on small screens.
- Keep the gallery as the primary context above it.
- Provide structured sections:
  - Overview
  - Source
  - Metadata
  - Outputs
  - Diagnostics
  - Raw details
- Use long text disclosure for captions, descriptions, and raw text.

## Action Hierarchy

Primary page actions:

- Refresh
- Promote ready
- Open Review Board

Session actions:

- Open session
- Delete session

Tile actions:

- Details
- Promote when ready
- Retry enrichment when needed
- Retry preview when preview is missing
- Exclude
- Delete

Batch actions:

- Promote selected ready items
- Retry selected items
- Exclude selected items
- Delete selected items
- Clear selection

## State Correctness Requirements

Session delete must synchronize:

- Active session.
- Session Ribbon.
- Gallery.
- Status Strip.
- Selected item IDs.
- Active inspector item.
- Inspector open state.

Item delete must synchronize:

- Selected session items.
- Session summary counts.
- Session list counts.
- Visible gallery.
- Selected item IDs.
- Active inspector item.
- Inspector open state.

Action responses must preserve existing workflow state transitions and local reconciliation behavior.

## Thumbnail Truthfulness

The frontend may only show thumbnails sourced from captured item fields or nested payload fields that pass the existing image-like URL checks. No fake or generated thumbnails should be introduced.

If no thumbnail is available, the tile should show a truthful placeholder such as `No thumbnail` with a small preview-readiness label.

## Testing Strategy

Focused tests verify source-level guarantees:

- Media-first Studio structure exists.
- Status Strip replaces KPI/Kanban terminology.
- Flat toolbar includes the required toggles.
- Tile Gallery replaces the Kanban board.
- Bottom Inspector Sheet remains present.
- Session delete and item delete sync logic remains present.
- Thumbnail placeholder is truthful.
- Kanban-first primary artifacts are removed from the page and tests.

Verification completed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

Both commands passed.

## Risks

- Over-reusing generic ops components can make the page feel too admin-heavy. Mitigation: add Capture Inbox-specific media studio classes and compact styling.
- Removing Kanban components while preserving action behavior may accidentally break batch state. Mitigation: keep existing action functions and state sync paths.
- Thumbnail payload variability may cause empty thumbnails. Mitigation: keep the existing deterministic resolver and truthful fallback.
