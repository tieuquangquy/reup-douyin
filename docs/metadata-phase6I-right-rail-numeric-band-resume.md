# Phase 6I-H Right-Rail Numeric Band Resume

## Current State

Phase 6I-H is implemented in `apps/extension-douyin-capture` and focused modal harvest tests have passed once.

## Changed Files

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `docs/metadata-phase6I-right-rail-numeric-band-log.md`
- `docs/metadata-phase6I-right-rail-numeric-band-resume.md`

## Behavior Summary

The modal action rail extractor now:

1. Selects the active modal video using the existing active-video logic.
2. Builds a right-side rail region from viewport geometry and active video geometry.
3. Collects exact compact numeric labels from visible elements using element rects.
4. Samples `document.elementsFromPoint()` in the right rail band as fallback.
5. Deduplicates and y-sorts labels, then maps the first four labels to like, comment, favorite, and share.
6. Rejects bottom player time, date-like decimals, caption/chapter text, search text, and profile grid card numbers.
7. Uses profile-card fallback only for `like_count`.
8. Emits shared diagnostics for Probe Current Modal Metrics and Full Modal Harvest.

## Verification Completed

Focused test command passed:

```cmd
cd apps\extension-douyin-capture && npx tsx src/modalHarvest.test.ts
```

## Remaining Verification

Run before closing the task:

```cmd
cd apps\extension-douyin-capture && npx tsc -p tsconfig.json --noEmit
cd apps\extension-douyin-capture && npm run test
```

## Live Retest Focus

On the Douyin modal that visibly shows `818`, `15`, `152`, and `35`, run Probe Current Modal Metrics and verify:

- `duration_text` remains around `12:56`
- `like_count = 818`
- `comment_count = 15`
- `favorite_count = 152`
- `share_count = 35`
- `probe_status = PASS`
- `extraction_mode = right_rail_numeric_band` or `right_rail_element_from_point_fallback`
- diagnostics include `rail_region`, `numeric_labels_found`, `selected_rail_labels`, `selected_rail_labels_with_rect`, `assigned_metrics`, and `rejected_examples`
