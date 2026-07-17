# Douyin Capture Inbox Card Redesign Log

## Purpose

Refactor the Capture Inbox at `/ops/extensions/douyin/capture-inbox` into an operator-friendly visual staging workspace without changing the core capture, enrichment, promotion, or downstream Review Board workflow.

The current workflow is functional, but the screen is too text-heavy for fast operator review. Operators need to scan captured videos visually, understand state at a glance, open dense details only when needed, and perform promote, retry, exclude, and delete actions safely.

## Audit completed before implementation

### Repository rules reviewed

`AGENTS.md` was reviewed before editing. Relevant constraints:

- `apps/web` owns the Next.js and TypeScript UI, review screens, operator workflows, and API calls.
- `apps/web` must not perform crawling, video processing, scoring, queue orchestration, or direct database writes.
- `apps/api` owns HTTP contracts, validation, persistence coordination, and stable backend actions.
- Docs must be updated when architecture, boundaries, workflows, or environment requirements change.
- Changes must stay scoped and must not implement future product phases early.

### Current route and shell

The route `apps/web/src/app/ops/extensions/douyin/capture-inbox/page.tsx` directly renders `CaptureInboxPage`. No duplicate shell issue was found.

The current `CaptureInboxPage` already uses the shared Ops Console shell and primitives:

- `OpsConsoleShell`
- `PageShell`
- `OpsConsolePage`
- `OpsContentGrid`
- `OpsMainColumn`
- `OpsSideColumn`
- `OpsSummaryCards`
- `OpsFilterBar`
- `OpsItemCard`
- `OpsDetailPanel`
- `OpsBatchActionBar`

### Current UX issues found

1. The main item area is a stacked text list instead of a visual staging grid.
2. Cards use generic `OpsItemCard` rendering and are still dominated by text metadata.
3. Thumbnail rendering only checks `item.thumbnail_url` in the web UI.
4. Thumbnail fallback is a plain `Preview pending` label rather than a clear visual placeholder.
5. Dense item details are always placed in the right column through `OpsDetailPanel`, not an explicit open/close drawer-style surface.
6. Per-item actions are contextual but do not include delete.
7. Bulk actions exist but only include promote, retry, and exclude.
8. The backend action contract does not support delete.

### Thumbnail and preview fields found

The web type `CapturedItem` already includes:

- `thumbnail_url`
- `preview_url`
- `preview_ready`
- `media_ready`

The API schema `CapturedItemResponse` exposes the same fields.

The backend model `CapturedItem` stores the same fields.

The backend build path currently extracts thumbnails from raw extension data with:

```py
thumbnail_url = _first_string(raw_item, "thumbnail_url", "cover_url")
```

It then sets:

```py
preview_url=thumbnail_url or source_url
```

Audit finding: `poster_url` is not currently included as a thumbnail fallback in backend extraction.

### Delete capability found

No staged item delete action exists today.

Current soft-removal action is `exclude`, implemented by setting item status to `EXCLUDED` for non-promoted items.

The model relationship has `cascade="all, delete-orphan"` from capture session to captured items, but that is not an item-level delete API.

Safe staged item deletion therefore requires a minimal backend/API addition if delete is included in the UI.

## Implementation plan

### UI changes in `apps/web`

- Keep the existing route and shared Ops Console shell.
- Replace the stacked item list with a visual card grid/list staging area.
- Add a purpose-built capture card renderer with:
  - Large 16:9 thumbnail area.
  - Clear placeholder for missing thumbnails.
  - Status badge and next-action copy.
  - Compact caption/source/metric metadata.
  - Selection checkbox.
  - Contextual actions.
- Convert details into a drawer-like right-side panel with explicit open/close semantics.
- Preserve source URLs, raw details, diagnostics, metadata, output artifact references, and Review Board navigation.
- Extend the batch action bar to include delete selected with explicit confirmation.

### API/backend changes in `apps/api`

- Extend Capture Inbox action contract with a delete action for staged items.
- Add a service method for deleting selected captured staged items.
- Require explicit item IDs for deletion.
- Guard promoted items so downstream Review Board / candidate references are not silently removed.
- Reconcile capture session counts after deletion.
- Return an operator-facing action response message.

### Tests

Update focused source tests to assert:

- Route still renders `CaptureInboxPage`.
- Shared Ops Console shell remains in use.
- Main item area uses a visual card grid/list.
- Cards render thumbnail and a clear missing-thumbnail placeholder.
- Details are available through drawer/modal copy and open/close controls.
- Per-item delete action is present.
- Bulk delete selected action is present.
- Backend schema/route/service support delete.
- Existing promote, retry, exclude, source, raw details, and Review Board actions remain represented.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No scoring/filtering implementation changes.
- No queue implementation changes.
- No database schema migration unless strictly required.
- No auto-publish integration.
- No change to Review Board, Reup Queue, Export Package, or Publish Handoff workflows beyond preserving navigation.

## Progress log

- Audit completed.
- Mandatory docs created before implementation.
- Implemented visual card grid, thumbnail placeholder, detail drawer, per-item delete, bulk delete, backend delete action, and focused tests.
- Verification passed with `npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/capture-inbox.test.ts`.
