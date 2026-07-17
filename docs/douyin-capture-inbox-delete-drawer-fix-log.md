# Douyin Capture Inbox Delete / Drawer Fix Log

## Objective

Hard-fix `/ops/extensions/douyin/capture-inbox` for two operator-critical issues:

1. Delete state and counts must stay truthful after single or bulk deletion.
2. Details drawer actions must reliably open, switch, close, and handle deleted active items.

## Scope

Expected touched areas:

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- Documentation in `docs/`

Backend changes are not planned unless the frontend cannot consume authoritative delete responses. Current API delete response already returns affected deleted ids and an updated session aggregate.

## Audit Findings

### Delete / sync count flow

Current source of truth is split between:

- `selectedSession.items` for the active grid, filters, selected item derivation, and summary cards.
- `sessions` for the session sidebar aggregate rows.
- `selectedItemIds` for batch state.
- `focusedItemId` plus `detailDrawerOpen` for detail state.

The delete action currently does a hybrid optimistic patch plus `loadSessions(selectedSession.id)`. The weak points are:

- `applyDeletedItems` locally decrements only `captured_item_count` in the session sidebar. It does not patch ready, duplicate, failed, promoted, or skipped counts, so the sidebar can remain stale between optimistic delete and refetch.
- `applyDeletedItems` recomputes only part of `selectedSession.reconciliation`, so active session aggregate can be incomplete or stale before refetch completes.
- `loadSession` silently replaces a removed focused item with the first remaining item and keeps the drawer open if any item remains. After deleting the active drawer item, the operator may see a different item without explicitly opening it.
- `runAction` closes over `selectedSession.id` after async mutation. If state changes while the request is in flight, refresh should still target the action session id captured before the request.

### Details drawer interaction flow

Current drawer state is `focusedItemId` plus `detailDrawerOpen`.

Findings:

- The drawer item is derived from `focusedItemId`, but `focusedItemId` is also mutated by selection helpers such as checkbox toggling. This creates ambiguous states where selecting an item changes the focused row without opening the drawer.
- `toggleItem` sets `focusedItemId` but does not open the drawer. That can leave a visually focused card while the drawer remains closed.
- `openItemDetails` sets both id and open state, which is the right direction, but there is no guard that the target id still exists in the active session.
- The drawer remains mounted in a closed state with content opacity reduced; on desktop this is acceptable as a safe detail panel, but the open state must be controlled by a canonical open handler to avoid dead buttons.
- If the active item is deleted, the current cleanup may set focus to `null`, then `loadSession` may choose the first item and keep the drawer open depending on timing. This can look like the wrong item opened after delete.

## Fix Strategy

1. Rename the drawer item source concept to a canonical active item id at the component level.
2. Use one open handler for `Details`, `Open details drawer`, card media click, and view-more click.
3. Keep checkbox selection separate from drawer activation.
4. Patch active session and sidebar counts from a shared derived summary helper during optimistic delete.
5. Capture the action session id before network requests and refresh that exact session after mutation.
6. On delete, remove stale selected ids and close the drawer if the active item was deleted.
7. On authoritative reload, preserve active drawer only if the active item still exists; otherwise close safely.

## Planned Verification

- Web typecheck.
- Capture Inbox source test.
- API tests only if backend files are changed.

## Final Verification

Completed:

- `npm run typecheck --workspace apps/web`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`

Backend code was audited but not changed. API verification was not rerun because the existing delete response already returns authoritative affected ids plus the updated session aggregate.

## Implemented Results

- Replaced ambiguous drawer focus state with canonical active item identity in the Capture Inbox page.
- Kept checkbox selection independent from drawer activation, so selecting rows no longer changes the active drawer item.
- Routed card media click, `Open details drawer`, `View more in details`, and contextual `Details` through the same guarded drawer opener.
- Added explicit close behavior that clears both open state and active item identity.
- Added optimistic delete cleanup that removes deleted ids from active session items, selected ids, and active drawer state before refetch.
- Added shared item-derived count patching for active session aggregates, reconciliation counts, and sidebar session rows.
- Captured the action session id before async mutation so post-action refresh targets the session that was actually mutated.
- Reconciled active drawer state after authoritative session reload without stale active-item closures or fallback-to-first-item behavior.
