# Phase 22D-2 — Studio filters redesign for Douyin metadata resume

## Status

Phase 22D-2 implementation is complete pending final full web test/build verification and final report.

## Files changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-2-studio-filters-douyin-metadata-log.md`
- `docs/metadata-phase22D-2-studio-filters-douyin-metadata-resume.md`

## What changed

- Replaced old Studio filter type values with Douyin-oriented values.
- Added `StudioFilters` type documenting the requested state model.
- Updated search placeholder to `Caption, video ID, profile, source URL`.
- Expanded search text to include caption, title, source video ID, aweme ID, source/share/video/profile URLs, and profile names.
- Replaced broad metadata filters with concrete metadata completeness filters:
  - All metadata
  - Complete
  - Missing posted
  - Missing thumbnail
  - Missing duration
  - Missing metrics
- Added all required sort modes.
- Updated filter diagnostics to show `Showing X of Y`, loaded items, and hidden-by-filter count.
- Added optional frontend typings for Phase 22D-1 normalized fields.
- Updated Capture Inbox source tests to assert Phase 22D-2 toolbar/filter behavior.

## Validation already run

- `npx tsx apps/web/src/test/capture-inbox.test.ts` — passed.
- `npx tsc --noEmit -p apps/web/tsconfig.typecheck.json` — passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsc --noEmit -p apps/web/tsconfig.typecheck.json` — passed.

## Remaining validation

Run the broader requested web verification before final completion:

- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run build`

If workspace script names differ, equivalent commands from `apps/web` are:

- `npm run test`
- `npm run typecheck`
- `npm run build`

## Manual retest steps

1. Open Capture Inbox.
2. Confirm Studio search placeholder is `Caption, video ID, profile, source URL`.
3. Search by caption, title, aweme ID, source URL, video URL, profile URL, and profile name where available.
4. Click each item status filter and confirm only matching items remain.
5. Click each metadata filter and confirm missing posted/thumbnail/duration/metrics groupings behave honestly.
6. Toggle `Only actionable`, `Only with thumbnail`, and `Hide duplicates` individually and together.
7. Try every sort option and confirm missing values sort after known values with stable fallback.
8. Click `Clear filters` and confirm search, item status, metadata filter, toggles, session status, and sort reset.
9. Confirm Advanced filters still exist but were not redesigned or expanded in this phase.
10. Confirm Tile Gallery card layout did not change.

## Notes for future phases

- Advanced filters are still out of scope for this phase and should be handled separately.
- Backend response mapping was not changed in this phase because the frontend can consume Phase 22D-1 normalized response fields as optional properties.
- Legacy staged items remain supported through fallback checks.
