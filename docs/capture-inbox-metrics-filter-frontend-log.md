# Capture Inbox Metrics + Advanced Filter Frontend Log

## Scope Lock
- Implement only frontend changes for Capture Inbox metrics visibility and advanced filter panel behavior in [`apps/web`](apps/web).
- Keep backend as filtering source-of-truth via [`queryCaptureInboxItems()`](apps/web/src/lib/api.ts:357).
- Keep inspector detail-heavy content in [`RightInspector`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:612), not on cards.
- No backend behavior changes in this task.

## Required Audit Findings

### 1) Capture Inbox current filtering model
- Primary UI is [`CaptureInboxPage()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:69).
- Existing visible list comes from local `useMemo` in [`visibleItems`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:140).
- Existing controls are local state filters in [`StudioFilterToolbar()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:441), plus status chips in [`StatusStrip()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:422).
- Existing `matchesFilter` logic is local in [`matchesFilter()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:847).

### 2) Metrics visibility on cards
- Card rendering is in [`MediaTile()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:565).
- Compact metadata helper already exists in [`compactQuickMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:973).
- Required metric fields (`view_count`, `like_count`, `comment_count`, `share_count`) are available in [`CapturedItem`](apps/web/src/types/capture-inbox.ts:44).

### 3) Backend query wiring already available
- Web API contract exists in [`queryCaptureInboxItems()`](apps/web/src/lib/api.ts:357).
- Payload model exists in [`CaptureInboxItemQueryRequest`](apps/web/src/types/capture-inbox.ts:178).
- Advanced filter fields exist in [`CaptureInboxAdvancedFilter`](apps/web/src/types/capture-inbox.ts:155).

### 4) `/intake` filter semantics to mirror
- Intake form source is [`IntakePage`](apps/web/src/components/intake/IntakePage.tsx:479).
- Filter groups and fields are in [`intake-filter-groups`](apps/web/src/components/intake/IntakePage.tsx:627), including:
  - time range: from/to date
  - metric ranges: views/likes/comments/shares
  - engagement range
  - processing fit: duration, speech, text density
  - exclusion flags: heavy watermark, high complexity, high copyright risk
- Intake value normalization flow is visible in [`buildIntakeDiscoverRequest` usage](apps/web/src/components/intake/IntakePage.tsx:267).

## Reuse Decision
- Capture Inbox advanced panel will mirror intake field semantics and naming from [`CaptureInboxAdvancedFilter`](apps/web/src/types/capture-inbox.ts:155), while preserving inbox-specific controls (session/status/search/select-visible) in [`StudioFilterToolbar()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:441).

## Implemented Frontend Wiring
1. Preserved existing session ribbon/status strip and right inspector in [`CaptureInboxPage()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:115).
2. Added compact metric row in [`MediaTile()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:770) using [`compactMetricMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1189) and [`compactMetricValue()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1198).
3. Added collapsible advanced filter panel in [`AdvancedFilterPanel()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:591).
4. Added draft/applied/query state and handlers in [`CaptureInboxPage()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:115), including [`applyAdvancedFilters()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:241) and [`resetAdvancedFilters()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:263).
5. Wired Apply to [`queryCaptureInboxItems()`](apps/web/src/lib/api.ts:357) with session-scoped payload mapping in [`buildAdvancedFilterPayload()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1293).
6. Preserved fast browsing/status chips/right-inspector boundaries while query mode is active.
7. Added focused assertions in [`capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts:123) for metrics strip, advanced panel state, payload mapping, and API query wiring.

## Verification Evidence
- Targeted test pass:
  - Command: `npx -w apps/web tsx src/test/capture-inbox.test.ts`
  - Result: `capture inbox Media-first Triage Studio... tests passed`
- Typecheck pass:
  - Command: `npm run -w apps/web typecheck`
  - Result: `tsc --noEmit -p tsconfig.typecheck.json` exit code `0`

## Changed Files
- [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx)
- [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts)
- [`docs/capture-inbox-metrics-filter-frontend-log.md`](docs/capture-inbox-metrics-filter-frontend-log.md)
- [`docs/capture-inbox-metrics-filter-frontend-resume.md`](docs/capture-inbox-metrics-filter-frontend-resume.md)

## Non-goals
- No backend filtering logic implementation.
- No change to capture ingestion or promotion flows.
- No redesign of unrelated pages.
