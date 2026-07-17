# Phase 22F-2A - Review Board Compact UX Refinement

## Summary
Phase 22F-2A refines `/selection/review-board` from the larger 22F-2 workspace into a compact, fast-review surface. The change is frontend-only and keeps the locked Review Board metadata contract intact.

## Files Audited
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/review-board.test.ts`
- `apps/web/src/lib/reviewCandidateMetadata.ts`
- `apps/web/src/types/review-board.ts`
- `apps/web/src/lib/reviewBoardState.ts`

## Compact Layout
- Header is reduced to a thin command row with title, requested subtitle, compact count summary, Refresh, and Capture Inbox link.
- Status tabs are slim segmented controls with label and count only.
- Filters are a single compact toolbar: search, status, sort, preset, More filters, Apply, Reset.
- Candidate items are dense rows with a vertical Douyin-friendly thumbnail, inline metadata, inline metrics, and compact actions.
- The right inspector remains sticky and auto-opens on the first visible candidate when candidates are available.

## Candidate Row Display Rules
- Visible score uses `candidate.reup_score` through `reviewCandidateDisplayScore(candidate)` only.
- Missing score displays `Unscored`.
- Estimated views label is `Est. Views`.
- Estimated views display prefers `estimated_views_display`, then min/max when both exist, otherwise `—`.
- Likes, comments, and shares display only real metric text/value; missing values remain `—`.
- Posted uses `posted_display` through the adapter; missing values remain `—`.
- Duration uses `duration_text` or adapter-formatted `duration_seconds`; missing values remain `—`.
- Thumbnail uses `thumbnail_url`; missing thumbnails show the clean placeholder.

## Inspector Behavior
- If visible candidates exist and no active candidate is selected, the first visible candidate is selected automatically.
- If the active candidate is filtered out or removed, the next visible candidate becomes active through the same auto-select path.
- The inspector shows score, status, caption, metadata, review status, decision status, source references, and diagnostics.

## Action Labels And Placement
- `Keep` was renamed to `Approve` anywhere it maps to `APPROVED`.
- Bulk `Keep selected` was renamed to `Approve selected`.
- `Remove` remains available only as a muted row link with explicit confirmation.
- Reject remains available but visually lower emphasis than the primary approve action.

## Deferred Items
- Reject reasons workflow.
- Bulk review reason capture.
- Approved-to-Reup-Queue handoff.
- Grid/table advanced view modes.
- Backend metadata hydration, backfill, or schema changes.
