# Phase 6I-F Text-Node Action Rail Extraction Log

## Scope

Phase 6I-F only: fix Full Modal Harvest action rail extraction by using rendered text-node geometry instead of broad ancestor text rejection.

Touched area:
- `apps/extension-douyin-capture`
- focused action rail extraction tests
- Phase 6I-F documentation

Non-goals:
- no backend changes
- no metadata normalizer changes
- no backend browser crawling
- no captcha bypass
- no fake metrics

## Root Cause

Full Modal Harvest already detected the active modal/video and duration, and compact count text was present in the rendered DOM. However, action rail candidate filtering still rejected valid compact counts when a broad ancestor container contained caption/card/modal text. On Douyin full modal pages, valid action rail text nodes can live inside noisy modal ancestors that also contain long captions, tags, ratings, or profile/card content. That made valid compact numeric texts such as `74`, `161`, `94`, `623`, and `109` fail with `ancestor_caption_or_card_text_detected`, leaving action blocks empty.

## Implementation Summary

- Changed action rail compact-count extraction to build candidates from rendered text nodes instead of whole parent elements.
- Added a `TreeWalker` over text nodes and measured each compact text node with `Range.getBoundingClientRect()`.
- Kept only compact count-like text nodes such as `161`, `94`, `623`, `109`, `6.6万`, `8.0万`, and supported suffix count forms.
- Removed active broad ancestor caption/card text rejection from the extraction path.
- Kept text-node-specific rejection rules:
  - invisible or oversized text-node rect
  - bottom player/timeline region
  - left caption area
  - actual profile/video card anchor ancestry via `a[href*="/video/"]`
  - date/rating-like decimals such as `9.7` and `9.8`
  - non-numeric compact-count parse failures
- Preserved Phase 6I-E active video/modal geometry behavior:
  - active video prefers unpaused finite-duration video
  - fallback uses largest visible video
  - candidate scoring remains derived from active video/modal geometry rather than fixed viewport-right assumptions
- Preserved compact count clustering:
  - group eligible text-node candidates by x-position
  - score vertically stacked clusters near the active video/modal side
  - map selected cluster y order to like, comment, favorite, share
- Added required diagnostics to probe/detail metrics:
  - `active_video_rect`
  - `compact_text_node_candidates_count`
  - `compact_count_candidates`
  - `compact_count_clusters`
  - `selected_compact_count_cluster`
  - `selected_cluster_texts`
  - `selected_cluster_rects`
  - `warning_reason`
- Ensured Probe Current Modal Metrics and Full Modal Harvest continue to use the same extraction function.

## PASS/WARN/FAIL Behavior

- `PASS`: aweme id, duration, and all four action counts are detected from the selected compact text-node cluster.
- `WARN`: duration plus one reliable compact count, typically like only, are detected while optional comment/favorite/share counts are missing.
- `FAIL`: no reliable compact count cluster is available, or aweme/duration requirements fail.
- `WARN` still requires explicit operator override before harvest.

## Tests Added/Updated

Focused modal harvest tests now cover:
- noisy modal ancestors no longer reject valid compact count text nodes with `ancestor_caption_or_card_text_detected`
- text-node cluster `161/94/623/109` maps by y order to like/comment/favorite/share
- selected cluster diagnostics expose texts and rects
- compact text-node candidate count is exposed
- actual profile/video anchor ancestry remains rejected
- rating-like decimal text such as `9.8` is rejected
- left caption compact numbers are rejected
- only-like extraction returns `WARN` with `partial_action_cluster`
- existing duration/action rail probe and harvest behavior still shares the same extraction path

## Verification Status

Focused modal harvest tests passed before this documentation was created:

```cmd
cd apps\extension-douyin-capture && npx tsx src/modalHarvest.test.ts
```

Pending after docs:
- rerun TypeScript compile
- run full extension test suite
