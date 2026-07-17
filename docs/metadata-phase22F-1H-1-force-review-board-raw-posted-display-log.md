# Phase 22F-1H-1 - Force Review Board Raw Posted Display

## Summary
Phase 22F-1H-1 makes Review Board Posted rendering prefer the raw Capture Inbox `posted_display` snapshot and prevents `posted_at` date formatting when display text exists.

## Audit
- Active component: `apps/web/src/components/review-board/ReviewBoardPage.tsx` `ReviewCandidateCard`.
- Historical bad path: `Posted {metadata.postedDisplay ?? formatDate(source?.posted_at)}`.
- Wrong field: `source?.posted_at`.
- Wrong formatting: `formatDate` used `new Date(value)` and `toLocaleDateString()`, which could render `03/04/2026` instead of Capture Inbox text.
- Secondary Review Board card: `apps/web/src/components/review-board/CandidateCard.tsx` previously formatted `source?.posted_at` with `Intl.DateTimeFormat`; it now uses `getReviewCandidateMetadata(candidate).postedDisplay` first.

## Source Priority
The frontend adapter uses this display/raw priority before any `posted_at` fallback:

```ts
candidate.source_metadata?.posted_display
candidate.sourceMetadata?.posted_display
candidate.source_metadata?.posted_text_raw
candidate.posted_display
candidate.postedDisplay
candidate.metadata?.posted_display
candidate.metadata?.postedDisplay
candidate.metadata?.posted_text_raw
```

Only after those fields are absent does it use `posted_at` fallback values.

## API Contract
`CandidateDetailResponse` exposes raw posted display via:
- `source_metadata.posted_display`
- `source_metadata.posted_text_raw`
- `posted_display`
- `postedDisplay`

Debug fields include:
- `review_candidate_debug.postedDisplaySource`
- `review_candidate_debug.postedDisplayValue`
- `review_candidate_debug.postedAtValue`
- `review_candidate_debug.postedDisplayWasFormatted`

## Bird Fixture
The exact bird case is covered in backend and frontend tests:
- Caption: `190最聪明的鱼和最奇怪的鸟`
- Posted display: `23:00:00 2/4/2026`
- Duration: `12:14`
- Reup score: `42`
- Estimated views: `3.8K-19K`
- Likes/comments/shares: `190/7/5`

Assertions verify Review Board metadata returns `23:00:00 2/4/2026` and not `03/04/2026`, with `postedDisplayWasFormatted = false`.

## Validation
Completed during implementation:
- `cd apps/api && python -m unittest tests.test_phase22f_review_candidate_contract`
- `cd apps/api && python -m compileall src`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run build`

The web build passed with existing webpack path-casing cache warnings and autoprefixer mixed-support warnings in `apps/web/src/app/globals.css`.
