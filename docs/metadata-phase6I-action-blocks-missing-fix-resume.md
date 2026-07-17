# Phase 6I-D Action Blocks Missing Fix Resume

## Current Status

Phase 6I-D implementation is complete in the extension and focused modal harvest tests pass.

## Files Changed

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `docs/metadata-phase6I-action-blocks-missing-fix-log.md`
- `docs/metadata-phase6I-action-blocks-missing-fix-resume.md`

## Key Behavior

The action rail extractor now uses two stages:

1. Compute a right action rail x-band from visible right-side icon/button candidates, falling back to the rightmost viewport rail when needed.
2. Collect compact count labels in that x-band and reject only clear leakage sources such as profile grid anchors, caption/card text, timeline text, left-side caption numbers, and bottom controls.

Valid count nodes are no longer rejected solely because a modal ancestor is large.

## Diagnostics To Inspect In Live Probe

Probe Current Modal Metrics should now show:

- `rail_x_band`
- `compact_count_candidates`
- `accepted_action_blocks`
- `rejected_candidate_examples`
- assigned metrics in `action_block_diagnostics`
- `action_blocks_missing_reason` if extraction still fails

Expected failure reason meanings:

- `no_rail_band`: no usable viewport/icon rail could be computed.
- `no_compact_counts`: no compact count labels were found inside the rail.
- `compact_counts_rejected`: compact labels existed but were rejected by safety filters.
- `ambiguous_order`: accepted labels existed but could not be safely assigned.

## Verification Completed

Focused test command passed:

```text
cd apps/extension-douyin-capture && npx tsx src/modalHarvest.test.ts
```

## Remaining Verification

Run the full extension suite:

```text
cd apps/extension-douyin-capture && npm run test
```

## Live Retest Steps

1. Rebuild/reload the extension from `apps/extension-douyin-capture/dist` after running the full test/build command.
2. Open the Douyin profile grid and open a video modal.
3. Use Probe Current Modal Metrics.
4. Confirm the modal aweme id is detected.
5. Confirm duration seconds are detected.
6. Confirm `rail_x_band` is present.
7. Confirm `compact_count_candidates` includes the visible rail counts.
8. Confirm accepted action blocks assign at least `like_count` plus two of `comment_count`, `favorite_count`, and `share_count`.
9. Confirm probe status is PASS for that case, or WARN only when one optional action count is genuinely missing.
10. Confirm rejected examples do not include the valid modal rail counts and do include background profile-grid/card leakage when present.
