# Douyin Capture Inbox Kanban Architecture

## Decision

The Capture Inbox primary UX is a Kanban Moderation Board. This is the final chosen model for triaging captured Douyin content before it is promoted to downstream review workflows.

This model replaces earlier table-first, card-grid-first, and 3-pane-first layouts as the primary operator experience.

## Why Kanban Is Primary

Capture Inbox is not a raw record browser. It is an operator triage surface where the most important question is: what work is ready, blocked, duplicated, failed, or already promoted?

A Kanban board makes that state visible without requiring the operator to interpret a table or scan a mixed list. It preserves local-first simplicity while keeping clean boundaries for future SaaS-ready state grouping, distributed workers, and multi-operator ownership.

## Page Structure

### 1. Compact Header

The top header identifies the page and keeps only high-priority actions, such as refresh. It should not become a large form or debug dashboard.

### 2. Session Ribbon

The Session Ribbon is a horizontal session selector near the top of the page. It shows compact session chips/cards with:

- session status
- short session label
- capture time
- captured count
- ready count
- duplicate count
- failed count
- active session state
- overflow menu
- session delete action in the menu

The ribbon replaces the prior left Session Rail. It keeps session selection visible while giving the board full horizontal working space.

### 3. KPI Strip

The KPI strip summarizes the active session and doubles as a fast filter surface. Metrics include:

- captured items
- ready items
- duplicates
- needs-action items
- failed items
- promoted items

Clicking a KPI applies the associated board filter. KPIs are compact and must not become verbose diagnostics.

### 4. Filter Toolbar

The filter toolbar controls the board view. It includes:

- text search
- session status filter
- sort mode
- workflow filter
- select visible
- clear filters

Optional toggles may be added only when supported truthfully by available data, such as thumbnail presence or actionable-only filtering. Unsupported filters must not be faked.

### 5. Kanban Board Column Model

The board groups visible items by operator workflow state. Required columns are:

- Ready
- Needs action
- Duplicates
- Failed
- Promoted

A compact Excluded / Other column may appear when the active filtered data contains such items.

Each column has:

- title
- count
- short operational description
- state-aware column action where appropriate
- empty state guidance

Column actions are wrappers over existing explicit item actions. They must not introduce hidden workflow semantics.

### 6. Compact Moderation Card Model

Each moderation card represents one captured item and shows:

- selection checkbox
- thumbnail or truthful placeholder
- status badge
- title/caption snippet
- source/video identifier
- small metadata chips
- next action label
- compact actions
- detail open action

Cards should be short and scannable. Long captions, transcript-like text, raw payloads, diagnostics, and metadata dumps belong in the Inspector Sheet, not the card.

### 7. Bottom Inspector Sheet Model

The Inspector Sheet opens from the lower page region and preserves board context. It replaces the right-side Inspector Drawer as the primary desktop pattern.

The sheet contains:

- selected item status and title
- caption and long text with show more/show less behavior
- overview metadata
- source references
- metadata/readiness
- downstream artifact info
- diagnostics
- raw details
- latest action raw details/source URLs when available

The sheet must close explicitly and must not clear board filters or selection unexpectedly.

### 8. Delete / Promote / Retry / Batch Interaction Model

All actions remain explicit API calls through the existing Capture Inbox action endpoint.

- Promote applies only to ready/enriched items.
- Retry applies to retryable needs-action/failed states.
- Exclude applies to non-promoted items.
- Delete applies to non-promoted staged items and requires confirmation.
- Session delete remains in the Session Ribbon overflow menu and requires confirmation.
- Batch actions operate on selected eligible items only.
- Column actions operate on eligible items in that column only.

State must remain synchronized after actions:

- deleted items disappear locally and counts are patched
- active inspector item closes if deleted
- selected ids are pruned after deletion
- session counts refresh after API action completion
- active session remains stable when possible

### 9. Responsive Fallback Behavior

Desktop uses the horizontal Session Ribbon and horizontally tolerant Kanban board.

Narrow screens should:

- keep Session Ribbon horizontally scrollable
- stack toolbar controls
- allow board columns to scroll horizontally or collapse into single-column sections
- present Inspector Sheet as a modal-like bottom sheet rather than a right drawer

### 10. Boundaries

The web app owns the UI and API calls only. It must not perform crawling, video processing, scoring, queue orchestration, or direct database writes.

The API already exposes session list/detail, session delete, item list, and Capture Inbox actions. No API changes were required for this Kanban refactor.

## Implemented Files

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-capture-inbox-kanban-log.md`
- `docs/douyin-capture-inbox-kanban-resume.md`
- `docs/douyin-capture-inbox-kanban-architecture.md`
- `docs/douyin-capture-inbox-kanban-user-guide.md`

## Verification Results

- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed.
- `npm run typecheck --workspace apps/web` passed.

## Testing Expectations

Tests should assert that the final primary model is Kanban, including:

- Session Ribbon exists
- KPI strip exists
- Kanban board exists
- board columns exist
- compact moderation cards exist
- bottom Inspector Sheet exists
- 3-pane workspace assertions are removed
- right-side drawer naming is not primary
- delete/promote/retry/batch wiring remains present
- thumbnail placeholder behavior remains truthful
