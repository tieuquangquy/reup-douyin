# Phase 22D-3B Views Filter Root Fix + Metadata Health UX Resume

## Scope
Phase 22D-3B is limited to Capture Inbox frontend filtering, diagnostics, tests, CSS, and documentation. It intentionally does not touch the Douyin extension crawler, batch collection, backend save endpoints, batch Next 10, Tile Gallery redesign, or Studio filters.

## What Changed
- New helper module: `apps/web/src/lib/captureInboxFilterMetadata.ts`.
- Component refactor: `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` uses adapter-derived metadata for Advanced filters.
- CSS polish: `apps/web/src/app/globals.css` includes Metadata health responsive card styles.
- New regression test: `apps/web/src/test/capture-inbox-filter-metadata.test.ts`.
- Updated source-inspection test: `apps/web/src/test/capture-inbox.test.ts`.
- Documentation:
  - `docs/metadata-phase22D-3B-views-filter-root-fix-metadata-health-ux-log.md`
  - `docs/metadata-phase22D-3B-views-filter-root-fix-metadata-health-ux-resume.md`

## Root Cause
The active chip could show `Views >= 1K`, but the old frontend fallback could not parse range display strings such as `9K-43K`. When numeric normalized fields were absent/null, the comparable estimated-view value became `null`. With a min views filter active, `null` fails the predicate, which explains `Loaded 59`, `Showing 0`, `Hidden by filters 59` for display-range-only data.

## Current Behavior
- Comparable views never treat missing values as zero.
- If a min/max estimated-views filter is active, the adapter-derived comparable value must be non-null and within bounds.
- Display ranges use midpoint; for example `9K-43K` resolves to `26000`.
- Metadata health filters are stored in `metadataHealthFilters` and match with OR semantics.
- Metadata health counts reflect `studioFilteredItems`, before Advanced filters and sorting.

## Validation To Run Before Final Report
Run these from repo root:

```sh
npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts
npx tsx apps/web/src/test/capture-inbox.test.ts
npx tsc --noEmit -p apps/web/tsconfig.typecheck.json
npm --workspace @reup-douyin/web run build
```

## Expected Final Report Headings
1. Summary
2. Files changed
3. Views filter root cause
4. Actual item field shape found
5. Comparable views behavior
6. Views filter fix
7. Metadata health UX redesign
8. Metadata health filter behavior
9. Tests run
10. Build result
11. Manual retest steps
