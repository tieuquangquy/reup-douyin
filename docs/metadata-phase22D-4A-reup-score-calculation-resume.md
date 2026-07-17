# Phase 22D-4A Reup Score Calculation Resume

## Files Changed
- `apps/web/src/lib/captureInboxReupScore.ts`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox-filter-metadata.test.ts`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-4A-reup-score-calculation-log.md`
- `docs/metadata-phase22D-4A-reup-score-calculation-resume.md`

## Implementation Notes
- Helper name: `calculateDouyinReupScore(item, options)`.
- Runtime accessor: `getReupScoreForCaptureItem(item, options)`.
- Backend-compatible optional fields were added to the frontend `CapturedItem` type:
  - `reup_score`
  - `reup_score_label`
  - `reup_score_level`
  - `reup_score_components`
  - `reup_score_reasons`
- Existing backend score fields are preferred when complete; otherwise the frontend fallback calculates the score.

## Score Output
```ts
{
  reup_score: number,
  reup_score_label: "Excellent" | "Good" | "Average" | "Low" | "Needs metadata",
  reup_score_level: "excellent" | "good" | "average" | "low" | "needs_metadata",
  reup_score_components: {
    performance: number,
    engagement: number,
    shareability: number,
    duration_fit: number,
    recency: number,
    metadata_quality: number,
    penalty: number
  },
  reup_score_reasons: string[]
}
```

## Manual Retest Steps
1. Open Capture Inbox with a session containing complete Douyin metadata.
2. Confirm each Tile Gallery card shows `Score NN Label` or `Needs metadata`.
3. Open item details and confirm the Reup Score section shows components and reasons.
4. Select `Highest Reup Score` in sort options and confirm high-score items appear first.
5. Confirm duplicate, failed, and missing-metadata items are not hidden by default.

## Validation
- `npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts` passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed.
- `npm run typecheck --workspace @reup-douyin/web` passed.
- `npm run build --workspace @reup-douyin/web` passed with existing CSS/autoprefixer warnings.
- Full `npm --workspace apps/web run test` and `npm run test --workspace @reup-douyin/web` currently fail before Capture Inbox tests because existing source-inspection tests resolve `apps/web/apps/web/...` paths on this Windows workspace.
