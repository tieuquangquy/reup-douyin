# Phase 22F-2 Review Board Workspace Redesign

## Scope

Phase 22F-2 redesigns the frontend Review Board at `/selection/review-board` only. It does not change Capture Inbox promotion, backend hydration/backfill, crawler behavior, backend statuses, or Reup Queue handoff behavior.

## Audited Frontend Path

- Canonical route: `apps/web/src/app/selection/review-board/page.tsx`
- Active page/component: `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- Data loading: `fetchCandidates(appliedFilters)` in `apps/web/src/lib/api.ts`, calling normal `GET /candidates` with `cache: "no-store"`
- Filter/search/sort helpers: `apps/web/src/lib/reviewBoardState.ts`
- Metadata adapter: `apps/web/src/lib/reviewCandidateMetadata.ts`
- Source-inspection regression tests: `apps/web/src/test/review-board.test.ts`
- Shared styling: `apps/web/src/app/globals.css`

## UI Structure

The page now presents a two-pane professional review workspace:

- Left pane: status tabs, search/filter controls, dense candidate list, and selected-row actions.
- Right pane: sticky candidate command panel with thumbnail, score/status, source context, metadata, metrics, and actions.
- Header action points back to Capture Inbox as the upstream source for Review Board candidates.
- Dev-only trace marker is updated to `22F-2` and continues to show route, API endpoint, and refresh time.

## Candidate Card Mapping

The card is compact and scannable while preserving canonical fields:

- Thumbnail uses `thumbnail_url` via `getReviewCandidateMetadata`; missing thumbnail shows `No thumbnail`.
- Visible score uses `reviewCandidateDisplayScore(candidate)`, which resolves canonical `reup_score` only.
- Missing score renders `Unscored`.
- Status renders from `candidate.status` without changing backend status values.
- Caption is clamped to two lines.
- Metadata chips render Posted, Duration, Preset, and ID.
- Metrics chips render Est. Views, Likes, Comments, and Shares.
- Nested checkbox/remove/action buttons stop propagation so card click can select/open the inspector safely.

## Inspector Mapping

The right inspector shows:

- Large preview thumbnail or clean placeholder.
- Score badge and status badge.
- Caption/source context.
- Actions mapped only to existing review status updates: Keep candidate, Mark in review, Reject candidate.
- Core metadata section: Posted, Duration, Est. Views, Likes, Comments, Shares.
- Source/reference section: source video, capture item, aweme ID, source URL, profile URL, posted source, duration source.
- Score/review section: visible Reup Score, diagnostic-only internal score note, label, preset, priority, evaluated, updated.
- Collapsed diagnostics with backend/frontend debug payloads.

## Data Contract Rules Preserved

- Visible score uses `candidate.reup_score` through the metadata adapter.
- Internal `candidate.score` is not used as a visible Review Board score; it is labeled diagnostic-only in the inspector.
- Missing score shows `Unscored`.
- Estimated views prefer `estimated_views_display`, then min/max range, then midpoint/view count, else `—`.
- Missing metrics render `—`, not `0`.
- Duration prefers `duration_text`/adapter text, else `—`.
- Posted prefers exact/display metadata through the adapter, else `—`.
- Review status, decision status, notes, and candidate metadata are not overwritten by the redesign.

## Reup Queue Boundary

Phase 22F-2 removes the page-level visible/send action and frontend call path for Reup Queue handoff from the redesigned Review Board. The page now limits actions to review state updates and removal from Review Board. This matches the phase boundary: no real `Send approved to Reup Queue` action is introduced or expanded in this phase.

## Responsive And Accessibility Notes

- Cards use a desktop two-column grid and collapse to one column under the existing `max-width: 760px` breakpoint.
- Thumbnail previews use a 16:9 aspect ratio.
- Cards are keyboard-focusable and expose an inspect label.
- Search input has an explicit aria label.
- The inspector retains the existing mobile fixed-drawer behavior from shared workflow styles.

## Test Coverage

`apps/web/src/test/review-board.test.ts` covers:

- Canonical route wiring and redirects.
- Shared Ops Console two-pane structure.
- Phase `22F-2` UI and trace markers.
- Score badge, metadata chip, metrics chip, status tabs, inspector empty state, and responsive style smoke checks.
- Reup Queue handoff absence in this phase.
- Visible score helper usage and no visible `candidate.score` display.
- Missing estimated views and metrics rendering as `—`.
- State helpers for selection, status updates, search, and sorting by canonical Reup Score.

## Validation Commands

Run from the repository root:

```bash
npm --workspace @reup-douyin/web run test
npm --workspace @reup-douyin/web run typecheck
npm --workspace @reup-douyin/web run build
```

## Manual QA Checklist

- Open `/selection/review-board`.
- Confirm status tabs show counts and filter the board.
- Confirm search/filter controls preserve existing behavior.
- Confirm cards show thumbnail, Reup Score/Unscored, status, Posted, Duration, Preset, ID, Est. Views, Likes, Comments, Shares.
- Confirm missing views/metrics display `—` and not `0`.
- Confirm clicking a card opens the right inspector for that candidate.
- Confirm Keep, Mark in review, Reject, Remove, Select all, Clear, and selected bulk actions still map to existing handlers.
- Confirm there is no real Send approved to Reup Queue action in this phase.
- Confirm desktop and mobile layouts remain usable.
