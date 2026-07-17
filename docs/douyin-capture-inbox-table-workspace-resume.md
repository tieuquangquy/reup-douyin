# Douyin Capture Inbox Table Workspace Resume

## Current Goal

Refactor `/ops/extensions/douyin/capture-inbox` into the official table-based operator workspace.

## Completed

- Read `AGENTS.md`.
- Reset task checklist for the table workspace refactor.
- Audited current Capture Inbox implementation and directly relevant shared code.
- Confirmed no backend change is required for the table workspace refactor.
- Created required docs before implementation.
- Implemented the compact context strip and preserved clickable summary cards.
- Moved session status filtering and select-visible controls into the toolbar.
- Refactored Capture Sessions into the compact left panel with overflow actions.
- Replaced the primary captured-items card grid with the official data table.
- Kept the right-side detail drawer independent from checkbox selection.
- Preserved row actions, staged item delete, session delete, batch actions, optimistic delete cleanup, and session count sync.
- Updated Capture Inbox-specific styles and focused source tests.
- Ran focused verification and web typecheck successfully.

## Relevant Files

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/components/ops-console/OpsShared.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/capture-inbox.ts`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/services/capture_inbox_service.py`

## Audit Summary

The previous page already had strong state handling and truthful data helpers, but the primary item renderer was a card grid. The layout used a main/side shared grid where sessions and details shared the side column. The implemented refactor now uses a Capture Inbox-specific three-column operator workspace: sessions on the left, the captured-items table in the center, and the detail drawer on the right.

## Reuse

- Session list loading and session detail loading.
- Session status filter state and item status filter state.
- Search and sort state.
- Selected item ids and active drawer item id as separate state.
- Promote, retry enrich, retry preview, exclude, staged item delete, and session delete actions.
- Optimistic delete cleanup and count patching.
- Thumbnail resolver and missing-thumbnail placeholder copy.
- Shared Ops summary cards, toolbar groups, action rows, detail sections, and batch action bar.

## Replaced

- `CaptureItemCard` as primary rendering.
- `capture-inbox-card-grid` as primary workspace.
- Two-column content grid for this page.
- Large workflow context block.
- Tests that required card-grid/card classes.

## Verification

Passed:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```

Output:

```text
capture inbox table workspace, action hierarchy, and polish tests passed

> typecheck
> tsc --noEmit -p tsconfig.typecheck.json
```

## Current State

The table workspace refactor is complete. No backend/API/schema changes were required because the existing contracts already support session deletion, staged item deletion, item actions, thumbnail fields, metadata, raw payloads, source URLs, and session/item reconciliation data.
