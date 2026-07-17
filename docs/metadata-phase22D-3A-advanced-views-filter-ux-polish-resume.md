# Phase 22D-3A — Advanced estimated views filter and UX polish resume

## Status

Phase 22D-3A implementation is complete pending validation commands.

## Files changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-3A-advanced-views-filter-ux-polish-log.md`
- `docs/metadata-phase22D-3A-advanced-views-filter-ux-polish-resume.md`

## Implemented behavior

- Added strict `parseCompactNumberInput(value)` result helper.
- Updated estimated views validation with exact Phase 22D-3A messages.
- Added `getComparableEstimatedViews(item)` with source tracking.
- Advanced Min/Max estimated views now compare against comparable numeric estimated views instead of display text or wrong-priority view count values.
- Items with no comparable views fail when a views filter is active.
- Added development/test diagnostics for views filter input, parsed bounds, and comparable source.
- Polished Advanced filters into compact card/grid sections.
- Updated active filter chips to use compact labels such as `Views ≥ 10K`.

## Validation to run

Run from repository root on Windows:

```cmd
npx tsx apps/web/src/test/capture-inbox.test.ts
npx tsc --noEmit -p apps/web/tsconfig.typecheck.json
npm --workspace @reup-douyin/web run build
```

## Manual retest checklist

1. Open Capture Inbox.
2. Expand Advanced filters.
3. Enter `5K` in Min estimated views and apply.
4. Confirm only items with comparable views >= `5000` remain.
5. Enter `50K` in Max estimated views and apply.
6. Confirm only items with comparable views <= `50000` remain.
7. Enter `abc` and confirm Apply is disabled with `Invalid estimated views format. Try 10000, 10K, 1.2M, or 3万.`
8. Enter min `50K` and max `10K` and confirm `Min estimated views must be less than Max estimated views.`
9. Reset filters and confirm draft/applied values clear.
10. Collapse and expand Advanced filters and confirm applied filters are preserved.
