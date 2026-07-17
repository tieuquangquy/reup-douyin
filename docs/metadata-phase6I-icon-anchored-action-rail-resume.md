# Phase 6I-G Icon-Anchored Action Rail Resume

## Current Status

Phase 6I-G is complete. The Douyin extension no longer maps modal like/comment/favorite/share from numeric clusters alone. Modal metrics are now extracted from icon-anchored right-rail action blocks.

## Files Changed

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `docs/metadata-phase6I-icon-anchored-action-rail-log.md`
- `docs/metadata-phase6I-icon-anchored-action-rail-resume.md`

## Extractor Behavior

1. Select active modal video from the playing video when available, else largest visible video.
2. Collect visible right-rail icon/button candidates near the active video.
3. Infer action type from semantic hints when available.
4. Fall back to vertical visual order only among icon-like candidates.
5. For each action icon, choose the nearest compact numeric count below the icon within the same x-band.
6. Reject text-only numeric clusters that lack a right-rail icon anchor.
7. Return matching diagnostics through both Probe Current Modal Metrics and Full Modal Harvest.

## Diagnostics Added

- `icon_candidates`
- `selected_action_icons`
- `icon_anchored_metrics`
- `rejected_number_examples`
- `rejected_icon_examples`

Each icon-anchored metric diagnostic includes the metric name, icon rectangle, count text, count rectangle, icon-to-count distance, and `source = icon_anchored_right_rail`.

## Exclusions Added

Counts are rejected for profile grid anchors, search boxes, left caption/content area, bottom player controls, chapter/rating/hash/profile context, and current/total time text.

## Verification

Passing commands:

- `cd apps\\extension-douyin-capture && npx tsc -p tsconfig.json --noEmit`
- `cd apps\\extension-douyin-capture && npx tsx src/modalHarvest.test.ts`
- `cd apps\\extension-douyin-capture && npm run test`

## Live Retest

1. Rebuild or reload the unpacked extension from `apps/extension-douyin-capture/dist` after running `npm run test` or `npm run build`.
2. Open a Douyin profile grid and open a video modal where the visible rail shows like/comment/favorite/share counts.
3. Run Probe Current Modal Metrics.
4. Verify `probe_status = PASS` when duration plus all four action metrics are detected.
5. Verify `icon_candidates`, `selected_action_icons`, and `icon_anchored_metrics` are present.
6. Verify each metric diagnostic has `source = icon_anchored_right_rail` and the expected count text below the matching icon.
7. Run Full Modal Harvest on the same modal and verify it returns the same action metric values as the probe.
