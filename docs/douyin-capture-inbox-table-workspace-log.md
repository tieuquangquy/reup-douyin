# Douyin Capture Inbox Table Workspace Log

## Status

Implemented and verified.

## Request

Refactor `/ops/extensions/douyin/capture-inbox` into the official table-based operator workspace. The primary layout is fixed: compact header, summary cards, filter/search toolbar, left Capture Sessions panel, center captured-items data table, right item detail drawer, and sticky batch action bar.

## Guardrails

- Keep the table workspace as the primary layout.
- Do not return to a card-grid primary layout.
- Keep changes scoped to Capture Inbox and directly related styles/tests/docs.
- Preserve existing workflow semantics: staged items are reviewed, retried, excluded, deleted, or promoted to Review Board.
- Do not add crawler, video processing, scoring, queue, publishing, or new backend architecture.
- Do not introduce new dependencies.

## Audit Findings

### Reusable

- Existing session/action state in `CaptureInboxPage.tsx` can be reused: session loading, selected session, selected rows, active item id, drawer open state, working/error/notice state, raw action details, and source URLs.
- Existing API client functions are sufficient for the table workspace: list sessions, get session, delete session, and run session actions.
- Existing delete/promote/retry/exclude behavior can be reused, including optimistic item removal and session count patching.
- Existing thumbnail resolver already prioritizes canonical thumbnail/poster/cover aliases and avoids fake thumbnails.
- Existing detail drawer content can be reused, with section names aligned to the table workspace requirement.
- Shared Ops primitives remain useful for shell, sections, summary cards, toolbar groups, detail panels, action rows, and batch action bars.

### Replace

- Replace `capture-inbox-card-grid` and `CaptureItemCard` as the primary item layout.
- Replace the two-column `OpsContentGrid` placement with a Capture Inbox-specific three-column workspace.
- Replace the large workflow context block with a compact context strip.
- Move session status filtering into the table toolbar.
- Expand the session overflow menu to include Open session and Delete session.
- Update tests that currently require card-grid/card classes.

### Blockers Removed By This Work

- The current main item view is a card grid, which does not scale for dense scanning or batch operations.
- The current side column combines sessions and drawer rather than reserving left and right workspace regions.
- The current toolbar does not include session status and select-visible controls in the same operator control row.
- Current CSS has card-specific rules and lacks table, three-column workspace, row, thumbnail-cell, and sticky table-header styles.

### Backend Support

No backend change is required for the first table refactor. Existing response fields include thumbnail URL, raw payload, metadata, status, source URLs, counts, delete actions, and session detail records. Thumbnail field mapping is already supported in backend and frontend; only frontend rendering needs to keep it truthful.

## Implementation Plan

1. Create table workspace docs first.
2. Add compact context strip.
3. Update toolbar to include search, session status, item status, sort, and select-visible.
4. Refactor session list into a compact left panel.
5. Replace item cards with a table component.
6. Keep detail drawer on the right and align section titles.
7. Keep action/state synchronization intact.
8. Update CSS and tests.
9. Run focused verification.

## Work Log

- 2026-04-27: Read `AGENTS.md`, audited current Capture Inbox implementation, shared Ops components, tests, CSS, API client, web types, backend schema, and thumbnail support.
- 2026-04-27: Created table workspace docs before implementation.
- 2026-04-27: Replaced the primary Capture Inbox card-grid workspace with a three-column table workspace in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- 2026-04-27: Added the compact workflow context strip, moved session status and select-visible controls into the toolbar, and kept clickable summary cards.
- 2026-04-27: Refactored Capture Sessions into a compact left panel with `Open session` and `Delete session` overflow actions.
- 2026-04-27: Added the captured-items data table with select, thumbnail, title/caption, status, source, metadata, next action, and row actions columns.
- 2026-04-27: Kept existing row/batch actions, session delete, staged item delete, optimistic cleanup, session count sync, and drawer state reconciliation.
- 2026-04-27: Aligned the right drawer sections to `Source / References` and `Outputs / Downstream artifacts` while preserving diagnostics and collapsed raw details.
- 2026-04-27: Added Capture Inbox-specific CSS for the context strip, three-column workspace, table rows, thumbnail cells, selected rows, clamps, sticky side regions, and responsive collapse.
- 2026-04-27: Updated `apps/web/src/test/capture-inbox.test.ts` to assert the official table workspace and reject card-grid as the primary layout.
- 2026-04-27: Verified with `npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web`.

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

## Backend Decision

No backend change was needed. Existing Capture Inbox API contracts already expose session records, item records, thumbnail fields, raw payloads, metadata, source URLs, action endpoints, session deletion, and staged item deletion. Existing backend and frontend thumbnail resolvers already support canonical and alias thumbnail fields without fabricating thumbnails.
