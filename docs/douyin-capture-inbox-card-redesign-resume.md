# Douyin Capture Inbox Card Redesign Resume

## Verification

Passed: `npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/capture-inbox.test.ts`.

## Current status

The Capture Inbox card redesign is in progress. Audit has been completed and docs were created before code implementation, per repository working rules.

## Completed

- Reviewed `AGENTS.md` before editing.
- Audited Capture Inbox route, component, web type, API client, API schema, backend route, backend model, backend service, CSS support, and focused tests.
- Created this resume document before implementation.
- Created the redesign log, architecture, and user guide documents before implementation.

## Key audit findings

### Existing route and layout

- Route: `apps/web/src/app/ops/extensions/douyin/capture-inbox/page.tsx`
- Main component: `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- The route already renders `CaptureInboxPage` directly.
- The component already uses the shared Ops Console shell.
- No duplicate shell was found.

### Existing UI limitations

- The item workspace is a stacked text list, not a video-first card grid.
- Current cards are generic `OpsItemCard` cards.
- Details are shown in a side column but not as an explicit drawer/modal interaction.
- Thumbnail fallback is weak and text-only.
- The UI has contextual promote/retry/exclude/source/detail actions but no delete action.
- The bulk bar has promote/retry/exclude but no delete selected action.

### Existing thumbnail support

Fields already exist across web/API/model:

- `thumbnail_url`
- `preview_url`
- `preview_ready`
- `media_ready`

Backend extraction currently supports `thumbnail_url` and `cover_url`. `poster_url` is not included yet.

### Existing delete support

No item-level staged delete API exists.

Current soft action is `exclude`, which changes status to `EXCLUDED` for non-promoted staged rows.

A minimal delete action is required to satisfy the requested explicit staged item deletion workflow.

## Planned touched files

Expected implementation files:

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/src/services/capture_inbox_service.py`

Docs to update after verification:

- `docs/douyin-capture-inbox-card-redesign-log.md`
- `docs/douyin-capture-inbox-card-redesign-resume.md`
- `docs/douyin-capture-inbox-card-redesign-architecture.md`
- `docs/douyin-capture-inbox-card-redesign-user-guide.md`

## Next steps

1. Refactor `CaptureInboxPage` card rendering into a visual staging grid.
2. Add thumbnail fallback helper and missing-thumbnail placeholder.
3. Add drawer-like detail panel open/close behavior.
4. Add per-item delete action and confirmation state.
5. Add bulk delete selected action and confirmation state.
6. Add minimal backend delete action contract/service route.
7. Update tests.
8. Run `npm run typecheck --workspace apps/web` and focused tests.
9. Update docs with verification results.

## Resume notes

Keep the implementation scoped. Do not add crawler, processing, scoring, queue, publishing, or unrelated Review Board changes.
