# Phase 6I-D Action Blocks Missing Fix Log

## Scope

Phase 6I-D only: recover Full Modal Harvest and Probe Current Modal Metrics action rail extraction after the strict rail filter rejected valid modal action count nodes.

Touched area:

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`

Non-goals:

- No backend changes.
- No metadata normalizer changes.
- No crawler implementation.
- No captcha bypass.
- No fake metrics.

## Root Cause

The previous action rail guard rejected candidates by walking every ancestor and rejecting any ancestor whose rectangle was larger than `140x140` or whose aggregate text was longer than a short threshold. In the live Douyin modal, valid action count nodes can sit inside a large modal container, so broad ancestor inspection made valid like/comment/favorite/share count nodes look like profile-grid leakage. That caused `action_blocks_missing` even though current modal and duration detection were working.

A secondary issue was that count extraction required every valid count to have a nearby icon pair, leaving no robust fallback when semantic icon identity was unavailable.

## Implementation

- Replaced broad ancestor size rejection with candidate-local size checks.
- Ancestors are rejected only when they are clearly profile-card/grid sources:
  - `a[href*="/video/"]` ancestry.
  - profile/card caption-like text containing rejected markers such as `豆瓣`, `纪录片`, `#`, `关注`, `合集`, or `听抖音`.
- Added two-stage rail extraction:
  - Stage A computes `rail_x_band` from right-side icon/button candidates, with a rightmost viewport fallback.
  - Stage B collects compact count labels inside the rail x-band and filters captions, player timeline text, profile card text, left-caption numbers, and bottom controls.
- Added vertical-order fallback when semantic icon identity is unavailable and four compact right-rail labels are found:
  - first = like
  - second = comment
  - third = favorite
  - fourth = share
- Fixed compact `万` suffix detection for values such as `6.6万`.
- Updated probe readiness status so duration + like + at least two other action counts can PASS, while partial results remain WARN where appropriate.

## Diagnostics Added

Probe and raw DOM detail metrics now expose:

- `rail_x_band`
- `compact_count_candidates`
- `rejected_candidate_examples` with rejection reasons
- `accepted_action_blocks`
- assigned action block metrics via existing `action_block_diagnostics`
- `action_blocks_missing_reason` values:
  - `no_rail_band`
  - `no_compact_counts`
  - `compact_counts_rejected`
  - `ambiguous_order`

## Tests Added Or Updated

Focused modal harvest tests now cover:

- right-rail compact counts `2695 / 94 / 623 / 109` map exactly.
- valid count nodes inside a large modal ancestor are not rejected.
- compact Chinese suffix `6.6万` parses and maps.
- background profile card text with `豆瓣` / `纪录片` / `#` is rejected.
- `a[href*="/video/"]` profile card ancestry is rejected.
- bottom player time `00:39 / 14:02` is not accepted as an action count.
- left caption numbers are rejected as no compact rail counts.
- `action_blocks_missing_reason` distinguishes `no_rail_band` from `no_compact_counts`.
- Probe and Harvest continue to use the same extractor.

## Verification So Far

Focused command passed:

```text
npx tsx src/modalHarvest.test.ts
```

Full extension suite remains pending at this checkpoint.
