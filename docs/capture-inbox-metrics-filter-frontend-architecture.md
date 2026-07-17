# Capture Inbox Metrics + Filter Frontend Architecture

## Problem
Capture Inbox already has compact card and local toolbar filtering, but operators need: (1) explicit on-card metric visibility for scan speed, and (2) an advanced filter panel aligned with `/intake` semantics and backed by backend query filtering.

## Existing Boundaries
- UI ownership remains in [`apps/web`](apps/web) per [`AGENTS.md`](AGENTS.md:17).
- Backend contract is already available through [`POST /capture-inbox/items/query`](apps/api/src/api/routes/capture_inbox.py:104), consumed by [`queryCaptureInboxItems()`](apps/web/src/lib/api.ts:357).
- Detailed metadata remains in [`RightInspector`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:612).

## UX Architecture

### A) Card metrics surface
- Add a compact metric strip to [`MediaTile()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:565).
- Always show four metrics in stable order: Views, Likes, Comments, Shares.
- Missing values render as `—` (not `0`) unless source value is explicitly zero.
- Keep label/value short to preserve media-first density.

### B) Advanced panel layout
- Add a collapsible panel near existing toolbar in [`CaptureInboxPage()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:325).
- Group fields to mirror intake:
  1. Time range
  2. Core metrics
  3. Audience signals
  4. Processing fit
  5. Exclusions
- Include explicit actions:
  - Apply filters
  - Reset filters
- Default state collapsed.

### C) State model
- `draftAdvancedFilter`: controlled form values as strings/enum flags.
- `appliedAdvancedFilter`: last committed payload.
- `queryLoading/queryError`: backend query lifecycle.
- Preserve existing local quick controls (search, status strip, toggles) while backend query controls the base item set for selected session.

### D) Contract mapping
- Frontend panel state maps to [`CaptureInboxAdvancedFilter`](apps/web/src/types/capture-inbox.ts:155).
- On apply, build [`CaptureInboxItemQueryRequest`](apps/web/src/types/capture-inbox.ts:178):
  - must include `capture_session_id`
  - include optional `status`, `search`, `limit`, `offset` only if actively used
  - include `advanced_filter` only with non-empty values
- Call [`queryCaptureInboxItems()`](apps/web/src/lib/api.ts:357) and replace visible dataset with response items.

### E) Status-aware browsing
- Keep high-level status chips in [`StatusStrip()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:422).
- Maintain explicit handling for requested categories: all captured, matches intake, needs enrichment, filtered out, hard rejected (if represented in current status model).

## Testing Strategy
- Extend [`capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts) with focused cases:
  - renders compact metrics row with null-safe display
  - toggles advanced panel open/closed
  - apply invokes [`queryCaptureInboxItems()`](apps/web/src/lib/api.ts:357) with mapped payload
  - reset clears draft/applied filters and restores baseline session listing
- Keep tests deterministic by mocking API layer.

## Verification Targets
- Typecheck passes in [`apps/web`](apps/web).
- Capture Inbox tests pass with new panel + metrics assertions.
- No regressions to session selection, batch actions, and right-inspector details.
