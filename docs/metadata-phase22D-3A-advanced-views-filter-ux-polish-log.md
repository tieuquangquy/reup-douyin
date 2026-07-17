# Phase 22D-3A — Advanced estimated views filter and UX polish log

## Summary

Implemented Phase 22D-3A for Capture Inbox Advanced filters. This phase fixes Min/Max estimated views matching, adds strict compact-number parsing, and polishes the Advanced filters panel into a compact card/grid layout.

## Scope

Touched only the frontend Capture Inbox advanced filter surface, source-inspection tests, CSS, and documentation.

## Estimated views bug root cause

The previous frontend estimated views filter compared against `resolveEstimatedViewsForFilter()`, which preferred `resolveKnownViewCountValue(item)` / `view_count` before normalized estimated-view fields and did not average `estimated_views_min` plus `estimated_views_max`. It also did not parse legacy `estimated_views_text_raw`. This meant an active `Views` chip could be shown while filtering used the wrong comparable value or no comparable value.

## Parser behavior

Added `parseCompactNumberInput(value)` returning `{ value, valid, error, normalizedDisplay }`.

Supported examples:

- `5000` -> `5000`
- `5K` / `5k` -> `5000`
- `10K` -> `10000`
- `1.2M` -> `1200000`
- `3万` -> `30000`
- `1.5万` -> `15000`
- `0` -> `0`
- empty or null input -> `null` with `valid: true`

Invalid input now remains invalid instead of silently becoming zero or a usable null filter.

## Comparable estimated views behavior

Added `getComparableEstimatedViews(item)` with source tracking. Priority is:

1. `estimated_views_mid`
2. average of `estimated_views_min` and `estimated_views_max`
3. trusted `view_count` via `resolveKnownViewCountValue(item)`
4. parsed `estimated_views_display`
5. parsed legacy `estimated_views_text_raw`
6. `null`

## Filter behavior

Advanced Min/Max estimated views now compare the numeric comparable value with inclusive bounds:

- Min: item value must be greater than or equal to the min.
- Max: item value must be less than or equal to the max.
- If views filter is active and comparable item value is null, the item does not match.

## Validation

Added exact required validation messages:

- `Invalid estimated views format. Try 10000, 10K, 1.2M, or 3万.`
- `Min estimated views must be less than Max estimated views.`

Apply remains disabled while validation fails.

## Diagnostics

Development/test diagnostics now include:

- `views_filter_input_raw`
- `views_filter_parsed_min`
- `views_filter_parsed_max`
- `item_estimated_views_comparable_source`

## UX/UI polish

Updated Advanced filters with:

- Required subtitle: `Filter by posted date, duration, performance, and metadata quality.`
- Compact empty state: `No advanced filters applied`
- Card classes for Time, Performance, Duration, and Data quality groups
- Performance grid class for denser scanning
- Data quality responsive pill grid
- Compact active filter chips without colon, for examples like `Views ≥ 10K` and `Views ≤ 50K`

## Tests

Updated `apps/web/src/test/capture-inbox.test.ts` to assert parser, comparable-view priority, exact validation messages, diagnostics fields, chip formatting, card/grid UI classes, and data quality pill styles.
