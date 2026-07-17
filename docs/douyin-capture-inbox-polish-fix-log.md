# Douyin Capture Inbox Polish Fix Log

## Scope

This pass hard-fixes and polishes `/ops/extensions/douyin/capture-inbox` after the card redesign. It is intentionally scoped to Capture Inbox interaction, data synchronization, thumbnail resolution, title readability, and compact operator layout.

## Non-goals

- Do not redesign unrelated pages.
- Do not rewrite the shared Ops Console styling system.
- Do not change Capture Inbox workflow semantics.
- Do not fake thumbnails when no real thumbnail or image-like preview URL exists.
- Do not introduce crawler, processing, scoring, queue, or publishing implementation.

## Audit findings

1. Stale summary count after deletion is caused by two related issues:
   - The UI `captured` summary trusts the persisted reconciliation count before the visible item list.
   - Backend deletion reconciles the session before deleted ORM items are flushed or removed from the loaded relationship.
2. Missing thumbnails are caused by narrow thumbnail lookup. The current UI only checks explicit `thumbnail_url`, top-level raw `cover_url`, and top-level raw `poster_url`.
3. The details drawer action sets React state, but the desktop drawer is always rendered inline and `open` only changes opacity. Operators do not see a meaningful open interaction.
4. Long titles and captions render directly on cards without CSS clamping or a clear full-text affordance.
5. Capture Sessions and Item Detail panel remain text-heavy from the first implementation pass.

## Planned changes

- Reconcile backend delete counts after flush and return truthful session state.
- Make UI summary derive captured count from the current item list so deletion results are immediately truthful.
- Optimistically remove deleted staged items from local state before refetch to avoid stale visible state.
- Expand thumbnail resolver across saved fields, metadata, raw payload, nested image/video/cover fields, and image-like preview URLs.
- Make the details drawer a real open/closed inspector with visible desktop and mobile behavior.
- Clamp card title/caption and use Details/View more to expose full text.
- Compact Capture Sessions into short rows with status/count chips.
- Compact Item Detail into an operator-first inspector, with diagnostics collapsed.

## Progress

- Audit completed.
- Required documentation created before implementation.
- Implemented backend delete reconciliation flush/expire, UI item-list-derived captured summary, and optimistic delete sync.
- Implemented recursive backend/frontend thumbnail resolvers with image-like URL checks.
- Implemented visible open/closed detail drawer state, clamped card title/caption, View more affordance, compact card actions, compact session rows, and compact detail hero/sections.
- Updated focused Capture Inbox source tests for delete sync, thumbnails, drawer visibility, title clamp, compact sessions, and compact details.
- Verification passed with `npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/capture-inbox.test.ts`.
