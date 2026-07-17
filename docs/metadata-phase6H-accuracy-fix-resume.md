# Phase 6H Accuracy Fix Resume

## Current target

Fix Full Modal Harvest DOM metric extraction accuracy before running the full 49-video sweep.

## Root cause summary

- Duration extraction mixed two sources without validating they represented the same active video.
- Side action counts were derived from generic nearby-node scanning, so one count node could be reused across multiple metrics.

## Intended post-fix behavior

- `duration_seconds` stays tied to the active video element.
- `duration_text` is only kept when it agrees with the active video duration.
- Like/comment/favorite/share counts come from distinct action blocks, not shared generic text nodes.
- Ambiguous metrics stay null and emit diagnostic reasons instead of guessed values.

## Operator-visible diagnostics to add

- last harvested item summary in popup progress
- duration source and conflict diagnostics
- per-action block raw text
- rejected metric reasons

## Verification plan

- extension typecheck
- extension test suite with new focused accuracy tests
- no backend changes expected unless source labels need tiny alignment

## Implemented outcome

- active-video duration is now the primary canonical modal duration source
- conflicting timeline totals no longer leak into canonical `duration_text`
- side action metrics now require distinct action blocks
- ambiguous or shared blocks now leave the metric null with a diagnostic reason
- popup progress now includes the last harvested item summary for live spot checks

## Exact live retest steps

1. `cd apps/extension-douyin-capture`
2. `npm run build`
3. Reload the unpacked extension.
4. Open the Douyin profile page and click the first video modal.
5. Start Full Modal Harvest and inspect `Show Harvest Progress` after the first item.
6. Verify the last harvested item summary shows:
   - correct `aweme_id`
   - `duration_seconds`
   - non-duplicated `like/comment/favorite/share` values
   - `extraction_warning` only when a metric was intentionally rejected
7. Flush harvested metadata.
8. `cd ../api`
9. `python tests/metadata_phase5a_real_live_audit.py`
