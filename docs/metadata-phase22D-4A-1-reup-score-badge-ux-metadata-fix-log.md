# Phase 22D-4A-1 Reup Score Badge UX And Metadata Fix Log

## Scope

Phase 22D-4A-1 polishes the Capture Inbox Tile Gallery Reup Score badge and fixes false `Needs metadata` labels caused by stale backend completeness flags.

No Douyin extension crawler logic, batch collection logic, backend save behavior, or promotion behavior was changed.

## Audit Findings

1. The score badge is rendered in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` inside `MediaTile`.
2. The verbose `Score 54 Average` text came from `reupScoreBadgeText`, which appended `reup_score_label` to the compact badge.
3. `Needs metadata` on score badges came from `reup_score_level === "needs_metadata"` in `reupScoreBadgeText` and from score label logic in `apps/web/src/lib/captureInboxReupScore.ts`.
4. Card metadata gap text used `hasMissingAnyMetadata`, which previously trusted stale `missing_metadata_fields` and `has_all_core_metadata === false` before recomputing visible metadata.
5. The Tile Gallery displayed metadata through canonical/adapter helpers, but completeness could rely on stale backend fields, so an item could visibly show thumbnail, posted, duration, estimated views, likes, comments, and shares while still being labeled incomplete.

## Badge Text

The compact card badge now renders only:

```txt
Score N
```

The score label remains available in the details panel as:

```txt
Score N · Average
```

This keeps cards scannable while preserving explanation in the inspector.

## Score Color Levels

Score color levels now follow the requested ranges:

- `excellent`: 80-100, strong readable green
- `good`: 60-79, light teal/blue-green
- `average`: 40-59, soft amber/yellow
- `low`: 1-39, soft red
- `needs_metadata`: score 0, missing score, or incomplete key metadata, neutral gray

## Metadata Completeness Helper

Added `getDouyinMetadataCompletenessForItem(item)` in `apps/web/src/lib/captureInboxFilterMetadata.ts`.

It uses the same source family as Tile Gallery display and filters:

- thumbnail from `resolveThumbnailUrl`
- posted from `posted_at`, `posted_display`, or `posted_text`
- duration from finite `duration_seconds` or non-empty `duration_text`
- estimated views from the shared estimated views adapter, including like-derived estimates
- likes/comments/shares from finite numeric fields, with `0` treated as present

Computed visible data wins over stale `missing_metadata_fields` and `has_all_core_metadata` flags. Diagnostics include whether stale backend missing flags were ignored.

## Badge Layout

The top overlay now separates the left and right responsibilities:

```txt
[Select] [Promoted/Ready]                         [Score N]
```

The score remains right aligned, while Select and status are grouped on the left with wrapping support for narrow cards. Card height is not increased.

## Tests Run

Targeted Capture Inbox validation passed:

```sh
npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts
npx tsx apps/web/src/test/capture-inbox.test.ts
npm --workspace @reup-douyin/web run typecheck
```

The full web test command was also attempted:

```sh
npm --workspace @reup-douyin/web run test
```

It failed before the Capture Inbox tests on the existing Windows source-inspection path issue in `review-board.test.ts`:

```txt
ENOENT: no such file or directory, open 'c:\Users\PC\Desktop\reup_douyin\apps\web\apps\web\src\components\review-board\ReviewBoardPage.tsx'
```

## Build Result

```sh
npm --workspace @reup-douyin/web run build
```

Build passed. Existing non-blocking warnings remained for Windows webpack cache path casing and CSS autoprefixer `start`/`end` alignment values.
