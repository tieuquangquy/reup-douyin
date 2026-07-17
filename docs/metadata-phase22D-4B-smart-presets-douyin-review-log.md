# Phase 22D-4B Smart Presets Douyin Review Log

## Why Smart Presets Were Added

Capture Inbox already supports Studio filters, Advanced filters, estimated views, metadata health, Reup Score, and score sorting. Smart Presets add fast review shortcuts so operators can jump to useful Douyin review slices without replacing the existing filter systems.

No extension crawler, batch collection, backend save behavior, auto-promotion, deletion, or Review Board handoff behavior was changed.

## Audit

Current frontend pipeline before this phase:

```txt
selectedSession.items
-> Studio filters: status, search, metadata status, actionable, thumbnail, duplicate toggles
-> Advanced filters: dates, duration, estimated views, likes/comments/shares, engagement, metadata health
-> Sort
```

Reup Score is read through `getReupScoreForCaptureItem(item)`, which uses complete backend score fields when present and falls back to frontend scoring. Estimated views and metadata health use `getDouyinItemMetadataForFilters(item)` and `getDouyinMetadataCompletenessForItem(item)`.

Phase 22D-4B inserts presets after Studio filters and before Advanced filters:

```txt
items
-> Studio filters
-> Smart preset filter
-> Advanced filters
-> Sort
```

This keeps presets combinable with both Studio and Advanced filters.

## Preset List And Rules

- `high_potential`: score >= 70, or score >= 60 with estimated views >= 20000 and shares >= 20; excludes failed, duplicate, or severely incomplete metadata.
- `ready_to_promote`: ready/enriched, complete metadata, score >= 50, not duplicate, not failed, not needs-action, and not already promoted.
- `high_engagement`: engagement rate >= 3, engagement score >= 1000, or likes >= 1000 with comments >= 50; excludes missing metrics and failed items.
- `high_share`: share count >= 50, or shares >= 20 with score >= 60. Shares are not faked from likes/comments.
- `short_strong`: duration 30-900 seconds with score >= 55, or duration 30-1200 seconds with shares >= 20 and likes >= 500; excludes missing duration and failed items.
- `needs_cleanup`: partial/missing/failed metadata, computed missing core metadata, missing thumbnail/posted/duration/views/likes/comments/shares, needs-action status, or retry/failed recoverable status.
- `low_priority`: score < 40, or estimated views < 5000 with engagement score < 200, or likes < 100 with shares < 5. Review-only; no deletion or mutation.

## UI Behavior

The Smart Presets section appears between Studio filters and Advanced filters. Chips are compact, show counts, and allow one active preset at a time. Clicking the active preset clears it. When active, the bar shows `Preset: Label`; `Clear preset` clears only the preset.

Global `Clear filters` clears Studio filters, metadata filters, search, sort, toggles, and the active Smart Preset. Advanced Reset clears only Advanced filters and keeps the active preset.

## Count Behavior

Counts are computed in the frontend from currently loaded items after Studio filters and before Advanced filters. No backend calls are made for counts.

## Filter Combination

Presets do not override other filters. Example: High potential plus Advanced Min shares 50 shows only high-potential items matching the share threshold. Needs cleanup plus Studio Missing posted shows only cleanup items also missing posted.

## Sort Hint Behavior

Preset clicks can apply a sort hint only when the current sort is still the default `ready_first` and the user has not manually touched sort. Hints:

- High potential: Highest Reup Score
- Ready to promote: Highest Reup Score
- High engagement: Highest engagement
- High share: Highest shares
- Short & strong: Highest Reup Score
- Needs cleanup: Recently captured
- Low priority: Lowest Reup Score

## Tests Run

Passed:

```sh
npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts
npx tsx apps/web/src/test/capture-inbox.test.ts
npm --workspace @reup-douyin/web run typecheck
npm --workspace @reup-douyin/web run build
```

Attempted full web test:

```sh
npm --workspace @reup-douyin/web run test
```

The full command failed before Capture Inbox coverage on the existing Windows source-inspection path issue in `review-board.test.ts`:

```txt
ENOENT: no such file or directory, open 'c:\Users\PC\Desktop\reup_douyin\apps\web\apps\web\src\components\review-board\ReviewBoardPage.tsx'
```

Build passed with existing non-blocking warnings for Windows webpack cache path casing and CSS autoprefixer `start`/`end` alignment values.

## Known Limitations

- Presets are review shortcuts, not automatic decisions.
- Reup Score is heuristic.
- Estimated views are estimated, not actual Douyin views.
- Bulk action and Review Board handoff come later.
