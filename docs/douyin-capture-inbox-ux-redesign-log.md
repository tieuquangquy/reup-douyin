# Douyin Capture Inbox UX Redesign Log

## Scope

Redesign `/ops/extensions/douyin/capture-inbox` into a clean operator-first staging workspace. This slice is limited to `apps/web` unless a minimal API shape change becomes necessary.

## Goals

- Make Capture Inbox understandable without reading diagnostics.
- Add clickable summary cards for Captured, Ready, Duplicates, Needs enrichment, Failed, and Promoted.
- Add search, compact filter chips, and sort controls.
- Use a two-column workspace with the main item list on the left and item details on the right.
- Simplify collapsed item cards so they show only operational information and contextual actions.
- Move raw metadata, raw payloads, and diagnostics into the detail panel with diagnostics collapsed by default.
- Add a sticky batch action bar for common safe flows.
- Make session-level recommended next action obvious.

## Non-Goals

- No crawler implementation.
- No capture backend rewrite.
- No Review Board rewrite.
- No Reup Queue changes.
- No direct database writes from the web app.
- No live Douyin or paid service dependency in tests.

## Audit Notes

- The existing route is `apps/web/src/app/ops/extensions/douyin/capture-inbox/page.tsx` and renders `CaptureInboxPage`.
- Current UI already has sessions, grouped queues, selection, actions, and a detail drawer, but the layout still exposes too much technical information in the main flow.
- Existing web types already provide enough item/session fields for the redesign: status, caption, source URLs, thumbnail, duration, posted date, preview/media readiness, promotion ids, duplicate ids, metadata, enrichment, and raw payload.
- Existing API client functions are sufficient for this UI redesign: `fetchCaptureInboxSessions`, `fetchCaptureInboxSession`, and `runCaptureInboxAction`.
- No API changes are planned unless implementation reveals a missing field.

## Planned Implementation

1. Create docs before implementation.
2. Define operator state vocabulary and filter buckets.
3. Redesign `CaptureInboxPage` with header CTAs, summary cards, search/filter/sort, main list, sticky batch bar, and right-side detail panel.
4. Keep actions contextual by item state.
5. Update Capture Inbox source tests to verify the required UX affordances.
6. Run focused web tests and typecheck.

## Verification Log

- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed. The focused source check covers the clean title, header CTAs, clickable summary card vocabulary, search/filter/sort controls, contextual actions, simplified card affordances, right-side detail panel sections, collapsed diagnostics, sticky batch actions, recommended next action copy, and honest missing metadata labels.
- `npm run typecheck` passed for the web TypeScript project.
- Route/navigation source checks were not changed because the existing `/ops/extensions/douyin/capture-inbox` route remained unchanged.

## Current Status

- Audit completed.
- Documentation created before implementation.
- Operator-first state vocabulary, filters, sort modes, contextual actions, batch action behavior, and detail panel boundaries implemented.
- Capture Inbox UI redesign implemented in `apps/web` without API shape changes.
- Tests and typecheck passed.
