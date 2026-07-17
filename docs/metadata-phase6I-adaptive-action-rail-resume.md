# Phase 6I-E Adaptive Action Rail Detection Resume

## Completed

- Read `AGENTS.md` and scoped work to Phase 6I-E.
- Updated `apps/extension-douyin-capture/src/types.ts` with adaptive action rail diagnostics.
- Updated `apps/extension-douyin-capture/src/modalHarvest.ts` to use active video/modal geometry plus compact count x-clustering instead of rejecting candidates by fixed viewport-right rail before clustering.
- Updated probe and harvested-item status behavior:
  - `PASS` for duration plus all four action counts.
  - `WARN` for duration plus reliable like when optional action counts are missing.
  - `FAIL` for missing aweme id, missing duration, or no reliable like/action source.
- Updated `shouldRequireProbeOverride()` so `WARN` requires explicit override.
- Updated `apps/extension-douyin-capture/src/modalHarvest.test.ts` with adaptive cluster coverage and Phase 6I-E status expectations.
- Ran focused modal harvest test successfully.

## Current Behavior

Adaptive action rail detection now:
- records viewport and active video geometry diagnostics
- collects compact count candidates without fixed right-viewport x rejection
- rejects known non-action sources such as profile/video cards, captions, ratings, hashtags, long text, and timeline text
- clusters compact count candidates by x-position
- selects the best vertically stacked rail cluster near the active video/modal right side
- maps selected cluster y order to like, comment, favorite, share
- keeps profile grid fallback like-only

## Tests Run

```cmd
cd apps/extension-douyin-capture && npx tsx src/modalHarvest.test.ts
```

Result: passed.

## Pending

- Run TypeScript compile again after docs/test edits.
- Run full extension test:

```cmd
cd apps/extension-douyin-capture && npm run test
```

- Prepare final Phase 6I-E report with:
  1. exact root cause
  2. files/functions changed
  3. adaptive rail/cluster detection method
  4. PASS/WARN/FAIL behavior
  5. tests run
  6. verification result
  7. exact live retest steps

## Live Retest Draft

1. Reload the unpacked Chrome extension from `apps/extension-douyin-capture` after building if needed.
2. Open the Douyin profile/video modal where probe aweme `7624192822287142207` was observed.
3. Open the extension popup.
4. Run Probe Current Modal Metrics.
5. Confirm diagnostics show:
   - `active_video_rect`
   - `computed_rail_x_band`
   - compact count candidates for `90`, `6`, `32`, `10`
   - a selected compact count cluster
6. Confirm metric values:
   - like = `90`
   - comment = `6`
   - favorite = `32`
   - share = `10`
7. Confirm probe status is `PASS` when all four counts are present, or `WARN` only when duration plus like are present and optional action counts are missing.
