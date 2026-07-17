# Phase 22D-4A-1 Resume Notes

## Phase

22D-4A-1 — Reup Score badge UX polish and metadata label correctness.

## Completed Work

- Simplified compact Tile Gallery score badge from `Score N Label` to `Score N`.
- Kept score label in the details panel as `Score N · Label`.
- Added score display level mapping for 80/60/40/1 ranges.
- Added `getDouyinMetadataCompletenessForItem(item)` to align completeness with Tile Gallery/filter data sources.
- Changed Capture Inbox missing metadata checks to use computed completeness instead of stale backend missing flags.
- Reworked top overlay into left Select/status group and right score badge.
- Added source-inspection and helper assertions for badge text, score levels, layout classes, computed completeness, stale backend flags, and zero metrics.

## Files Changed

- `apps/web/src/lib/captureInboxFilterMetadata.ts`
- `apps/web/src/lib/captureInboxReupScore.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox-filter-metadata.test.ts`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-4A-1-reup-score-badge-ux-metadata-fix-log.md`
- `docs/metadata-phase22D-4A-1-reup-score-badge-ux-metadata-fix-resume.md`

## Validation Results

Passed:

```sh
npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts
npx tsx apps/web/src/test/capture-inbox.test.ts
npm --workspace @reup-douyin/web run typecheck
npm --workspace @reup-douyin/web run build
```

Attempted full web tests:

```sh
npm --workspace @reup-douyin/web run test
```

The full command failed before Capture Inbox coverage because of the existing Windows source-inspection path issue in `review-board.test.ts`:

```txt
ENOENT: no such file or directory, open 'c:\Users\PC\Desktop\reup_douyin\apps\web\apps\web\src\components\review-board\ReviewBoardPage.tsx'
```

If resuming, re-run the targeted Capture Inbox tests above after any Capture Inbox changes. Re-run the full web test after the unrelated review-board path issue is fixed.

## Manual Retest Focus

- Tile card score badge reads `Score N` only.
- Complete items with visible thumbnail, posted, duration, estimated views, likes, comments, and shares do not show `Needs metadata`.
- Promoted/Ready status remains visible on the card.
- Score badge remains right aligned and does not overlap Select/status.
- Details panel still shows score label and reasons.
