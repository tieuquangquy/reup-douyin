# Phase 22A Start Collecting Diagnostics Log

## Scope
- Add scoped diagnostics for the active [`Start Collecting`](apps/extension-douyin-capture/src/popup.ts:709) pipeline in the extension.
- Persist collection progress breadcrumbs without changing Capture Inbox UI behavior.
- Keep the work extension-only unless backend changes become strictly necessary.

## Files changed
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)

## Implemented changes
1. Added persisted harvest diagnostics fields in [`WholeProfileHarvestState`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:327):
   - [`pause_diagnostics`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:356)
   - [`collect_trace`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:357)

2. Initialized those fields in [`createWholeProfileHarvestIdleState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:504) so blocked or fresh runs have a stable diagnostics shape.

3. Extended [`checkpointTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1570) to append bounded per-target trace entries that record:
   - phase
   - aweme id
   - queue size
   - processed / pending / failed counters
   - short operator-facing note
   - structured details such as stage and error code

4. Extended [`pauseHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1604) to persist:
   - pause reason and timestamp
   - raw pause details
   - normalized captcha/checkpoint evidence when present
   - queue progress snapshot at the time of pause
   - a final collect-trace event for the pause transition

5. Updated Advanced diagnostics in [`setDetailSummary()`](apps/extension-douyin-capture/src/popup.ts:1503) to surface:
   - collect trace event count
   - last collect trace event
   - queue progress summary
   - pause diagnostics presence / reason

6. Updated [`copyWholeProfileDebugJsonFromPopup()`](apps/extension-douyin-capture/src/popup.ts:1535) to export a top-level `collect_diagnostics` section containing pause diagnostics, collect trace, and current queue progress.

7. Added regression coverage in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:308) and [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:805) for:
   - blocked Start Collecting state shape
   - captcha pause diagnostics
   - tab-health pause trace persistence

## Validation completed
- Full extension suite via [`npm run extension:test`](package.json:24)
- TypeScript check via `npx tsc -p apps/extension-douyin-capture/tsconfig.json --noEmit`
- Extension build via the build step chained inside [`npm run extension:test`](package.json:24)

## Notes
- No backend files were modified, so backend diagnostics changes were not required for this Phase 22A scope.
- No backend tests or compile checks were needed because the change remained fully inside [`apps/extension-douyin-capture`](apps/extension-douyin-capture).
- Capture Inbox UI behavior was intentionally left unchanged; diagnostics were surfaced only through Advanced details and copied debug JSON.
