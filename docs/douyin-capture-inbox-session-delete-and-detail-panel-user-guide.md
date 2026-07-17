# Douyin Capture Inbox Session Delete / Detail Panel User Guide

## What This Change Covers

This change improves `/ops/extensions/douyin/capture-inbox` in two focused places:

1. Operators can delete an entire Capture Inbox session from the session sidebar.
2. The item detail drawer becomes more compact for long text, with explicit expansion controls.

## Deleting a Capture Session

Expected workflow:

1. Find the session in `Capture sessions`.
2. Use the row action `Delete session`.
3. Confirm the prompt titled `Delete capture session?`.
4. The session disappears from the sidebar after deletion succeeds.

When the deleted session was active:

- The captured item grid changes to a safe fallback session if one exists.
- If no sessions remain, the page shows the normal empty state.
- Summary cards are recalculated from the active fallback session, or reset to empty counts.
- Selected item ids are cleared.
- The detail drawer is closed and cleared.
- Latest raw action details/source URLs are cleared.

Deleting a Capture Inbox session removes the staged session and its staged captured items from Capture Inbox. It does not delete already-promoted canonical review records.

## Compact Detail Panel Behavior

The item detail drawer is organized for quick scanning:

1. Header with status and timing metadata.
2. Compact title and caption previews.
3. Operator summary for next action, promotion, duplicate state, and item identity.
4. Captured text disclosures for description, transcript, notes, and raw text when present.
5. Source/media links and readiness status.
6. Diagnostics/raw details collapsed at the bottom.

Long text defaults to a compact preview. Use:

- `Show more` to expand the full text.
- `Show less` to return to the compact preview.

Switching to another item resets expanded long-text controls so the next item starts compact.

## Verification

The implementation was verified with:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`

## Limitations

This change does not redesign the full Capture Inbox page, change thumbnail/media behavior, change promotion workflow, add crawler behavior, or change publishing behavior.
