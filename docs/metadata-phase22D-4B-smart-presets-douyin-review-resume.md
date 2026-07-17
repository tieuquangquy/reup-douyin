# Phase 22D-4B Smart Presets Resume

## Completed Work

- Added `apps/web/src/lib/captureInboxReviewPresets.ts` with typed Smart Preset IDs, configs, predicates, counts, matching helper, and matching-presets helper.
- Added Smart Presets UI between Studio filters and Advanced filters.
- Integrated preset filtering after Studio filters and before Advanced filters.
- Added preset counts based on Studio-filtered loaded items before Advanced filters.
- Added active preset chip, click-to-clear behavior, and Clear preset action.
- Updated global Clear filters to reset active preset and sort touch state.
- Added sort hints that apply only while sort remains untouched and default.
- Added `lowest_reup_score` sort mode for low-priority review availability.
- Added predicate and source-inspection tests.

## Files Changed

- `apps/web/src/lib/captureInboxReviewPresets.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox-filter-metadata.test.ts`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-4B-smart-presets-douyin-review-log.md`
- `docs/metadata-phase22D-4B-smart-presets-douyin-review-resume.md`

## Pipeline

```txt
items
-> Studio filters
-> Smart preset filter
-> Advanced filters
-> Sort
```

Counts use the Studio-filtered set before preset and Advanced filters.

## Validation Results

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

## Manual Retest Focus

- Smart Presets section appears between Studio filters and Advanced filters.
- Each preset chip shows a count and can be activated.
- Clicking the active preset clears it.
- Global Clear filters clears the active preset.
- Presets combine with Studio filters, Advanced filters, search, and metadata filters.
- Sort hints apply only from default untouched sort.
- No item is auto-promoted, deleted, or hidden permanently.
