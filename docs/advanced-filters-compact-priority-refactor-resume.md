# Advanced Filters Compact-Priority Refactor Resume

## Task
Refactor only the Capture Inbox Advanced filters panel UI/UX to be shorter, lighter, and operator-first by moving Exclusions out of the main visible body while preserving filter semantics.

## Scope Lock
- Touch only Advanced filters UI in [`apps/web`](apps/web).
- No backend or filter-semantic changes.
- No broad Capture Inbox redesign.
- Exclusions logic must remain functional.

## Current Status
- Audit complete.
- Docs-first artifacts created.
- UI refactor completed and verified.

## Audit Summary
- Current panel structure in [`AdvancedFilterPanel()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:634).
- Current visual weight largely from grouped cards and equal-weight sections in [`.capture-inbox-advanced-group`](apps/web/src/app/globals.css:3141).
- Exclusions currently consume full visible section in [`.capture-inbox-advanced-exclusions`](apps/web/src/app/globals.css:3181).
- Existing tests already assert advanced panel structure in [`capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts:140).

## Implementation Outcome (Strict Order Completed)
1. Refactored hierarchy so primary groups dominate (`Time`, `Performance`, `Processing fit`) in [`AdvancedFilterPanel()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:686).
2. Removed Exclusions from main visible body by deleting the full `Exclusions` primary section.
3. Moved Exclusions into compact secondary placement using [`capture-inbox-advanced-risk-disclosure`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:757), collapsed by default.
4. Preserved and emphasized active summary chips (including exclusions) via [`advancedFilterSummaryItems()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:115).
5. Tightened spacing/layout for material height reduction in [`globals.css`](apps/web/src/app/globals.css:3064).
6. Updated focused panel tests in [`capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts:144).
7. Verification passed:
   - [`npx -w apps/web tsx src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts)
   - [`npm run typecheck --workspace apps/web`](package.json:11)
8. Docs updated with final evidence.

## Non-goals
- No backend query/payload change.
- No advanced filter semantics change.
- No extraction/data pipeline changes.
- No redesign outside Advanced filters panel.
