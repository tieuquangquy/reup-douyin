# Phase 22D-3 — Advanced filters for Douyin performance, posted date, and duration log

## Summary

Implemented Phase 22D-3 for Capture Inbox Advanced filters. The Advanced panel now filters Douyin captured videos using real normalized metadata fields instead of unsupported risk/speech/text-density controls.

## Current Advanced filters audit

- Component: `AdvancedFilterPanel` in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- Previous state shape: `AdvancedFilterDraft` stored `fromDate`, `toDate`, min/max generic views, metrics, engagement rate, duration seconds, speech, text density, watermark, complexity, and copyright-risk flags.
- Previously real-ish fields: min/max views/likes/comments/shares/engagement/duration were mapped into the legacy backend query payload, but they were not aligned to the Phase 22D normalized Douyin fields.
- Previously unsupported/fake filters: speech, text density, heavy watermark, processing complexity, and copyright risk.
- Previous combine behavior: applying Advanced filters called the backend query endpoint and then Studio filters operated over `queryItems ?? selectedSession?.items ?? []`.
- Previous apply behavior: draft fields were applied only after clicking Apply.
- Normalized fields available in frontend item objects: posted, duration, estimated views, engagement, metric counts, and data quality flags from Phase 22D-1/22D-2.

## Files changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-3-advanced-filters-douyin-performance-date-duration-log.md`
- `docs/metadata-phase22D-3-advanced-filters-douyin-performance-date-duration-resume.md`

## Implementation notes

- Added `AdvancedAppliedFilters` with nullable applied values matching the requested Phase 22D-3 state model.
- Kept `AdvancedFilterDraft` as string-backed form state for date and numeric inputs.
- Advanced chips are derived from `advancedFilterSummaryItems(applied)`, so draft edits do not change active chips before Apply.
- Replaced the backend query-item mode with frontend matching over selected-session `baseItems`.
- Final visible pipeline is now base items → Studio filters → Advanced applied filters → sort.
- Unsupported old filters remain disclosed as unavailable and are not represented in active filters or payload state.

## Time filter behavior

- Posted from/to uses `posted_at` and falls back to safe parsing of `posted_display`.
- Captured from/to uses `created_at` as the available frontend captured timestamp.
- Date ranges are inclusive with start/end-of-day bounds.
- Items missing the relevant date do not match active date ranges.
- Invalid date ranges disable Apply and surface validation text.

## Duration filter behavior

- Duration inputs accept numeric minutes, `mm:ss`, and `hh:mm:ss`.
- Numeric `10` maps to 600 seconds.
- `12.5` maps to 750 seconds.
- Existing item duration matching uses `duration_seconds`, falling back to parsed `duration_text`.
- Missing duration does not match active duration ranges.
- Invalid duration ranges disable Apply and surface validation text.

## Performance filter behavior

- Estimated views filters use `resolveKnownViewCountValue(item)`, then `estimated_views_mid`, then parsed `estimated_views_display` fallback.
- Likes/comments/shares use the normalized count fields.
- Engagement filters use `engagement_score` and `engagement_rate`.
- Numeric input parsing accepts compact values such as `10000`, `10K`, `1.2M`, `3万`, and `1.5万`.
- Engagement-rate inputs are percent values and are converted to decimal rates for matching.
- Missing metric values do not match active metric ranges.
- Invalid min/max ranges disable Apply and surface validation text.

## Data quality filter behavior

- Added toggles for thumbnail, posted date, duration, estimated views, all core metadata, and missing any metadata.
- Data quality filters use normalized `has_*`, `has_all_core_metadata`, and `missing_metadata_fields` when present, with safe fallback checks.

## Apply/reset/collapse behavior

- Apply validates draft input, converts the draft to `AdvancedAppliedFilters`, snapshots applied filters, and prunes selections hidden by the applied filter.
- Reset clears draft and applied filters.
- Collapse only hides the panel body and does not clear applied filters.

## Tests

- Updated `apps/web/src/test/capture-inbox.test.ts` to assert the Phase 22D-3 state model, UI labels, validation, parser helpers, frontend matching, active-chip behavior, and removal of unsupported old active filters.

## Validation completed during implementation

- `npx tsc --noEmit -p apps/web/tsconfig.typecheck.json` passed after implementation fixes.
- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed after test updates.
