# Capture Inbox Metrics + Filter Frontend Resume

## Task
Implement Capture Inbox frontend metrics visibility plus advanced filter panel synced to `/intake` semantics, with backend query wiring and focused tests.

## Current Status
Frontend metrics + advanced filter implementation complete. Focused test and web typecheck verification complete.

## Completed
- Re-read constraints in [`AGENTS.md`](AGENTS.md:1).
- Audited Capture Inbox structure in [`CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:115).
- Confirmed existing local filter path in [`visibleItems`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:195) and [`matchesFilter()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1055).
- Audited intake filter groups/field semantics in [`IntakePage.tsx`](apps/web/src/components/intake/IntakePage.tsx:620).
- Confirmed backend query API availability via [`queryCaptureInboxItems()`](apps/web/src/lib/api.ts:357) and types in [`capture-inbox.ts`](apps/web/src/types/capture-inbox.ts:155).
- Implemented compact metrics row in [`MediaTile()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:770) using [`compactMetricMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1189).
- Implemented collapsible advanced panel in [`AdvancedFilterPanel()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:591).
- Wired Apply/Reset/query-mode in [`applyAdvancedFilters()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:241) and [`resetAdvancedFilters()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:263) with mapping in [`buildAdvancedFilterPayload()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1293).
- Preserved right-inspector boundary in [`RightInspector()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:820).
- Updated focused assertions in [`capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts:123).
- Verification completed:
  - `npx -w apps/web tsx src/test/capture-inbox.test.ts` (pass)
  - `npm run -w apps/web typecheck` (pass)

## Next Steps
1. None for this scoped frontend step; implementation and verification are complete.

## Scope Constraints
- Frontend-only implementation for this task.
- No backend contract redesign.
- No unrelated page refactor.
