# Phase 22D-3 — Advanced filters for Douyin performance, posted date, and duration resume

## Current status

Phase 22D-3 implementation is complete for the Capture Inbox frontend advanced filters and targeted source-inspection tests.

## Scope completed

- Replaced old generic/unsupported Advanced filters with real Douyin metadata filters.
- Added posted date, captured date, duration, performance, engagement, and data-quality filters.
- Switched Advanced filtering from backend query-item mode to frontend applied matching over loaded session items.
- Preserved Studio filters and combined them before Advanced applied filters and sort.
- Removed unsupported risk/speech/text-density/copyright/complexity filters from active filter state and chips.
- Added validation for invalid date, duration, numeric, and min/max ranges.
- Updated source-inspection tests for Phase 22D-3 behavior.

## Key files

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-3-advanced-filters-douyin-performance-date-duration-log.md`
- `docs/metadata-phase22D-3-advanced-filters-douyin-performance-date-duration-resume.md`

## Validation already run

- `npx tsc --noEmit -p apps/web/tsconfig.typecheck.json`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`

Both passed during implementation.

## Recommended final validation before handoff

Run:

```txt
npx tsx apps/web/src/test/capture-inbox.test.ts
npx tsc --noEmit -p apps/web/tsconfig.typecheck.json
npm --workspace @reup-douyin/web run build
```

Known note from earlier Phase 22D work: full broader web tests may still be affected by an unrelated pre-existing `review-board.test.ts` path issue. The targeted Capture Inbox test and typecheck are the relevant Phase 22D-3 checks.

## Manual retest checklist

1. Open Capture Inbox.
2. Expand Advanced filters.
3. Confirm Time includes Posted from/to and Captured from/to.
4. Confirm Duration accepts numeric minutes and clock notation.
5. Confirm Performance includes estimated views, likes, comments, shares, engagement score, and engagement rate.
6. Confirm Data quality includes thumbnail, posted, duration, estimated views, all core metadata, and missing metadata toggles.
7. Confirm unsupported risk/speech/text-density/copyright/complexity filters are only disclosed as unavailable.
8. Apply filters and confirm chips show applied filters only.
9. Change draft filters without applying and confirm chips do not change.
10. Collapse and expand the panel and confirm applied filters remain active.
11. Reset and confirm draft and applied filters clear.
12. Enter invalid ranges and confirm Apply is disabled with validation text.
