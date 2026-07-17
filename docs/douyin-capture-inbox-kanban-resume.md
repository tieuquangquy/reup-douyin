# Douyin Capture Inbox Kanban Resume

## Current Objective

Capture Inbox is being refactored into the final Kanban Moderation Board UX. This is now the primary layout and supersedes table-first, card-grid-first, and 3-pane-first approaches.

## Files Expected To Change

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-capture-inbox-kanban-log.md`
- `docs/douyin-capture-inbox-kanban-resume.md`
- `docs/douyin-capture-inbox-kanban-architecture.md`
- `docs/douyin-capture-inbox-kanban-user-guide.md`

## Implemented Baseline

The page now renders the final Kanban Moderation Board workspace:

- compact header with high-priority actions
- horizontal Session Ribbon
- clickable KPI strip
- compact board controls toolbar
- multi-column Kanban Moderation Board
- compact moderation cards
- bottom Inspector Sheet
- bottom batch action bar when items are selected

The previous 3-pane-first baseline has been replaced as the primary Capture Inbox experience.

## Reusable Existing Behavior

- `fetchCaptureInboxSessions`
- `fetchCaptureInboxSession`
- `deleteCaptureInboxSession`
- `runCaptureInboxAction`
- selected item id management
- active item id management
- session delete flow
- item delete state patching
- summary derivation
- contextual item action derivation
- thumbnail resolver
- metadata helpers
- compact text expansion

## Required Kanban Model

The final page structure must be:

1. compact top header
2. horizontal Session Ribbon
3. clickable KPI strip
4. compact filter toolbar
5. multi-column Kanban board
6. compact moderation cards
7. bottom Inspector Sheet
8. selection and column/batch actions

## Non-Goals

- No crawler changes.
- No video processing changes.
- No new workflow architecture.
- No unrelated page redesign.
- No new dependencies unless strictly required.
- No backend changes unless minimally required for data truthfulness or action support.

## Verification

Completed verification:

1. `npx tsx apps/web/src/test/capture-inbox.test.ts` passed.
2. `npm run typecheck --workspace apps/web` passed.

API tests were not required because no API files changed.

## Final Notes

- No new dependencies were added.
- No backend changes were required.
- Thumbnail behavior remains truthful and uses existing deterministic thumbnail candidate resolution.
- Table-first, card-grid-first, and 3-pane-first layouts are not used as the primary Capture Inbox experience.
