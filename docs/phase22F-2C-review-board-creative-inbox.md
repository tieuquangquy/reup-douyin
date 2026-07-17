# Phase 22F-2C - Review Board Creative Inbox

## Summary
Phase 22F-2C redesigns Review Board as a full-width Creative Review Inbox. The fixed right inspector is removed from the default workspace, and candidate details now open only when requested in a slide-over drawer.

## Capture Inbox Design Files Audited
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`

## Review Board Files Audited
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/test/review-board.test.ts`
- `apps/web/src/lib/reviewBoardState.ts`
- `apps/web/src/lib/reviewCandidateMetadata.ts`

## Creative Inbox Layout
- Compact command header keeps the page context and high-level counts light.
- Slim pipeline tabs own status filtering instead of a form-like status select.
- The queue uses full width by default so candidate rows are not squeezed.
- Candidate details are deferred to the drawer and do not reserve permanent horizontal space.

## Slide-Over Drawer Behavior
- State uses `selectedCandidateId` and `isDetailDrawerOpen`.
- Loading/refetching does not force a permanent detail panel open.
- Row clicks select/highlight only; `Inspect details` in More opens the drawer.
- Close and Escape hide the drawer while preserving the selected candidate id.
- If filters leave no visible candidates, the drawer closes and selection clears.

## Candidate Row Redesign
- Rows use a checkbox, vertical thumbnail, compact score/status/Est. Views metadata, caption, posted/duration, metrics, and source/preset line.
- Visible actions are reduced to Approve, Review, Reject, and More.
- Inspect details and Remove from board are tucked into More.
- Remove still requires explicit confirmation and states source/upstream records are not deleted.

## Status Pipeline Tabs
- Status tabs are rendered with `review-board-pipeline-strip` and `review-board-pipeline-tab`.
- Counts are computed from the visible loaded candidate set before status filtering.
- Status semantics continue to normalize candidate status, review status, and decision status.

## Command Toolbar Changes
- Toolbar keeps Search, Sort, Preset, More filters, Apply, and Reset.
- Status select was removed from the toolbar to avoid duplicating the pipeline tabs.

## Action Hierarchy
- Approve is primary.
- Review is secondary.
- Reject is danger outline.
- More is low-emphasis and contains Inspect details, Open source, and Remove from board.

## Data Contract Safeguards
- Visible score still uses `reviewCandidateDisplayScore(candidate)` from the metadata adapter.
- Missing score displays `Unscored`; visible UI does not read `candidate.score` directly.
- Estimated views remain labeled exactly `Est. Views` and use display/min-max/`—` only.
- Metrics preserve real values, real zero, and missing `—` behavior.
- Duration and posted labels use canonical adapter fields first.
- Thumbnail uses canonical `thumbnail_url` adapter output with a clean placeholder when missing.

## Deferred Items
- Reject reason workflow.
- Bulk review reason capture.
- Approved-to-Reup Queue handoff.
- Grid/table view modes.
- Backend hydration/backfill changes.
